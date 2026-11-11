"""Supabase JWKS verification using the Workers fetch API."""

import time
from typing import Any

import jwt

from app.clients.http import fetch_json

_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_CACHE_TTL = 3600.0


async def _get_jwks(jwks_url: str) -> dict[str, Any]:
    now = time.time()
    cached = _JWKS_CACHE.get(jwks_url)
    if cached is not None and now - cached[0] < _JWKS_CACHE_TTL:
        return cached[1]

    jwks: dict[str, Any] = await fetch_json(jwks_url)
    _JWKS_CACHE[jwks_url] = (now, jwks)
    return jwks


def _select_key(jwks: dict[str, Any], kid: str | None) -> dict[str, Any]:
    keys = jwks.get("keys", [])
    if not isinstance(keys, list):
        raise jwt.InvalidTokenError("Invalid JWKS document")
    for key in keys:
        if isinstance(key, dict) and (kid is None or key.get("kid") == kid):
            return key
    raise jwt.InvalidTokenError("Signing key not found")


async def verify_supabase_token(token: str, jwks_url: str, supabase_url: str) -> dict[str, Any]:
    """Verify a Supabase JWT using a cached JWKS public key.

    Returns the decoded payload (contains ``sub`` = user_id, ``email``, etc.).
    Raises ``jwt.InvalidTokenError`` on failure.
    """
    header = jwt.get_unverified_header(token)
    jwks = await _get_jwks(jwks_url)
    key_data = _select_key(jwks, header.get("kid"))
    algorithm = str(key_data.get("alg") or "RS256")
    signing_key = jwt.PyJWK(key_data, algorithm=algorithm)

    issuer = f"{supabase_url}/auth/v1" if supabase_url else None
    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=[algorithm],
        audience="authenticated",
        issuer=issuer,
    )
    result: dict[str, Any] = payload
    return result
