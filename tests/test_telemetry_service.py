"""Telemetry merge tests for the dual-device setup."""

from typing import Any

import pytest

from app.db.models import UserDevice
from app.services.telemetry import (
    fill_snapshot_gaps_from_history,
    read_latest_snapshot_with_timestamps,
)


def _device(device_id: str, name: str, device_type: str) -> UserDevice:
    return UserDevice(
        id=1,
        user_id="user-1",
        favoriot_device_id=device_id,
        device_name=name,
        device_type=device_type,
        mac_address=None,
        created_at=0,
    )


class _FakeFavorIoT:
    def __init__(
        self,
        latest: dict[str, dict[str, tuple[float, int]]],
        history: dict[str, list[dict[str, float]]] | None = None,
    ) -> None:
        self._latest = latest
        self._history = history or {}

    async def get_latest_readings(
        self, device_id: str, keys: list[str]
    ) -> dict[str, tuple[float, int]]:
        return self._latest.get(device_id, {})

    async def get_telemetry_history(
        self,
        device_id: str,
        keys: list[str],
        start_ts_ms: int,
        end_ts_ms: int,
        agg: str = "AVG",
        interval_ms: int = 3_600_000,
        limit: int = 10_000,
    ) -> dict[str, list[dict[str, Any]]]:
        return self._history


@pytest.mark.asyncio
async def test_newest_reading_wins_across_devices() -> None:
    """A stale non-owner device cannot mask a newer owner reading."""
    environment = _device("env@device", "Lextari Environment", "lextari-env")
    water = _device("water@device", "Lextari Water", "lextari-water")
    favoriot = _FakeFavorIoT(
        {
            environment.favoriot_device_id: {
                "soil_moisture": (0.0, 200),
                "temperature": (23.5, 200),
            },
            water.favoriot_device_id: {
                "soil_moisture": (59.0, 100),
                "water_level": (409.0, 100),
            },
        }
    )

    snapshot = await read_latest_snapshot_with_timestamps(
        favoriot,  # type: ignore[arg-type]
        [environment, water],
        keys=("soil_moisture", "temperature", "water_level"),
    )

    assert snapshot["soil_moisture"] == (0.0, 200)
    assert snapshot["temperature"] == (23.5, 200)
    assert snapshot["water_level"] == (409.0, 100)


@pytest.mark.asyncio
async def test_role_owner_breaks_a_timestamp_tie() -> None:
    environment = _device("env@device", "Lextari Environment", "lextari-env")
    water = _device("water@device", "Lextari Water", "lextari-water")
    favoriot = _FakeFavorIoT(
        {
            environment.favoriot_device_id: {"soil_moisture": (0.0, 200)},
            water.favoriot_device_id: {"soil_moisture": (59.0, 200)},
        }
    )

    snapshot = await read_latest_snapshot_with_timestamps(
        favoriot,  # type: ignore[arg-type]
        [water, environment],
        keys=("soil_moisture",),
    )

    assert snapshot["soil_moisture"] == (0.0, 200)


@pytest.mark.asyncio
async def test_missing_readings_fall_back_to_history() -> None:
    environment = _device("env@device", "Lextari Environment", "lextari-env")
    favoriot = _FakeFavorIoT(
        {},
        history={"temperature": [{"ts": 100, "value": 22.0}]},
    )

    snapshot = await read_latest_snapshot_with_timestamps(
        favoriot,  # type: ignore[arg-type]
        [environment],
        keys=("temperature",),
    )
    await fill_snapshot_gaps_from_history(
        favoriot,  # type: ignore[arg-type]
        [environment],
        snapshot,
        keys=("temperature",),
    )

    assert snapshot["temperature"] == (22.0, 100)
