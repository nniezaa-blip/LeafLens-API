"""Lextari API - FastAPI application factory."""

from logging import getLogger

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.clients.http import FetchError, fetch_json
from app.config import Settings, get_settings, worker_env
from app.logging_config import setup_logging

logger = getLogger(__name__)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = Settings.from_env(worker_env())
    setup_logging(debug=settings.debug)
    app = FastAPI(
        title="Lextari API",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Middleware (last added = first executed)
    from app.middleware import RequestIDMiddleware

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers
    from app.utils.errors import LextariError, lextari_error_handler

    app.add_exception_handler(LextariError, lextari_error_handler)  # type: ignore[arg-type]

    # Routers
    from app.routers import devices, health, rpc, telemetry, ws

    app.include_router(devices.router)
    app.include_router(telemetry.router)
    app.include_router(health.router)
    app.include_router(rpc.router)
    app.include_router(ws.router)

    # Health probes (no auth)

    @app.get("/api/v1/health")
    async def liveness() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/api/v1/ready")
    async def readiness(
        request: Request,
        settings: Settings = Depends(get_settings),
    ) -> JSONResponse:
        checks: dict[str, bool] = {"database": False, "thingsboard": False}

        env = request.scope.get("env")
        db = getattr(env, "DB", None) if env is not None else None
        if db is not None:
            try:
                await db.prepare("SELECT 1").first()
                checks["database"] = True
            except Exception:
                logger.warning("Database health check failed")

        try:
            await fetch_json(
                f"{settings.tb_url}/api/auth/user",
                headers={"X-Authorization": f"ApiKey {settings.tb_api_key}"},
            )
            checks["thingsboard"] = True
        except FetchError as exc:
            checks["thingsboard"] = exc.status_code == 401
        except Exception:
            logger.warning("ThingsBoard health check failed")

        all_ok = all(checks.values())
        return JSONResponse(
            status_code=200 if all_ok else 503,
            content={"status": "ready" if all_ok else "degraded", "checks": checks},
        )

    return app


app = create_app()
