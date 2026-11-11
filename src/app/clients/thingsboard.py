"""ThingsBoard REST API client built on the Workers fetch API."""

from typing import Any
from urllib.parse import urlencode

from fastapi import Depends

from app.clients.http import fetch_json
from app.config import Settings, get_settings


class ThingsBoardClient:
    """Async client for the ThingsBoard REST API."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.tb_url.rstrip("/")
        self.headers = {"X-Authorization": f"ApiKey {settings.tb_api_key}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return await fetch_json(url, method=method, headers=self.headers, body=body)

    # ── Telemetry ───────────────────────────────────────────────────────

    async def get_latest_telemetry(self, device_id: str, keys: list[str]) -> dict[str, Any]:
        """Fetch latest values for given keys. Returns ``{key: value}``."""
        raw: dict[str, list[dict[str, Any]]] = await self._request(
            "GET",
            f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
            params={"keys": ",".join(keys)},
        )
        return {key: float(entries[0]["value"]) for key, entries in raw.items() if entries}

    async def get_telemetry_history(
        self,
        device_id: str,
        keys: list[str],
        start_ts_ms: int,
        end_ts_ms: int,
        agg: str = "AVG",
        interval_ms: int = 3_600_000,
        limit: int = 2000,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch historical telemetry. Returns ``{key: [{ts, value}, ...]}``."""
        result: dict[str, list[dict[str, Any]]] = await self._request(
            "GET",
            f"/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
            params={
                "keys": ",".join(keys),
                "startTs": start_ts_ms,
                "endTs": end_ts_ms,
                "limit": limit,
                "agg": agg,
                "interval": interval_ms,
                "orderBy": "ASC",
            },
        )
        return result

    # ── Attributes ──────────────────────────────────────────────────────

    async def get_shared_attributes(self, device_id: str) -> dict[str, Any]:
        raw: list[dict[str, Any]] = await self._request(
            "GET",
            f"/api/plugins/telemetry/DEVICE/{device_id}/values/attributes/SHARED_SCOPE",
        )
        return {entry["key"]: entry["value"] for entry in raw}

    # ── RPC ─────────────────────────────────────────────────────────────

    async def send_rpc_oneway(
        self, device_id: str, method: str, params: dict[str, object] | None = None
    ) -> None:
        await self._request(
            "POST",
            f"/api/rpc/oneway/{device_id}",
            body={"method": method, "params": params or {}},
        )

    async def send_rpc_twoway(
        self,
        device_id: str,
        method: str,
        params: dict[str, object] | None = None,
        timeout: int = 5000,
    ) -> dict[str, Any]:
        result: dict[str, Any] = await self._request(
            "POST",
            f"/api/rpc/twoway/{device_id}",
            body={"method": method, "params": params or {}, "timeout": timeout},
        )
        return result

    # ── Device Management ───────────────────────────────────────────────

    async def create_device(self, name: str, device_type: str = "sensor") -> dict[str, Any]:
        device: dict[str, Any] = await self._request(
            "POST",
            "/api/device",
            body={"name": name, "type": device_type},
        )
        return device

    async def get_device_credentials(self, device_id: str) -> dict[str, Any]:
        credentials: dict[str, Any] = await self._request(
            "GET",
            f"/api/device/{device_id}/credentials",
        )
        return credentials

    async def get_device(self, device_id: str) -> dict[str, Any]:
        device: dict[str, Any] = await self._request("GET", f"/api/device/{device_id}")
        return device


def get_tb_client(settings: Settings = Depends(get_settings)) -> ThingsBoardClient:
    """FastAPI dependency returning a ThingsBoard client for the request."""
    return ThingsBoardClient(settings)
