"""Command relay - Flutter -> Lextari API -> FavorIoT -> ESP32."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.clients.favoriot import FavorIoTClient, FavorIoUnsupportedError, get_favoriot_client
from app.clients.http import FetchError
from app.db.d1 import get_db
from app.schemas.requests import RPCRequest
from app.services.devices import resolve_user_device

router = APIRouter()


async def _relay_rpc(
    device_id: str,
    body: RPCRequest,
    favoriot: FavorIoTClient,
) -> dict[str, object]:
    try:
        if body.twoway:
            result = await favoriot.send_rpc_twoway(
                device_id, body.method, body.params, timeout=body.timeout
            )
            return {"device_id": device_id, "method": body.method, "result": result}
        await favoriot.send_rpc_oneway(device_id, body.method, body.params)
        return {"device_id": device_id, "method": body.method, "sent": True}
    except FavorIoUnsupportedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except FetchError as exc:
        if exc.status_code == 504:
            return {"device_id": device_id, "method": body.method, "queued": True}
        raise


@router.post("/api/v1/rpc/{device_id}")
async def send_rpc(
    device_id: str,
    body: RPCRequest,
    user: dict[str, Any] = Depends(get_current_user),
    favoriot: FavorIoTClient = Depends(get_favoriot_client),
) -> dict[str, object]:
    """Relay a one-way command from Flutter to a FavorIoT command stream.

    Two-way RPC is not available through FavorIoT REST and returns 501.
    """
    return await _relay_rpc(device_id, body, favoriot)


@router.post("/api/rpc")
async def send_rpc_for_user(
    body: RPCRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
    favoriot: FavorIoTClient = Depends(get_favoriot_client),
) -> dict[str, object]:
    """Device-agnostic command used by the Flutter app.

    The device is resolved from the authenticated user's linked devices.
    """
    device = await resolve_user_device(user["sub"], db)
    return await _relay_rpc(device.favoriot_device_id, body, favoriot)
