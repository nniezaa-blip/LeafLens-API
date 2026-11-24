"""End-to-end backend journey driven by a simulated device.

No hardware is required. A local FavorIoT v2 stand-in receives telemetry from a
simulated device, the real API client reads it, and a real RS256 access token is
verified against a locally served JWKS. The D1 binding is backed by the actual
migration file applied to in-memory SQLite.
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.db.d1 import get_db
from app.main import app
from app.routers import ws as ws_router

_READ_KEY = "simulated-read-key"
_WRITE_KEY = "simulated-write-key"
_DEVICE_ID = "Agrilink_1_device@anwarzain"
_USER_ID = "e2e-user-id"
_ISSUER = "lextari-auth"
_AUDIENCE = "lextari-app"


class SimulatedFavorIoT:
    """In-memory FavorIoT v2 endpoint used by the simulated device."""

    def __init__(self) -> None:
        self.devices: dict[str, dict[str, Any]] = {}
        self.streams: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self.make_handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> str:
        self._thread.start()
        return f"http://127.0.0.1:{self._server.server_port}/v2"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def publish(self, data: dict[str, Any], timestamp_ms: int) -> None:
        self.streams.append(
            {
                "device_developer_id": _DEVICE_ID,
                "timestamp": timestamp_ms,
                "stream_created_at": datetime.fromtimestamp(timestamp_ms / 1000, UTC).isoformat(),
                "data": {key: str(value) for key, value in data.items()},
            }
        )

    def read_commands(self) -> list[dict[str, Any]]:
        return [row["data"] for row in self.streams if "command" in row["data"]]

    def make_handler(self) -> type[BaseHTTPRequestHandler]:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if not service.is_authorized(self.headers.get("apikey"), expected=_READ_KEY):
                    self.send_error(401)
                    return
                query = parse_qs(parsed.query)
                if parsed.path == "/v2/devices":
                    self._reply(service.list_devices(query))
                elif parsed.path.startswith("/v2/devices/"):
                    device_id = unquote(parsed.path.removeprefix("/v2/devices/"))
                    self._reply(service.devices.get(device_id, {}))
                elif parsed.path == "/v2/streams":
                    self._reply({"results": service.list_streams(query)})
                else:
                    self.send_error(404)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if not service.is_authorized(self.headers.get("apikey"), expected=_WRITE_KEY):
                    self.send_error(401)
                    return
                length = int(self.headers.get("content-length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                if parsed.path == "/v2/devices":
                    self._reply(service.create_device(body))
                elif parsed.path == "/v2/streams":
                    service.append_stream(body)
                    self._reply({"status": "ok"})
                else:
                    self.send_error(404)

            def _reply(self, payload: Any) -> None:
                encoded = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args: Any) -> None:
                return

        return Handler

    def is_authorized(self, supplied: str | None, expected: str) -> bool:
        return supplied == expected

    def list_devices(self, query: dict[str, list[str]]) -> dict[str, Any]:
        name = query.get("device_name", [None])[0]
        rows = [
            device
            for device in self.devices.values()
            if name is None or device["device_name"] == name
        ]
        return {"results": rows}

    def create_device(self, body: dict[str, Any]) -> dict[str, Any]:
        device_id = f"{body['device_name'].replace(' ', '_')}_device@anwarzain"
        device = {
            "device_developer_id": device_id,
            "device_name": body["device_name"],
            "accesstoken": "simulated-device-token",
            "active": body.get("active", True),
        }
        self.devices[device_id] = device
        return device

    def append_stream(self, body: dict[str, Any]) -> None:
        self.streams.append(
            {
                "device_developer_id": body["device_developer_id"],
                "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                "data": body["data"],
            }
        )

    def list_streams(self, query: dict[str, list[str]]) -> list[dict[str, Any]]:
        device_id = query.get("device_developer_id", [None])[0]
        rows = [
            row
            for row in self.streams
            if device_id is None or row["device_developer_id"] == device_id
        ]
        created_range = query.get("created_from_to", [None])[0]
        if created_range:
            start_ms, end_ms = _parse_range(created_range)
            rows = [row for row in rows if start_ms <= row["timestamp"] <= end_ms]
        descending = query.get("order", ["desc"])[0].lower() == "desc"
        rows = sorted(rows, key=lambda row: row["timestamp"], reverse=descending)
        limit = int(query.get("max", [len(rows)])[0])
        return rows[:limit]


class LocalJwks:
    """Serves a public JWKS and signs access tokens with the matching key."""

    def __init__(self) -> None:
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._kid = "e2e-signing-key"
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self.make_handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> str:
        self._thread.start()
        return f"http://127.0.0.1:{self._server.server_port}/.well-known/jwks.json"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def token(self) -> str:
        now = int(datetime.now(UTC).timestamp())
        payload = {
            "sub": _USER_ID,
            "email": "e2e@example.com",
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + 3600,
        }
        return jwt.encode(
            payload, self._private_key, algorithm="RS256", headers={"kid": self._kid}
        )

    def jwks(self) -> dict[str, Any]:
        key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self._private_key.public_key()))
        key.update({"alg": "RS256", "kid": self._kid, "use": "sig"})
        return {"keys": [key]}

    def make_handler(self) -> type[BaseHTTPRequestHandler]:
        identity = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                encoded = json.dumps(identity.jwks()).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args: Any) -> None:
                return

        return Handler


class SqliteD1:
    """D1-shaped adapter over the real migration applied to SQLite."""

    def __init__(self, migration: Path) -> None:
        self._connection = sqlite3.connect(":memory:", check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(migration.read_text())

    def prepare(self, sql: str) -> "SqliteStatement":
        return SqliteStatement(self._connection, sql)


class _D1Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.results = rows


class SqliteStatement:
    def __init__(self, connection: sqlite3.Connection, sql: str) -> None:
        self._connection = connection
        self._sql = sql
        self._params: tuple[Any, ...] = ()

    def bind(self, *params: Any) -> "SqliteStatement":
        self._params = params
        return self

    async def all(self) -> _D1Result:
        rows = self._connection.execute(self._sql, self._params).fetchall()
        return _D1Result([dict(row) for row in rows])

    async def first(self) -> dict[str, Any] | None:
        row = self._connection.execute(self._sql, self._params).fetchone()
        return dict(row) if row is not None else None

    async def run(self) -> None:
        self._connection.execute(self._sql, self._params)
        self._connection.commit()


def _parse_range(value: str) -> tuple[int, int]:
    bounds = value.strip("[]").split(" TO ")
    moments = [datetime.fromisoformat(bound) for bound in bounds]
    return tuple(int(moment.timestamp() * 1000) for moment in moments)  # type: ignore[return-value]


def _configure_environment(
    monkeypatch: pytest.MonkeyPatch, favoriot_url: str, jwks_url: str
) -> None:
    monkeypatch.setenv("FAVORIOT_URL", favoriot_url)
    monkeypatch.setenv("FAVORIOT_READ_ONLY_API_KEY", _READ_KEY)
    monkeypatch.setenv("FAVORIOT_READ_WRITE_API_KEY", _WRITE_KEY)
    monkeypatch.setenv("AUTH_JWKS_URL", jwks_url)
    monkeypatch.setenv("AUTH_ISSUER", _ISSUER)
    monkeypatch.setenv("AUTH_AUDIENCE", _AUDIENCE)


def _create_database() -> SqliteD1:
    migration = Path(__file__).resolve().parents[1] / "migrations" / "0001_init.sql"
    return SqliteD1(migration)


def _assert_authentication_boundaries(client: TestClient) -> None:
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/devices").status_code == 401
    assert (
        client.get("/api/devices", headers={"Authorization": "Bearer invalid"}).status_code == 401
    )


def _register_device(client: TestClient) -> None:
    registration = client.post(
        "/api/v1/devices/register",
        json={
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "user_id": _USER_ID,
            "device_name": "Agrilink 1",
        },
    )
    assert registration.status_code == 200
    assert registration.json()["device_id"] == _DEVICE_ID
    assert registration.json()["device_access_token"] == "simulated-device-token"


def _publish_device_readings(favoriot: SimulatedFavorIoT) -> None:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    favoriot.publish(
        {
            "soil_moisture": 55,
            "temperature": 24,
            "humidity": 65,
            "water_level": 80,
            "fanStatus": "on",
        },
        now_ms,
    )
    favoriot.publish({"temperature": 20}, now_ms - 3_600_000)


def _assert_http_journey(client: TestClient, token: str, favoriot: SimulatedFavorIoT) -> None:
    headers = {"Authorization": f"Bearer {token}"}

    devices = client.get("/api/devices", headers=headers)
    assert devices.status_code == 200
    assert devices.json() == {
        "devices": [
            {
                "platform_device_id": _DEVICE_ID,
                "device_name": "Agrilink 1",
                "device_type": "lextari-env",
            }
        ]
    }

    latest = client.get(f"/api/v1/telemetry/{_DEVICE_ID}/latest", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["readings"] == {
        "soil_moisture": 55.0,
        "temperature": 24.0,
        "humidity": 65.0,
        "water_level": 80.0,
    }

    history = client.get("/api/telemetry/temperature?days=7", headers=headers)
    assert history.status_code == 200
    assert {point["value"] for point in history.json()["points"]} == {20.0, 24.0}

    health = client.get("/api/health-score", headers=headers)
    assert health.status_code == 200
    assert health.json()["score"] == 100.0
    assert health.json()["status"] == "Optimal"

    command = client.post(
        "/api/rpc",
        json={"method": "refill_on", "params": {"liters": 2}},
        headers=headers,
    )
    assert command.status_code == 200
    assert command.json()["sent"] is True
    assert favoriot.read_commands() == [{"command": "refill_on", "params": {"liters": 2}}]


def _assert_websocket_journey(client: TestClient, token: str) -> None:
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": token})
        assert websocket.receive_json() == {"type": "auth_ok"}
        assert websocket.receive_json() == {
            "type": "telemetry",
            "soilMoisture": 55.0,
            "temperature": 24.0,
            "humidity": 65.0,
            "waterLevel": 80.0,
        }
        assert websocket.receive_json() == {"type": "ghs", "score": 100.0, "status": "Optimal"}


def test_full_backend_journey_with_simulated_device(monkeypatch: pytest.MonkeyPatch) -> None:
    favoriot = SimulatedFavorIoT()
    jwks = LocalJwks()
    favoriot_url = favoriot.start()
    jwks_url = jwks.start()
    _configure_environment(monkeypatch, favoriot_url, jwks_url)

    d1 = _create_database()
    app.dependency_overrides[get_db] = lambda: d1
    monkeypatch.setattr(ws_router, "get_db_from_scope", lambda scope: d1)

    try:
        client = TestClient(app)
        token = jwks.token()
        _assert_authentication_boundaries(client)
        _register_device(client)
        _publish_device_readings(favoriot)
        _assert_http_journey(client, token, favoriot)
        _assert_websocket_journey(client, token)
    finally:
        app.dependency_overrides.clear()
        jwks.stop()
        favoriot.stop()
