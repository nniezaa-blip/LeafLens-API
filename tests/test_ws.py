"""WebSocket contract tests for the Flutter client."""

from fastapi.testclient import TestClient

from app.db.models import UserDevice
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

    async def resolve_devices(user_id: str, db: object) -> list[UserDevice]:
        return [
            UserDevice(
                id=1,
                user_id=user_id,
                favoriot_device_id="Agrilink_1_device@anwarzain",
                device_name="Lextari Environment",
                device_type="lextari-env",
                mac_address=None,
                created_at=0,
            )
        ]

    monkeypatch.setattr(ws_router, "verify_access_token", verify)
    monkeypatch.setattr(ws_router, "_resolve_devices", resolve_devices)
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
            "recordedAt": {
                "soilMoisture": FakeFavorIoT.default_reading_ts,
                "temperature": FakeFavorIoT.default_reading_ts,
                "humidity": FakeFavorIoT.default_reading_ts,
            },
            "source": {
                "soilMoisture": "Lextari Environment",
                "temperature": "Lextari Environment",
                "humidity": "Lextari Environment",
            },
        }

        ghs = websocket.receive_json()
        assert ghs == {"type": "ghs", "score": 100.0, "status": "Optimal"}


def test_ws_initial_snapshot_falls_back_to_last_known(monkeypatch) -> None:
    """Every missing sensor falls back to its newest history point."""
    favoriot = FakeFavorIoT()
    favoriot.history = {
        "soil_moisture": [{"ts": 1_792_114_890_241, "value": 59.0}],
        "temperature": [{"ts": 1_792_114_890_241, "value": 22.0}],
        "humidity": [{"ts": 1_792_114_890_241, "value": 73.0}],
        "water_level": [{"ts": 1_792_114_890_241, "value": 409.0}],
    }

    async def verify(*args: object, **kwargs: object) -> dict[str, str]:
        return {"sub": "user-1"}

    async def resolve_devices(user_id: str, db: object) -> list[UserDevice]:
        return [
            UserDevice(
                id=1,
                user_id=user_id,
                favoriot_device_id="Agrilink_1_device@anwarzain",
                device_name="Lextari Environment",
                device_type="lextari-env",
                mac_address=None,
                created_at=0,
            )
        ]

    monkeypatch.setattr(ws_router, "verify_access_token", verify)
    monkeypatch.setattr(ws_router, "_resolve_devices", resolve_devices)
    monkeypatch.setattr(ws_router, "_make_favoriot_client", lambda settings: favoriot)

    client = TestClient(app)
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"type": "auth", "token": "jwt"})
        assert websocket.receive_json() == {"type": "auth_ok"}

        telemetry = websocket.receive_json()
        assert telemetry == {
            "type": "telemetry",
            "soilMoisture": 59.0,
            "temperature": 22.0,
            "humidity": 73.0,
            "waterLevel": 409.0,
            "recordedAt": {
                "soilMoisture": 1_792_114_890_241,
                "temperature": 1_792_114_890_241,
                "humidity": 1_792_114_890_241,
                "waterLevel": 1_792_114_890_241,
            },
            "source": {
                "soilMoisture": "Lextari Environment",
                "temperature": "Lextari Environment",
                "humidity": "Lextari Environment",
                "waterLevel": "Lextari Environment",
            },
        }

        ghs = websocket.receive_json()
        assert ghs["type"] == "ghs"
