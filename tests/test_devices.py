"""Device endpoint tests."""

import pytest
from httpx import AsyncClient

from app.auth.dependencies import get_current_user
from app.clients.favoriot import get_favoriot_client
from app.db.d1 import get_db
from app.main import app
from tests.fakes import FakeD1, FakeFavorIoT


@pytest.mark.asyncio
async def test_list_devices_empty(client: AsyncClient) -> None:
    """Empty device list returns 200 with proper dependency overrides."""
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-id",
        "email": "test@test.com",
    }
    app.dependency_overrides[get_db] = lambda: FakeD1([])
    app.dependency_overrides[get_favoriot_client] = FakeFavorIoT

    try:
        resp = await client.get(
            "/api/v1/devices",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_device_uses_authenticated_user(client: AsyncClient) -> None:
    """A client-supplied user_id must not override the JWT subject."""
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "jwt-user-id",
        "email": "test@test.com",
    }
    fake_db = FakeD1([])
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_favoriot_client] = FakeFavorIoT

    try:
        resp = await client.post(
            "/api/v1/devices/register",
            headers={"Authorization": "Bearer fake-token"},
            json={
                "mac_address": "AA:BB:CC:DD:EE:01",
                "user_id": "spoofed-user-id",
                "device_name": "Lextari Demo",
            },
        )
        assert resp.status_code == 200
        assert fake_db.executed
        assert fake_db.executed[0][1][0] == "jwt-user-id"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_device_inserts_mapping(client: AsyncClient) -> None:
    """Linking an existing FavorIoT device stores the authenticated user mapping."""
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-id",
        "email": "test@test.com",
    }
    fake_db = FakeD1([])
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_favoriot_client] = FakeFavorIoT

    try:
        resp = await client.post(
            "/api/v1/devices/link",
            headers={"Authorization": "Bearer fake-token"},
            json={
                "device_developer_id": "Agrilink_1_device@anwarzain",
                "device_name": "My Lextari",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "platform_device_id": "Agrilink_1_device@anwarzain",
            "device_name": "My Lextari",
            "device_type": "lextari-env",
        }
        assert fake_db.executed
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_link_device_rejects_other_users_device(client: AsyncClient) -> None:
    """A device already mapped to another user cannot be linked again."""
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user-id",
        "email": "test@test.com",
    }
    app.dependency_overrides[get_db] = lambda: FakeD1(
        [
            {
                "id": 1,
                "user_id": "another-user-id",
                "favoriot_device_id": "Agrilink_1_device@anwarzain",
                "device_name": "Another Lextari",
                "device_type": "sensor",
                "mac_address": None,
                "created_at": 0,
            }
        ]
    )
    app.dependency_overrides[get_favoriot_client] = FakeFavorIoT

    try:
        resp = await client.post(
            "/api/v1/devices/link",
            headers={"Authorization": "Bearer fake-token"},
            json={"device_developer_id": "Agrilink_1_device@anwarzain"},
        )
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()
