"""RPC relay - Flutter -> Lextari API -> ThingsBoard -> ESP32."""

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.clients.http import FetchError
from app.clients.thingsboard import ThingsBoardClient, get_tb_client
from app.db.d1 import get_db
from app.schemas.requests import RPCRequest
from app.services.devices import resolve_user_device

router = APIRouter()


async def _relay_rpc(
    device_id: str,
    body: RPCRequest,
    tb: ThingsBoardClient,
) -> dict[str, object]:
    try:
        if body.twoway:
            result = await tb.send_rpc_twoway(
                device_id, body.method, body.params, timeout=body.timeout
            )
            return {"device_id": device_id, "method": body.method, "result": result}
        await tb.send_rpc_oneway(device_id, body.method, body.params)
        return {"device_id": device_id, "method": body.method, "sent": True}
    except FetchError as exc:
        if exc.status_code == 504:
            return {"device_id": device_id, "method": body.method, "queued": True}
        raise


@router.post("/api/v1/rpc/{device_id}")
async def send_rpc(
    device_id: str,
    body: RPCRequest,
    user: dict[str, Any] = Depends(get_current_user),
    tb: ThingsBoardClient = Depends(get_tb_client),
) -> dict[str, object]:
    """Relay an RPC command from Flutter to ThingsBoard to ESP32.

    One-way for fire-and-forget (watering, misting).
    Two-way for commands needing confirmation.
    """
    return await _relay_rpc(device_id, body, tb)


@router.post("/api/rpc")
async def send_rpc_for_user(
    body: RPCRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
    tb: ThingsBoardClient = Depends(get_tb_client),
) -> dict[str, object]:
    """Device-agnostic RPC used by the Flutter app.

    The device is resolved from the authenticated user's linked devices.
    """
    device = await resolve_user_device(user["sub"], db)
    return await _relay_rpc(device.tb_device_id, body, tb)
