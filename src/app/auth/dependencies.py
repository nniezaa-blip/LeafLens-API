"""FastAPI dependency for access-token verification."""

import logging
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwks import verify_access_token
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Extract and verify a Lextari access token from the Authorization header.

    Returns the decoded token payload with ``sub`` (user_id), ``email``, etc.
    """
    if not settings.jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth not configured",
        )

    try:
        return await verify_access_token(
            credentials.credentials,
            settings.jwks_url,
            settings.auth_issuer,
            settings.auth_audience,
        )
    except Exception:
        logger.warning("JWT verification failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
