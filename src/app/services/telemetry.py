"""Telemetry helpers that combine readings from every linked device."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
HISTORY_LOOKBACK_DAYS = 90
RECONCILE_STALE_AFTER_MS = 3_600_000


@dataclass(frozen=True)
class SnapshotReading:
    """Newest reading for one sensor and the device that recorded it."""

    value: float
    recorded_at_ms: int
    device_id: str
    device_name: str


def preferred_role_for_key(key: str) -> str:
    """Return the device role that owns a telemetry key."""
    return WATER_ROLE if key in WATER_KEYS else ENVIRONMENT_ROLE


def _newest_reading_for_key(
    pairs: list[tuple[UserDevice, dict[str, tuple[float, int]]]],
    key: str,
) -> SnapshotReading | None:
    """Return the newest reading for ``key`` and the device that sent it.

    The role owner wins only when timestamps tie, so a device that stopped
    publishing cannot mask a newer reading from another linked device.
    """
    preferred = preferred_role_for_key(key)
    best: tuple[bool, int, SnapshotReading] | None = None
    for device, snapshot in pairs:
        reading = snapshot.get(key)
        if reading is None:
            continue
        value, recorded_at_ms = reading
        candidate = (
            device_role(device) == preferred,
            recorded_at_ms,
            SnapshotReading(
                value=value,
                recorded_at_ms=recorded_at_ms,
                device_id=device.favoriot_device_id,
                device_name=device.device_name,
            ),
        )
        if best is None:
            best = candidate
            continue
        is_preferred, timestamp, _ = candidate
        best_preferred, best_timestamp, _ = best
        if timestamp > best_timestamp or (
            timestamp == best_timestamp and is_preferred and not best_preferred
        ):
            best = candidate
    return best[2] if best is not None else None


async def read_latest_snapshot_with_timestamps(
    favoriot: FavorIoTClient,
    devices: list[UserDevice],
    keys: tuple[str, ...] = SENSOR_KEYS,
) -> dict[str, SnapshotReading]:
    """Read the newest value, timestamp and source for every sensor key.

    The newest recorded timestamp wins. The environment device owns soil,
    temperature and humidity, and the water device owns water level, so the
    role owner breaks a tie between identical timestamps.
    """
    snapshots = await asyncio.gather(
        *(
            favoriot.get_latest_readings(device.favoriot_device_id, keys=list(keys))
            for device in devices
        )
    )
    pairs = list(zip(devices, snapshots, strict=True))
    merged: dict[str, SnapshotReading] = {}
    for key in keys:
        reading = _newest_reading_for_key(pairs, key)
        if reading is not None:
            merged[key] = reading
    return merged


async def read_latest_snapshot(
    favoriot: FavorIoTClient,
    devices: list[UserDevice],
    keys: tuple[str, ...] = SENSOR_KEYS,
) -> dict[str, float]:
    """Read the newest value for each key across every linked device."""
    snapshot = await read_latest_snapshot_with_timestamps(favoriot, devices, keys)
    return {key: reading.value for key, reading in snapshot.items()}


async def reconcile_snapshot_with_history(
    favoriot: FavorIoTClient,
    devices: list[UserDevice],
    snapshot: dict[str, SnapshotReading],
    keys: tuple[str, ...] = SENSOR_KEYS,
    lookback_days: int = HISTORY_LOOKBACK_DAYS,
) -> None:
    """Keep the newest reading per key across live streams and history.

    A stopped device keeps its last stored values, while another device or an
    hourly history bucket can hold a newer reading for the same sensor. The
    newer reading replaces the older one and carries its source device.
    """
    if not devices:
        return
    now = datetime.now(UTC)
    end = now
    start = end - timedelta(days=max(lookback_days, 1))
    stale_before_ms = int(now.timestamp() * 1000) - RECONCILE_STALE_AFTER_MS
    stale_keys = [
        key
        for key in keys
        if key not in snapshot or snapshot[key].recorded_at_ms < stale_before_ms
    ]
    for key in stale_keys:
        history = await read_history_for_key_with_device(
            favoriot,
            devices,
            key,
            start_ts_ms=int(start.timestamp() * 1000),
            end_ts_ms=int(end.timestamp() * 1000),
        )
        if history is None:
            continue
        device, points = history
        if not points:
            continue
        newest = points[-1]
        recorded_at_ms = int(newest["ts"])
        current = snapshot.get(key)
        if current is not None and current.recorded_at_ms >= recorded_at_ms:
            continue
        snapshot[key] = SnapshotReading(
            value=float(newest["value"]),
            recorded_at_ms=recorded_at_ms,
            device_id=device.favoriot_device_id,
            device_name=device.device_name,
        )


async def read_history_for_key_with_device(
    favoriot: FavorIoTClient,
    devices: list[UserDevice],
    key: str,
    start_ts_ms: int,
    end_ts_ms: int,
    interval_ms: int = 3_600_000,
) -> tuple[UserDevice, list[dict[str, float]]] | None:
    """Return the source device and history points for a key."""
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
            return device, points
    return None


async def read_history_for_key(
    favoriot: FavorIoTClient,
    devices: list[UserDevice],
    key: str,
    start_ts_ms: int,
    end_ts_ms: int,
    interval_ms: int = 3_600_000,
) -> list[dict[str, float]]:
    """Return history for a key from the device that owns it."""
    history = await read_history_for_key_with_device(
        favoriot,
        devices,
        key,
        start_ts_ms=start_ts_ms,
        end_ts_ms=end_ts_ms,
        interval_ms=interval_ms,
    )
    return history[1] if history is not None else []
