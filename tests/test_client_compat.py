"""Tests for the device-agnostic routes used by the Flutter app."""

import pytest
from httpx import AsyncClient

from app.auth.dependencies import get_current_user
from app.clients.favoriot import get_favoriot_client
from app.db.d1 import get_db
from app.main import app
from tests.fakes import FakeD1, FakeFavorIoT

DEVICE_ROW = {
    "id": 1,
    "user_id": "test-user-id",
    "favoriot_device_id": "Agrilink_1_device@anwarzain",
    "device_name": "Living Room",
    "device_type": "lextari-env",
    "mac_address": None,
    "created_at": 0,
}


def _override(db: FakeD1, favoriot: FakeFavorIoT) -> None:
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test-user-id"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_favoriot_client] = lambda: favoriot


@pytest.mark.asyncio
async def test_rpc_resolves_first_device(client: AsyncClient) -> None:
    """POST /api/rpc forwards to the user's first linked device."""
    favoriot = FakeFavorIoT()
    _override(FakeD1([DEVICE_ROW]), favoriot)

    try:
        resp = await client.post(
            "/api/rpc",
            json={"method": "triggerWatering"},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["sent"] is True
        assert favoriot.command_calls == [("Agrilink_1_device@anwarzain", "triggerWatering", None)]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_telemetry_key_history(client: AsyncClient) -> None:
    """GET /api/telemetry/{key} returns chart points for a sensor key."""
    favoriot = FakeFavorIoT()
    favoriot.history = {"temperature": [{"ts": 1735689600000, "value": "22.5"}]}
    _override(FakeD1([DEVICE_ROW]), favoriot)

    try:
        resp = await client.get(
            "/api/telemetry/temperature?days=7",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "key": "temperature",
            "unit": "°C",
            "points": [{"ts": 1735689600000, "value": 22.5}],
        }
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_telemetry_rejects_unknown_key(client: AsyncClient) -> None:
    """Unknown sensor keys return 404 without touching FavorIoT."""
    favoriot = FakeFavorIoT()
    _override(FakeD1([DEVICE_ROW]), favoriot)

    try:
        resp = await client.get(
            "/api/telemetry/pressure",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 404
        assert favoriot.history_calls == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_device_list_shape(client: AsyncClient) -> None:
    """GET /api/devices uses the Flutter-facing payload shape."""
    _override(FakeD1([DEVICE_ROW]), FakeFavorIoT())

    try:
        resp = await client.get(
            "/api/devices",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "devices": [
                {
                    "platform_device_id": "Agrilink_1_device@anwarzain",
                    "device_name": "Living Room",
                    "device_type": "lextari-env",
                }
            ]
        }
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_score_for_user(client: AsyncClient) -> None:
    """GET /api/health-score resolves the user's device and returns GHS."""
    favoriot = FakeFavorIoT()
    favoriot.latest = {
        "soil_moisture": 55.0,
        "temperature": 23.0,
        "humidity": 65.0,
    }
    _override(FakeD1([DEVICE_ROW]), favoriot)

    try:
        resp = await client.get(
            "/api/health-score",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] >= 80
        assert data["status"] == "Optimal"
        assert set(data["component_scores"]) == {
            "soil_moisture",
            "temperature",
            "humidity",
        }
    finally:
        app.dependency_overrides.clear()
