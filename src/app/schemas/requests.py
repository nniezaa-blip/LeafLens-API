"""Request body models."""

from pydantic import BaseModel


class DeviceRegisterRequest(BaseModel):
    """ESP32 device registration payload."""

    mac_address: str
    user_id: str
    device_name: str


class RPCRequest(BaseModel):
    """RPC command relay payload."""

    method: str
    params: dict[str, object] | None = None
    twoway: bool = False
    timeout: int = 5000
