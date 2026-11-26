"""Telemetry helpers that combine readings from every linked device."""

import asyncio
from typing import Any

from app.clients.favoriot import FavorIoTClient
from app.db.models import UserDevice
from app.services.devices import (
    ENVIRONMENT_ROLE,
    WATER_ROLE,
    device_role,
)

SENSOR_KEYS = ("soil_moisture", "temperature", "humidity", "water_level")
ENVIRONMENT_KEYS = {"soil_moisture", "temperature", "humidity"}
WATER_KEYS = {"water_level"}


def preferred_role_for_key(key: str) -> str:
    """Return the device role that owns a telemetry key."""
    return WATER_ROLE if key in WATER_KEYS else ENVIRONMENT_ROLE


def _preferred_snapshot_for_key(
    pairs: list[tuple[UserDevice, dict[str, float]]],
    key: str,
) -> dict[str, float] | None:
    preferred = preferred_role_for_key(key)
    for device, snapshot in pairs:
        if key in snapshot and device_role(device) == preferred:
            return snapshot
    for _, snapshot in pairs:
        if key in snapshot:
            return snapshot
    return None


async def read_latest_snapshot(
    favoriot: FavorIoTClient,
    devices: list[UserDevice],
    keys: tuple[str, ...] = SENSOR_KEYS,
) -> dict[str, float]:
    """Read the newest value for each key across every linked device.

    The environment device owns soil, temperature and humidity. The water
    device owns water level. A key missing from its owning role falls back to
    any other linked device so older single-device mappings still work.
    """
    snapshots = await asyncio.gather(
        *(
            favoriot.get_latest_telemetry(device.favoriot_device_id, keys=list(keys))
            for device in devices
        )
    )
    pairs = list(zip(devices, snapshots, strict=True))
    merged: dict[str, float] = {}
    for key in keys:
        snapshot = _preferred_snapshot_for_key(pairs, key)
        if snapshot is not None and key in snapshot:
            merged[key] = float(snapshot[key])
    return merged


async def read_history_for_key(
    favoriot: FavorIoTClient,
    devices: list[UserDevice],
    key: str,
    start_ts_ms: int,
    end_ts_ms: int,
    interval_ms: int = 3_600_000,
) -> list[dict[str, float]]:
    """Return history for a key from the device that owns it."""
    preferred = preferred_role_for_key(key)
    ordered = sorted(devices, key=lambda device: 0 if device_role(device) == preferred else 1)
    for device in ordered:
        data: dict[str, Any] = await favoriot.get_telemetry_history(
            device.favoriot_device_id,
            keys=[key],
            start_ts_ms=start_ts_ms,
            end_ts_ms=end_ts_ms,
            agg="AVG",
            interval_ms=interval_ms,
        )
        points: list[dict[str, float]] = data.get(key, [])
        if points:
            return points
    return []
