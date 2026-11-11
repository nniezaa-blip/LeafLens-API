"""Shared test doubles for D1 and ThingsBoard."""

from typing import Any


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.results = rows


class _FakeStatement:
    def __init__(self, db: "FakeD1", sql: str) -> None:
        self._db = db
        self._sql = sql
        self._params: tuple[Any, ...] = ()

    def bind(self, *params: Any) -> "_FakeStatement":
        self._params = params
        return self

    async def all(self) -> _FakeResult:
        return _FakeResult(list(self._db.rows))

    async def first(self) -> dict[str, Any] | None:
        return self._db.rows[0] if self._db.rows else None

    async def run(self) -> None:
        self._db.executed.append((self._sql, self._params))


class FakeD1:
    """Minimal stand-in for a Cloudflare D1 binding."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def prepare(self, sql: str) -> _FakeStatement:
        return _FakeStatement(self, sql)


class FakeThingsBoard:
    """In-memory ThingsBoard client used by endpoint tests."""

    def __init__(self) -> None:
        self.latest: dict[str, Any] = {}
        self.history: dict[str, list[dict[str, Any]]] = {}
        self.oneway_calls: list[tuple[str, str, dict[str, object] | None]] = []
        self.twoway_calls: list[tuple[str, str, dict[str, object] | None, int]] = []
        self.history_calls = 0

    async def get_latest_telemetry(self, device_id: str, keys: list[str]) -> dict[str, Any]:
        return dict(self.latest)

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
        self.history_calls += 1
        return self.history

    async def send_rpc_oneway(
        self, device_id: str, method: str, params: dict[str, object] | None = None
    ) -> None:
        self.oneway_calls.append((device_id, method, params))

    async def send_rpc_twoway(
        self,
        device_id: str,
        method: str,
        params: dict[str, object] | None = None,
        timeout: int = 5000,
    ) -> dict[str, Any]:
        self.twoway_calls.append((device_id, method, params, timeout))
        return {"ok": True}

    async def create_device(self, name: str, device_type: str = "sensor") -> dict[str, Any]:
        return {"id": {"id": "tb-new-device"}}

    async def get_device_credentials(self, device_id: str) -> dict[str, Any]:
        return {"credentialsId": "tb-access-token"}
