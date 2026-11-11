"""Request-scoped configuration for the Lextari API."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import Request


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration sourced from Workers bindings or the environment."""

    tb_url: str = "http://localhost:8080"
    tb_api_key: str = ""
    supabase_url: str = ""
    supabase_jwks_url: str = ""
    debug: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    ws_poll_interval: int = 5

    @property
    def jwks_url(self) -> str:
        """Supabase JWKS endpoint, auto-derived from the project URL."""
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"

    @classmethod
    def from_env(cls, env: Mapping[str, Any] | None = None) -> "Settings":
        """Build settings from Worker bindings, falling back to ``os.environ``."""

        def read(key: str, default: str = "") -> str:
            if env is not None:
                value = env.get(key) if isinstance(env, Mapping) else getattr(env, key, None)
                if value is not None:
                    return str(value)
            return os.environ.get(key, default)

        try:
            poll_interval = int(read("WS_POLL_INTERVAL", "5"))
        except ValueError:
            poll_interval = 5

        return cls(
            tb_url=read("TB_URL", "http://localhost:8080"),
            tb_api_key=read("TB_API_KEY"),
            supabase_url=read("SUPABASE_URL"),
            supabase_jwks_url=read("SUPABASE_JWKS_URL"),
            debug=_as_bool(read("DEBUG", "false")),
            cors_origins=_as_tuple(read("CORS_ORIGINS", "http://localhost:3000")),
            ws_poll_interval=poll_interval,
        )


def worker_env() -> Any:
    """Return the global Workers ``env`` binding, or ``None`` outside Workers."""
    try:
        from workers import env
    except ImportError:
        return None
    return env


def get_settings(request: Request) -> Settings:
    """FastAPI dependency returning settings from the Worker env."""
    return Settings.from_env(request.scope.get("env"))


def get_settings_from_scope(scope: Mapping[str, Any]) -> Settings:
    """Resolve settings for non-HTTP scopes such as WebSocket connections."""
    return Settings.from_env(scope.get("env"))
