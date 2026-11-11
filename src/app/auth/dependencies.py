"""FastAPI dependency for Supabase JWT verification."""

import logging
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwks import verify_supabase_token
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Extract and verify a Supabase JWT from the Authorization header.

    Returns the decoded token payload with ``sub`` (user_id), ``email``, etc.
    """
    if not settings.supabase_url and not settings.supabase_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth not configured",
        )

    try:
        return await verify_supabase_token(
            credentials.credentials,
            settings.jwks_url,
            settings.supabase_url,
        )
    except Exception:
        logger.warning("JWT verification failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
