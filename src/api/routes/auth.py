"""OAuth 2.0 + PKCE Authorization Code flow endpoints.

Routes
------
GET /auth/login     — Redirect the browser to the Microsoft identity platform
                      consent/login URL.  Generates a PKCE code_verifier,
                      code_challenge, and a CSRF state token.

GET /auth/callback  — Exchange the authorization code for tokens (server-side
                      only).  Tokens are stored via TokenManager; nothing is
                      returned to the browser that contains token values.

Security notes
--------------
- code_verifier = base64url(random 32 bytes)  — never leaves the server
- code_challenge = base64url(SHA-256(code_verifier))  — sent to Microsoft
- state          = secrets.token_hex(16), stored server-side with 5-min TTL
- Token exchange is entirely server-side; clients never see raw tokens.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from src.services.mail.token_manager import TokenManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# In-process state store (maps state -> {code_verifier, expires_at, oid})
# For production consider a Redis-backed store with TTL.
# ---------------------------------------------------------------------------
_STATE_TTL_SECS = 300  # 5 minutes
_pending_states: dict[str, dict[str, Any]] = {}


def _prune_expired_states() -> None:
    now = time.time()
    expired = [k for k, v in _pending_states.items() if v["expires_at"] < now]
    for k in expired:
        del _pending_states[k]


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge).

    code_verifier  = base64url(random 32 bytes), no padding
    code_challenge = base64url(SHA-256(ascii(code_verifier))), no padding
    """
    raw = secrets.token_bytes(32)
    code_verifier = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


# ---------------------------------------------------------------------------
# Config helpers (read from env)
# ---------------------------------------------------------------------------

def _tenant_id() -> str:
    return os.environ["AZURE_TENANT_ID"]


def _client_id() -> str:
    return os.environ["AZURE_CLIENT_ID"]


def _redirect_uri() -> str:
    from src.infra.config import get_settings
    return get_settings().azure_redirect_uri


_SCOPES = (
    "openid profile email offline_access User.Read Mail.ReadWrite Mail.Send"
)

_AUTHORIZE_URL = (
    "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
)
_TOKEN_URL = (
    "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/login")
def login() -> RedirectResponse:
    """Initiate the OAuth 2.0 + PKCE Authorization Code flow.

    Generates a fresh PKCE pair and state token, stores them server-side,
    then redirects the browser to the Microsoft identity platform.
    """
    _prune_expired_states()

    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_hex(16)

    _pending_states[state] = {
        "code_verifier": code_verifier,
        "expires_at": time.time() + _STATE_TTL_SECS,
    }
    logger.info("auth: initiated OAuth flow state=%s", state)

    params = {
        "client_id": _client_id(),
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "response_mode": "query",
        "scope": _SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = _AUTHORIZE_URL.format(tenant_id=_tenant_id())
    return RedirectResponse(url=f"{authorize_url}?{urlencode(params)}")


@router.get("/callback")
async def callback(
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: str = Query(..., description="CSRF state token"),
) -> dict[str, str]:
    """Exchange the authorization code for tokens and store them.

    The response body contains only non-sensitive confirmation data.
    Token values are never returned to the client.
    """
    _prune_expired_states()

    # --- CSRF / state validation ---
    pending = _pending_states.pop(state, None)
    if pending is None:
        logger.warning("auth: unknown or expired state state=%s", state)
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter.")

    if pending["expires_at"] < time.time():
        logger.warning("auth: state TTL exceeded state=%s", state)
        raise HTTPException(status_code=400, detail="State token has expired. Please restart the login flow.")

    code_verifier: str = pending["code_verifier"]

    # --- Token exchange (server-side only) ---
    token_url = _TOKEN_URL.format(tenant_id=_tenant_id())
    payload = {
        "grant_type": "authorization_code",
        "client_id": _client_id(),
        "client_secret": os.environ["AZURE_CLIENT_SECRET"],
        "code": code,
        "redirect_uri": _redirect_uri(),
        "code_verifier": code_verifier,
    }

    logger.info("auth: exchanging authorization code state=%s", state)
    resp = httpx.post(token_url, data=payload, timeout=15)

    if resp.status_code != 200:
        logger.error(
            "auth: token exchange failed status=%d body=%s",
            resp.status_code,
            resp.text,
        )
        raise HTTPException(
            status_code=502,
            detail="Token exchange with Microsoft failed. Please try again.",
        )

    data = resp.json()
    access_token: str = data["access_token"]
    refresh_token: str = data["refresh_token"]
    expires_in: int = data.get("expires_in", 3600)
    scope: str = data.get("scope", "")

    # Extract OID from the id_token claims (or use the /me endpoint)
    oid = _extract_oid(data.get("id_token", ""), access_token)

    expires_at = time.time() + expires_in
    tm = TokenManager()
    tm.store_tokens(oid, access_token, refresh_token, expires_at, scope)

    logger.info(
        "auth: tokens stored successfully oid=%s expires_at=%s", oid, expires_at
    )

    # Return only non-sensitive confirmation — never return token values
    return {
        "status": "authenticated",
        "oid": oid,
        "scope": scope,
    }


# ---------------------------------------------------------------------------
# Helper: extract OID from id_token or Graph /me
# ---------------------------------------------------------------------------

def _extract_oid(id_token: str, access_token: str) -> str:
    """Extract the Azure AD OID.

    Prefers the ``oid`` claim in the id_token payload (base64-decoded, no
    signature verification needed here since it came directly from Microsoft
    over TLS).  Falls back to GET /me if the id_token is absent.
    """
    import json as _json

    if id_token:
        try:
            parts = id_token.split(".")
            if len(parts) >= 2:
                # Add padding back
                padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                claims = _json.loads(base64.urlsafe_b64decode(padded))
                oid = claims.get("oid")
                if oid:
                    return oid
        except Exception as exc:  # noqa: BLE001
            logger.warning("auth: id_token decode failed, falling back to /me: %s", exc)

    # Fallback: call Graph /me
    me_resp = httpx.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    me_resp.raise_for_status()
    return me_resp.json()["id"]
