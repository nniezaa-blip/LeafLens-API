"""Request body models."""

from pydantic import BaseModel


class DeviceRegisterRequest(BaseModel):
    """ESP32 device registration payload.

    ``user_id`` remains accepted for older clients but the authenticated JWT
    subject is authoritative.
    """

    mac_address: str
    user_id: str | None = None
    device_name: str


class DeviceLinkRequest(BaseModel):
    """Payload for linking an existing FavorIoT device to the current user.

    Both ``platform_device_id`` and ``device_developer_id`` are accepted so the
    mobile client and the older backend contract keep working.
    """

    platform_device_id: str | None = None
    device_developer_id: str | None = None
    device_name: str | None = None
    device_type: str | None = None


class RPCRequest(BaseModel):
    """RPC command relay payload."""

    method: str
    params: dict[str, object] | None = None
    twoway: bool = False
    timeout: int = 5000
