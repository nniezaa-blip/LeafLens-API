"""Helpers for resolving a user's linked device."""

from typing import Any

from app.db.d1 import query_first
from app.db.models import UserDevice
from app.utils.errors import DeviceNotFoundError


async def resolve_user_device(user_id: str, db: Any) -> UserDevice:
    """Return the first device linked to ``user_id``.

    Raises ``DeviceNotFoundError`` when the user has no linked device.
    """
    row = await query_first(
        db,
        "SELECT id, user_id, tb_device_id, device_name, device_type, mac_address, created_at "
        "FROM user_devices WHERE user_id = ? ORDER BY id LIMIT 1",
        [user_id],
    )
    if row is None:
        raise DeviceNotFoundError
    return UserDevice.from_row(row)
