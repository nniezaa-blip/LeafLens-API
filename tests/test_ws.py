"""WebSocket contract tests for the Flutter client."""

from fastapi.testclient import TestClient

from app.main import app
from app.routers import ws as ws_router
from tests.fakes import FakeFavorIoT


def test_ws_first_message_auth_and_initial_snapshot(monkeypatch) -> None:
    """The Flutter client gets auth_ok then camelCase telemetry and GHS."""
    favoriot = FakeFavorIoT()
    favoriot.latest = {
        "soil_moisture": 55.0,
        "temperature": 23.0,
        "humidity": 65.0,
    }

    async def verify(*args: object, **kwargs: object) -> dict[str, str]:
        return {"sub": "user-1"}

    async def resolve_device(user_id: str, db: object) -> str:
        return "Agrilink_1_device@anwarzain"

    monkeypatch.setattr(ws_router, "verify_access_token", verify)
    monkeypatch.setattr(ws_router, "_resolve_device_id", resolve_device)
    monkeypatch.setattr(ws_router, "_make_favoriot_client", lambda settings: favoriot)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "jwt"})
        assert websocket.receive_json() == {"type": "auth_ok"}

        telemetry = websocket.receive_json()
        assert telemetry == {
            "type": "telemetry",
            "soilMoisture": 55.0,
            "temperature": 23.0,
            "humidity": 65.0,
        }

        ghs = websocket.receive_json()
        assert ghs == {"type": "ghs", "score": 100.0, "status": "Optimal"}
