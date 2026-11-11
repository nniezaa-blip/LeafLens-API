"""Row models for D1 records."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class UserDevice:
    """Maps a Supabase user to a ThingsBoard device."""

    id: int
    user_id: str
    tb_device_id: str
    device_name: str
    device_type: str
    mac_address: str | None
    created_at: int

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "UserDevice":
        """Build a device from a D1 row."""
        return cls(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            tb_device_id=str(row["tb_device_id"]),
            device_name=str(row["device_name"]),
            device_type=str(row.get("device_type") or "lextari-env"),
            mac_address=row.get("mac_address"),
            created_at=int(row.get("created_at") or 0),
        )
