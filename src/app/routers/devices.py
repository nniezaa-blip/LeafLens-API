"""Device management endpoints."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.clients.thingsboard import ThingsBoardClient, get_tb_client
from app.db.d1 import execute, get_db, query_all, query_first
from app.db.models import UserDevice
from app.schemas.requests import DeviceRegisterRequest
from app.schemas.responses import DeviceResponse

router = APIRouter()

_TELEMETRY_KEYS = ["soil_moisture", "temperature", "humidity", "water_level"]


@router.post("/api/v1/devices/register")
async def register_device(
    body: DeviceRegisterRequest,
    tb: ThingsBoardClient = Depends(get_tb_client),
    db: Any = Depends(get_db),
) -> dict[str, str]:
    """Register a new ESP32 device after BLE onboarding.

    Creates the TB device, saves the mapping, and returns the TB access token.
    """
    tb_device = await tb.create_device(name=body.device_name, device_type="sensor")
    tb_device_id: str = tb_device["id"]["id"]

    creds = await tb.get_device_credentials(tb_device_id)
    access_token: str = creds["credentialsId"]

    await execute(
        db,
        "INSERT INTO user_devices (user_id, tb_device_id, device_name, mac_address) "
        "VALUES (?, ?, ?, ?)",
        [body.user_id, tb_device_id, body.device_name, body.mac_address],
    )

    return {"thingsboard_token": access_token, "device_id": tb_device_id}


@router.get("/api/v1/devices", response_model=list[DeviceResponse])
async def list_devices(
    user: dict[str, Any] = Depends(get_current_user),
    tb: ThingsBoardClient = Depends(get_tb_client),
    db: Any = Depends(get_db),
) -> list[DeviceResponse]:
    """List all devices belonging to the current user, with latest telemetry."""
    rows = await query_all(
        db,
        "SELECT id, user_id, tb_device_id, device_name, device_type, mac_address, created_at "
        "FROM user_devices WHERE user_id = ?",
        [user["sub"]],
    )
    devices = [UserDevice.from_row(row) for row in rows]

    tasks = [tb.get_latest_telemetry(device.tb_device_id, _TELEMETRY_KEYS) for device in devices]
    readings = await asyncio.gather(*tasks, return_exceptions=True)

    response: list[DeviceResponse] = []
    for device, reading in zip(devices, readings, strict=True):
        latest = (
            {key: float(value) for key, value in reading.items()}
            if isinstance(reading, dict)
            else None
        )
        response.append(
            DeviceResponse(
                id=device.id,
                tb_device_id=device.tb_device_id,
                device_name=device.device_name,
                device_type=device.device_type,
                latest_readings=latest,
            )
        )
    return response


@router.get("/api/devices")
async def list_devices_for_user(
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict[str, object]:
    """Device list in the shape defined by the Flutter backend schema."""
    rows = await query_all(
        db,
        "SELECT id, user_id, tb_device_id, device_name, device_type, mac_address, created_at "
        "FROM user_devices WHERE user_id = ? ORDER BY id",
        [user["sub"]],
    )
    return {
        "devices": [
            {
                "platform_device_id": device.tb_device_id,
                "device_name": device.device_name,
                "device_type": device.device_type,
            }
            for device in (UserDevice.from_row(row) for row in rows)
        ]
    }


@router.get("/api/v1/devices/{device_id}")
async def get_device(
    device_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    tb: ThingsBoardClient = Depends(get_tb_client),
    db: Any = Depends(get_db),
) -> dict[str, object]:
    """Get single device details plus latest telemetry."""
    row = await query_first(
        db,
        "SELECT id, user_id, tb_device_id, device_name, device_type, mac_address, created_at "
        "FROM user_devices WHERE tb_device_id = ? AND user_id = ? LIMIT 1",
        [device_id, user["sub"]],
    )
    if row is None:
        return {"error": "Device not found"}

    device = UserDevice.from_row(row)
    readings = await tb.get_latest_telemetry(device_id, _TELEMETRY_KEYS)
    return {
        "id": device.id,
        "tb_device_id": device.tb_device_id,
        "device_name": device.device_name,
        "device_type": device.device_type,
        "latest_readings": readings,
    }
