"""Telemetry endpoints - latest and historical data."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_user
from app.clients.thingsboard import ThingsBoardClient, get_tb_client
from app.db.d1 import get_db
from app.services.devices import resolve_user_device

router = APIRouter()

_SENSOR_UNITS: dict[str, str] = {
    "soil_moisture": "%",
    "temperature": "°C",
    "humidity": "%",
    "water_level": "%",
}


@router.get("/api/v1/telemetry/{device_id}/latest")
async def get_latest_telemetry(
    device_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    tb: ThingsBoardClient = Depends(get_tb_client),
) -> dict[str, object]:
    """Latest sensor readings for dashboard tiles."""
    data = await tb.get_latest_telemetry(
        device_id,
        keys=["soil_moisture", "temperature", "humidity", "water_level"],
    )
    return {"device_id": device_id, "readings": data}


@router.get("/api/v1/telemetry/{device_id}/history")
async def get_telemetry_history(
    device_id: str,
    days: int = Query(default=30, ge=1, le=90),
    user: dict[str, Any] = Depends(get_current_user),
    tb: ThingsBoardClient = Depends(get_tb_client),
) -> dict[str, object]:
    """30-day historical telemetry for trend charts.

    Uses 1-hour AVG aggregation - 720 points per key, well within limits.
    """
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    data = await tb.get_telemetry_history(
        device_id,
        keys=["soil_moisture", "temperature", "humidity"],
        start_ts_ms=int(start.timestamp() * 1000),
        end_ts_ms=int(end.timestamp() * 1000),
        agg="AVG",
        interval_ms=3_600_000,
    )
    return {"device_id": device_id, "history": data}


@router.get("/api/telemetry/{key}")
async def get_telemetry_for_key(
    key: str,
    days: int = Query(default=30, ge=1, le=90),
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
    tb: ThingsBoardClient = Depends(get_tb_client),
) -> dict[str, object]:
    """Per-key telemetry history for the Flutter trend charts.

    Resolves the authenticated user's first linked device so the client does
    not need to know ThingsBoard device IDs.
    """
    if key not in _SENSOR_UNITS:
        raise HTTPException(status_code=404, detail=f"Unknown sensor key: {key}")

    device = await resolve_user_device(user["sub"], db)
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    data = await tb.get_telemetry_history(
        device.tb_device_id,
        keys=[key],
        start_ts_ms=int(start.timestamp() * 1000),
        end_ts_ms=int(end.timestamp() * 1000),
        agg="AVG",
        interval_ms=3_600_000,
    )

    points = [
        {"ts": int(entry["ts"]), "value": float(entry["value"])} for entry in data.get(key, [])
    ]
    return {"key": key, "unit": _SENSOR_UNITS[key], "points": points}
