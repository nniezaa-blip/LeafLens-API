"""HTTP helper built on the Workers fetch API with a local httpx fallback."""

import json
from typing import Any


class FetchError(Exception):
    """Raised when an upstream HTTP request returns an error status."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        super().__init__(detail or f"HTTP {status_code}")
        self.status_code = status_code
        self.detail = detail


async def _fetch_with_httpx(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
) -> Any:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(method, url, headers=headers, json=body)
        if response.status_code >= 400:
            raise FetchError(response.status_code, response.text)
        return response.json()


async def fetch_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    """Fetch JSON from an upstream service."""
    request_headers = headers or {}
    try:
        from pyodide.http import pyfetch
    except ImportError:
        return await _fetch_with_httpx(url, method=method, headers=request_headers, body=body)

    payload = json.dumps(body) if body is not None else None
    response = await pyfetch(url, method=method, headers=request_headers, body=payload)
    if not response.ok:
        detail = await response.string()
        raise FetchError(int(response.status), detail)
    return await response.json()
