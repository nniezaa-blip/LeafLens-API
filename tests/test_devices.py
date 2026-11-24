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
