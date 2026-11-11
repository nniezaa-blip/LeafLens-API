"""WebSocket relay that polls ThingsBoard for the user's device."""

import asyncio
import logging
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.jwks import verify_supabase_token
from app.clients.thingsboard import ThingsBoardClient
from app.config import Settings, get_settings_from_scope
from app.db.d1 import get_db_from_scope, query_first
from app.services.ghs import compute_health_score

logger = logging.getLogger(__name__)

router = APIRouter()

_TELEMETRY_FIELDS = {
    "soil_moisture": "soilMoisture",
    "temperature": "temperature",
    "humidity": "humidity",
    "water_level": "waterLevel",
}


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _make_tb_client(settings: Settings) -> ThingsBoardClient:
    return ThingsBoardClient(settings)


async def _resolve_device_id(user_id: str, db: Any) -> str | None:
    if db is None:
        return None
    row = await query_first(
        db,
        "SELECT tb_device_id FROM user_devices WHERE user_id = ? ORDER BY id LIMIT 1",
        [user_id],
    )
    return str(row["tb_device_id"]) if row is not None else None


async def _read_token(websocket: WebSocket) -> tuple[str, bool] | None:
    """Read the JWT from the query string or the first ``auth`` message."""
    token = websocket.query_params.get("token")
    if token is not None:
        return token, False

    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except (TimeoutError, WebSocketDisconnect):
        return None
    if not isinstance(first, dict) or first.get("type") != "auth":
        return None
    candidate = first.get("token")
    if not isinstance(candidate, str) or not candidate:
        return None
    return candidate, True


class _RelayConnection:
    """Per-client relay state and outbound message shaping."""

    def __init__(
        self,
        websocket: WebSocket,
        tb: ThingsBoardClient,
        poll_interval: int,
    ) -> None:
        self._websocket = websocket
        self._tb = tb
        self._poll_interval = poll_interval
        self._send_lock = asyncio.Lock()
        self._latest: dict[str, object] = {}
        self._poll_task: asyncio.Task[None] | None = None
        self.device_id: str | None = None

    async def send(self, payload: dict[str, object]) -> None:
        try:
            async with self._send_lock:
                await self._websocket.send_json(payload)
        except (RuntimeError, WebSocketDisconnect):
            pass

    async def attach(self, device_id: str | None) -> None:
        self.device_id = device_id
        self._latest.clear()
        if device_id is None:
            return
        try:
            snapshot = await self._tb.get_latest_telemetry(
                device_id,
                keys=list(_TELEMETRY_FIELDS),
            )
        except Exception:
            logger.warning("Initial telemetry fetch failed", exc_info=True)
            return
        self._latest.update(snapshot)
        await self.send_telemetry()
        await self.send_health()

    def detach(self) -> None:
        self.device_id = None

    def start(self) -> None:
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll())

    async def stop(self) -> None:
        self.detach()
        task = self._poll_task
        self._poll_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def switch(self, device_id: str) -> None:
        if device_id == self.device_id:
            return
        await self.attach(device_id)
        await self.send({"type": "subscribed", "device_id": device_id})

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            device_id = self.device_id
            if device_id is None:
                continue
            try:
                snapshot = await self._tb.get_latest_telemetry(
                    device_id,
                    keys=list(_TELEMETRY_FIELDS),
                )
            except Exception:
                logger.warning("Telemetry poll failed", exc_info=True)
                continue
            if snapshot == self._latest:
                continue
            self._latest.update(snapshot)
            await self.send_telemetry()
            await self.send_health()

    async def send_telemetry(self) -> None:
        readings = {
            camel: self._latest[key]
            for key, camel in _TELEMETRY_FIELDS.items()
            if key in self._latest
        }
        if readings:
            await self.send({"type": "telemetry", **readings})

    async def send_health(self) -> None:
        soil = _as_float(self._latest.get("soil_moisture"))
        temperature = _as_float(self._latest.get("temperature"))
        humidity = _as_float(self._latest.get("humidity"))
        if soil is None or temperature is None or humidity is None:
            return
        score, status, _ = compute_health_score(
            soil_moisture=soil,
            temperature=temperature,
            humidity=humidity,
        )
        await self.send({"type": "ghs", "score": score, "status": status.value})


@router.websocket("/ws")
@router.websocket("/api/v1/ws")
async def ws_relay(websocket: WebSocket) -> None:
    """WebSocket relay: ThingsBoard -> Lextari API -> Flutter.

    The Flutter client authenticates with a first message::

        {"type": "auth", "token": "<supabase_jwt>"}

    The server replies ``{"type": "auth_ok"}`` and auto-subscribes to the
    user's first linked device. The legacy query-param auth and explicit
    ``subscribe`` message remain supported for existing clients.
    """
    scope = websocket.scope
    settings = get_settings_from_scope(scope)
    db = get_db_from_scope(scope)
    await websocket.accept()

    auth = await _read_token(websocket)
    if auth is None:
        await websocket.close(code=4001, reason="Missing token")
        return
    token, token_from_message = auth

    try:
        user = await verify_supabase_token(token, settings.jwks_url, settings.supabase_url)
    except Exception:
        await websocket.close(code=4003, reason="Invalid token")
        return

    if token_from_message:
        await websocket.send_json({"type": "auth_ok"})

    relay = _RelayConnection(websocket, _make_tb_client(settings), settings.ws_poll_interval)
    await relay.attach(await _resolve_device_id(user["sub"], db))
    relay.start()

    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            if data.get("type") == "ping":
                await relay.send({"type": "pong"})
            elif data.get("type") == "subscribe":
                device_id = data.get("device_id")
                if isinstance(device_id, str) and device_id:
                    await relay.switch(device_id)
    except WebSocketDisconnect:
        pass
    finally:
        await relay.stop()
