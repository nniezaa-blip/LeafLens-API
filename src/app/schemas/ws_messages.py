"""WebSocket message types."""

from enum import StrEnum

from pydantic import BaseModel


class WSMessageType(StrEnum):
    SUBSCRIBE = "subscribe"
    TELEMETRY = "telemetry"
    ATTRIBUTE = "attribute"
    PING = "ping"
    PONG = "pong"


class WSMessage(BaseModel):
    """WebSocket message envelope."""

    type: WSMessageType
    device_id: str | None = None
    key: str | None = None
    value: float | None = None
    ts: int | None = None
