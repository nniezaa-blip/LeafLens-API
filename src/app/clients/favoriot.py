"""FavorIoT REST API client built on the Workers fetch API.

FavorIoT stores device readings as streams. Each stream row carries a
``timestamp`` (epoch milliseconds) and a ``data`` object that maps sensor keys
to values. The helpers normalise that shape into the ``{key: value}`` and
``{key: [{ts, value}]}`` contracts the API routers already speak.
"""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import Depends

from app.clients.http import FetchError, fetch_json
from app.config import Settings, get_settings

_DEFAULT_BASE_URL = "https://apiv2.favoriot.com/v2"
_LATEST_ROWS = 50
_HISTORY_ROWS = 10_000
_ORDER_DESC = "desc"
_ORDER_ASC = "asc"
_COMMAND_KEY = "command"
_COMMAND_PARAMS_KEY = "params"


class FavorIoUnsupportedError(Exception):
    """Raised for operations the FavorIoT API cannot perform."""


def _parse_timestamp(value: Any) -> int:
    """Convert a FavorIoT timestamp into epoch milliseconds."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int | float):
        return int(value if value > 1_000_000_000_000 else value * 1000)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return 0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return int(parsed.timestamp() * 1000)
    return 0


def _row_timestamp(row: dict[str, Any]) -> int:
    """Prefer the stream timestamp and fall back to its ISO created field."""
    return _parse_timestamp(
        row.get("timestamp") or row.get("stream_created_at") or row.get("created_at")
    )


def _iter_readings(rows: Any) -> list[tuple[int, str, Any]]:
    """Flatten stream rows into ``(timestamp_ms, key, raw_value)`` tuples."""
    readings: list[tuple[int, str, Any]] = []
    if not isinstance(rows, list):
        return readings
    for row in rows:
        if not isinstance(row, dict):
            continue
        timestamp = _row_timestamp(row)
        data = row.get("data")
        if isinstance(data, dict):
            for key, value in data.items():
                readings.append((timestamp, str(key), value))
            continue
        stream = row.get("stream")
        if isinstance(stream, str) and stream:
            readings.append((timestamp, stream, data))
    return readings


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def latest_values(rows: Any, keys: list[str]) -> dict[str, float]:
    """Newest numeric value per requested key."""
    wanted = set(keys)
    latest: dict[str, tuple[int, float]] = {}
    for timestamp, key, raw in _iter_readings(rows):
        if key not in wanted:
            continue
        number = _as_float(raw)
        if number is None:
            continue
        current = latest.get(key)
        if current is None or timestamp >= current[0]:
            latest[key] = (timestamp, number)
    return {key: value for key, (_, value) in latest.items()}


def bucket_history(
    rows: Any,
    keys: list[str],
    interval_ms: int,
) -> dict[str, list[dict[str, float]]]:
    """Average readings into fixed-width buckets per key."""
    wanted = set(keys)
    buckets: dict[str, dict[int, list[float]]] = {key: {} for key in keys}
    for timestamp, key, raw in _iter_readings(rows):
        if key not in wanted:
            continue
        number = _as_float(raw)
        if number is None:
            continue
        slot = (timestamp // interval_ms) * interval_ms
        buckets[key].setdefault(slot, []).append(number)
    return {
        key: [
            {"ts": slot, "value": sum(values) / len(values)}
            for slot, values in sorted(slots.items())
        ]
        for key, slots in buckets.items()
    }


def _format_created_range(start_ts_ms: int, end_ts_ms: int) -> str:
    """Format a millisecond range in the FavorIoT Solr date syntax."""

    def as_iso(timestamp_ms: int) -> str:
        moment = datetime.fromtimestamp(timestamp_ms / 1000, UTC)
        milliseconds = moment.microsecond // 1000
        return f"{moment.strftime('%Y-%m-%dT%H:%M:%S')}.{milliseconds:03d}Z"

    return f"[{as_iso(start_ts_ms)} TO {as_iso(end_ts_ms)}]"


def _path_device_id(device_id: str) -> str:
    return quote(device_id, safe="")


class FavorIoTClient:
    """Async client for the FavorIoT v2 REST API."""

    def __init__(self, settings: Settings) -> None:
        self.base_url = (settings.favoriot_url or _DEFAULT_BASE_URL).rstrip("/")
        self.read_only_api_key = settings.favoriot_read_only_api_key
        self.read_write_api_key = settings.favoriot_read_write_api_key
        self.group_id = settings.favoriot_group_id

    @property
    def is_configured(self) -> bool:
        return bool(self.read_only_api_key and self.read_write_api_key)

    def _headers(self, method: str) -> dict[str, str]:
        api_key = self.read_only_api_key if method == "GET" else self.read_write_api_key
        if not api_key:
            raise FetchError(
                503, "FAVORIOT_READ_ONLY_API_KEY or FAVORIOT_READ_WRITE_API_KEY is not configured"
            )
        return {"apikey": api_key, "content-type": "application/json"}

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        payload = await fetch_json(
            url,
            method=method,
            headers=self._headers(method),
            body=body,
        )
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
        return payload

    # ── Telemetry ───────────────────────────────────────────────────────

    async def get_latest_telemetry(self, device_id: str, keys: list[str]) -> dict[str, float]:
        """Fetch the newest value per key. Returns ``{key: value}``."""
        rows = await self._request(
            "GET",
            "/streams",
            {
                "device_developer_id": device_id,
                "max": _LATEST_ROWS,
                "order": _ORDER_DESC,
            },
        )
        return latest_values(rows, keys)

    async def get_telemetry_history(
        self,
        device_id: str,
        keys: list[str],
        start_ts_ms: int,
        end_ts_ms: int,
        agg: str = "AVG",
        interval_ms: int = 3_600_000,
        limit: int = _HISTORY_ROWS,
    ) -> dict[str, list[dict[str, float]]]:
        """Fetch history, bucketed to ``interval_ms`` (AVG only)."""
        if agg.upper() != "AVG":
            raise FavorIoUnsupportedError(f"FavorIoT aggregation {agg!r} is not supported")
        rows = await self._request(
            "GET",
            "/streams",
            {
                "device_developer_id": device_id,
                "created_from_to": _format_created_range(start_ts_ms, end_ts_ms),
                "max": min(max(limit, 1), _HISTORY_ROWS),
                "order": _ORDER_ASC,
            },
        )
        return bucket_history(rows, keys, interval_ms)

    # ── Devices ─────────────────────────────────────────────────────────

    async def list_devices(self, device_name: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"max": _HISTORY_ROWS}
        if device_name:
            params["device_name"] = device_name
        rows = await self._request("GET", "/devices", params)
        return rows if isinstance(rows, list) else []

    async def get_device(self, device_id: str) -> dict[str, Any]:
        device: dict[str, Any] = await self._request(
            "GET", f"/devices/{_path_device_id(device_id)}"
        )
        return device

    async def create_device(self, name: str, device_type: str = "sensor") -> dict[str, Any]:
        """Create a device and return its developer ID and access token."""
        body: dict[str, Any] = {
            "device_name": name,
            "active": True,
            "device_type": device_type,
        }
        if self.group_id:
            body["group_developer_id"] = self.group_id
        await self._request("POST", "/devices", body=body)

        devices = await self.list_devices(device_name=name)
        matching = [device for device in devices if device.get("device_name") == name]
        if not matching:
            raise FetchError(502, "FavorIoT did not return the created device")
        return matching[0]

    # ── Actuators ───────────────────────────────────────────────────────

    async def send_rpc_oneway(
        self,
        device_id: str,
        method: str,
        params: dict[str, object] | None = None,
    ) -> None:
        """Publish a command stream the device can subscribe to over MQTT."""
        await self._request(
            "POST",
            "/streams",
            body={
                "device_developer_id": device_id,
                "data": {
                    _COMMAND_KEY: method,
                    _COMMAND_PARAMS_KEY: params or {},
                },
            },
        )

    async def send_rpc_twoway(
        self,
        device_id: str,
        method: str,
        params: dict[str, object] | None = None,
        timeout: int = 5000,
    ) -> dict[str, Any]:
        raise FavorIoUnsupportedError(
            "FavorIoT has no REST request/reply channel; use a one-way command stream"
        )


def get_favoriot_client(settings: Settings = Depends(get_settings)) -> FavorIoTClient:
    """FastAPI dependency returning a FavorIoT client for the request."""
    return FavorIoTClient(settings)
