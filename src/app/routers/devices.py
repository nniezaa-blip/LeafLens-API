"""Device management endpoints."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.clients.favoriot import FavorIoTClient, get_favoriot_client
from app.db.d1 import execute, get_db, query_all, query_first
from app.db.models import UserDevice
from app.schemas.requests import DeviceLinkRequest, DeviceRegisterRequest
from app.schemas.responses import DeviceResponse, LinkedDeviceResponse

router = APIRouter()

_TELEMETRY_KEYS = ["soil_moisture", "temperature", "humidity", "water_level"]


async def _read_latest(favoriot: FavorIoTClient, device_id: str) -> dict[str, float] | None:
    """Read latest telemetry for a device without failing the whole list."""
    try:
        telemetry = await favoriot.get_latest_telemetry(device_id, keys=_TELEMETRY_KEYS)
    except Exception:
        return None
    return {key: telemetry[key] for key in _TELEMETRY_KEYS if key in telemetry}


@router.post("/api/v1/devices/register")
async def register_device(
    body: DeviceRegisterRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    favoriot: FavorIoTClient = Depends(get_favoriot_client),
    db: Any = Depends(get_db),
) -> dict[str, str]:
    """Register a new ESP32 device after BLE onboarding.

    Creates the FavorIoT device, saves the mapping, and returns its access token.
    """
    user_id = str(current_user["sub"])
    favoriot_device = await favoriot.create_device(name=body.device_name, device_type="sensor")
    platform_device_id = str(favoriot_device["device_developer_id"])
    device_access_token = str(favoriot_device.get("accesstoken") or "")

    await execute(
        db,
        "INSERT INTO user_devices (user_id, favoriot_device_id, device_name, mac_address) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(favoriot_device_id) DO UPDATE SET "
        "user_id = excluded.user_id, device_name = excluded.device_name, "
        "mac_address = excluded.mac_address",
        (user_id, platform_device_id, body.device_name, body.mac_address),
    )

    return {
        "device_access_token": device_access_token,
        "device_id": platform_device_id,
    }


def _infer_device_type(device_id: str, device_name: str) -> str:
    text = f"{device_id} {device_name}".lower()
    if any(hint in text for hint in ("water", "refill", "solenoid", "tank")):
        return "lextari-water"
    return "lextari-env"


@router.post("/api/v1/devices/link", response_model=LinkedDeviceResponse)
async def link_device(
    body: DeviceLinkRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    favoriot: FavorIoTClient = Depends(get_favoriot_client),
    db: Any = Depends(get_db),
) -> LinkedDeviceResponse:
    """Link an existing FavorIoT device to the authenticated user."""
    user_id = str(current_user["sub"])
    device_id = (body.platform_device_id or body.device_developer_id or "").strip()
    if not device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="platform_device_id is required",
        )

    favoriot_devices = await favoriot.list_devices()
    matching = [
        device
        for device in favoriot_devices
        if str(device.get("device_developer_id")) == device_id
    ]
    if not matching:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FavorIoT device not found",
        )

    favoriot_device = matching[0]
    device_name = body.device_name or str(favoriot_device.get("device_name") or device_id)
    device_type = body.device_type or _infer_device_type(device_id, device_name)

    existing = await query_first(
        db,
        "SELECT * FROM user_devices WHERE favoriot_device_id = ?",
        [device_id],
    )
    if existing is not None:
        if str(existing["user_id"]) != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Device is already linked to another user",
            )
        return LinkedDeviceResponse(
            platform_device_id=device_id,
            device_name=str(existing["device_name"]),
            device_type=str(existing["device_type"]),
        )

    await execute(
        db,
        "INSERT INTO user_devices (user_id, favoriot_device_id, device_name, device_type) "
        "VALUES (?, ?, ?, ?)",
        (user_id, device_id, device_name, device_type),
    )
    return LinkedDeviceResponse(
        platform_device_id=device_id,
        device_name=device_name,
        device_type=device_type,
    )


@router.get("/api/v1/devices", response_model=list[DeviceResponse])
async def list_devices(
    current_user: dict[str, Any] = Depends(get_current_user),
    favoriot: FavorIoTClient = Depends(get_favoriot_client),
    db: Any = Depends(get_db),
) -> list[DeviceResponse]:
    """List devices linked to the current user."""
    user_id = str(current_user["sub"])
    rows = await query_all(
        db,
        "SELECT * FROM user_devices WHERE user_id = ? ORDER BY created_at ASC",
        [user_id],
    )
    devices = [UserDevice.from_row(row) for row in rows]
    if not devices:
        return []

    telemetry_rows = await asyncio.gather(
        *(_read_latest(favoriot, device.favoriot_device_id) for device in devices)
    )
    return [
        DeviceResponse(
            id=device.id,
            favoriot_device_id=device.favoriot_device_id,
            device_name=device.device_name,
            device_type=device.device_type,
            latest_readings=latest,
        )
        for device, latest in zip(devices, telemetry_rows, strict=True)
    ]


@router.get("/api/devices")
async def list_devices_compat(
    current_user: dict[str, Any] = Depends(get_current_user),
    favoriot: FavorIoTClient = Depends(get_favoriot_client),
    db: Any = Depends(get_db),
) -> dict[str, list[dict[str, str]]]:
    """Compatibility device list for current Flutter client."""
    devices = await list_devices(current_user=current_user, favoriot=favoriot, db=db)
    return {
        "devices": [
            {
                "platform_device_id": device.favoriot_device_id,
                "device_name": device.device_name,
                "device_type": device.device_type,
            }
            for device in devices
        ]
    }


@router.get("/api/v1/devices/{device_id}")
async def get_device(
    device_id: str,
    _current_user: dict[str, Any] = Depends(get_current_user),
    favoriot: FavorIoTClient = Depends(get_favoriot_client),
) -> dict[str, Any]:
    """Get FavorIoT device details by platform device ID."""
    return await favoriot.get_device(device_id)
