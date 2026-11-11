"""Helpers for querying the Cloudflare D1 binding."""

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import HTTPException, Request, status


def _to_py(value: Any) -> Any:
    try:
        from pyodide.ffi import to_py  # type: ignore[attr-defined]
    except ImportError:
        return value
    return to_py(value)


async def query_all(db: Any, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """Run a query and return every row as a plain dictionary."""
    statement = db.prepare(sql)
    if params:
        statement = statement.bind(*params)
    result = await statement.all()
    rows = _to_py(result.results)
    return [dict(row) for row in rows]


async def query_first(db: Any, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    """Run a query and return the first row, if any."""
    rows = await query_all(db, sql, params)
    return rows[0] if rows else None


async def execute(db: Any, sql: str, params: Sequence[Any] = ()) -> None:
    """Run a statement that does not return rows."""
    statement = db.prepare(sql)
    if params:
        statement = statement.bind(*params)
    await statement.run()


def get_db(request: Request) -> Any:
    """FastAPI dependency returning the D1 binding for the current request."""
    env = request.scope.get("env")
    db = getattr(env, "DB", None) if env is not None else None
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database binding is not configured",
        )
    return db


def get_db_from_scope(scope: Mapping[str, Any]) -> Any:
    """Resolve the D1 binding for non-HTTP scopes such as WebSockets."""
    env = scope.get("env")
    return getattr(env, "DB", None) if env is not None else None
