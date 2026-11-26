"""Helpers for resolving and grouping a user's linked devices."""

from typing import Any

from app.db.d1 import query_all
from app.db.models import UserDevice
from app.utils.errors import DeviceNotFoundError

ENVIRONMENT_ROLE = "env"
WATER_ROLE = "water"

_WATER_HINTS = ("water", "refill", "solenoid", "tank")
_ENVIRONMENT_HINTS = ("env", "sensor", "environment", "plant")


def device_role(device: UserDevice) -> str:
    """Return the functional role of a linked device.

    Roles come from the stored device type when the link flow sets one.
    Older rows fall back to the device name so existing mappings keep working.
    """
    text = f"{device.device_type} {device.device_name}".lower()
    if any(hint in text for hint in _WATER_HINTS):
        return WATER_ROLE
    if any(hint in text for hint in _ENVIRONMENT_HINTS):
        return ENVIRONMENT_ROLE
    return ENVIRONMENT_ROLE


def select_rpc_device(devices: list[UserDevice], method: str) -> UserDevice:
    """Pick the linked device that owns an RPC command."""
    wants_water = "refill" in method.lower()
    target_role = WATER_ROLE if wants_water else ENVIRONMENT_ROLE
    for device in devices:
        if device_role(device) == target_role:
            return device
    return devices[0]


async def resolve_user_devices(user_id: str, db: Any) -> list[UserDevice]:
    """Return every device linked to ``user_id`` in link order."""
    rows = await query_all(
        db,
        "SELECT id, user_id, favoriot_device_id, device_name, device_type, mac_address, created_at "
        "FROM user_devices WHERE user_id = ? ORDER BY id",
        [user_id],
    )
    if not rows:
        raise DeviceNotFoundError
    return [UserDevice.from_row(row) for row in rows]


async def resolve_user_device(user_id: str, db: Any) -> UserDevice:
    """Return the first device linked to ``user_id``.

    Kept for single-device callers; new callers should resolve every device.
    """
    devices = await resolve_user_devices(user_id, db)
    return devices[0]
