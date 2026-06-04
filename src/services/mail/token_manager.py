"""Delegated OAuth token lifecycle manager.

Responsibilities
----------------
- Proactive refresh: if access token expires within 5 minutes, refresh before use.
- Reactive refresh: on HTTP 401 from Graph, retry once with a fresh token.
- Atomic write: refresh token is persisted to storage BEFORE the new access
  token is used, preventing a state where the old refresh token has been
  consumed but the new one is lost.
- All operations are logged at INFO level (token values are never logged).

Storage keys
------------
  graph-access-token-{oid}     — raw JWT string
  graph-refresh-token-{oid}    — raw refresh token string
  graph-token-metadata-{oid}   — JSON: {expires_at: float (unix), scope: str}
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from src.infra.token_store import SecretStore, get_token_store

logger = logging.getLogger(__name__)

# How many seconds before actual expiry we treat the token as expired
_PROACTIVE_REFRESH_MARGIN_SECS = 300  # 5 minutes

_TOKEN_ENDPOINT = (
    "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
)


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: float  # unix timestamp
    scope: str


class TokenManager:
    """Manages delegated Graph tokens for a single or multiple OIDs.

    Parameters
    ----------
    store:
        SecretStore implementation. Defaults to the factory result of
        ``get_token_store()``.
    tenant_id:
        Azure AD tenant ID. Defaults to the ``AZURE_TENANT_ID`` env var.
    client_id:
        Azure AD app (client) ID. Defaults to ``AZURE_CLIENT_ID`` env var.
    client_secret_value:
        App client secret value. Defaults to ``AZURE_CLIENT_SECRET`` env var.
        This is a *value* passed at construction time — it is never stored.
    """

    def __init__(
        self,
        store: Optional[SecretStore] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret_value: Optional[str] = None,
    ) -> None:
        self._store = store or get_token_store()
        self._tenant_id = tenant_id or os.environ["AZURE_TENANT_ID"]
        self._client_id = client_id or os.environ["AZURE_CLIENT_ID"]
        self._client_secret_value = (
            client_secret_value or os.environ["AZURE_CLIENT_SECRET"]
        )

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _access_key(oid: str) -> str:
        return f"graph-access-token-{oid}"

    @staticmethod
    def _refresh_key(oid: str) -> str:
        return f"graph-refresh-token-{oid}"

    @staticmethod
    def _meta_key(oid: str) -> str:
        return f"graph-token-metadata-{oid}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_tokens(
        self,
        oid: str,
        access_token: str,
        refresh_token: str,
        expires_at: float,
        scope: str = "",
    ) -> None:
        """Persist a token set returned from the OAuth token endpoint.

        Write order: refresh token first (atomic-write guarantee per
        ADR-SEC-004), then access token, then metadata.
        """
        # 1. Refresh token FIRST (atomic-write rule)
        self._store.set(self._refresh_key(oid), refresh_token)
        logger.info("TokenManager: stored refresh token oid=%s", oid)

        # 2. Access token
        self._store.set(self._access_key(oid), access_token)
        logger.info("TokenManager: stored access token oid=%s", oid)

        # 3. Metadata (expiry + scope)
        self._store.set_json(
            self._meta_key(oid),
            {"expires_at": expires_at, "scope": scope},
        )
        logger.info(
            "TokenManager: stored metadata oid=%s expires_at=%s", oid, expires_at
        )

    def get_access_token(self, team_lead_oid: str) -> str:
        """Return a valid access token for *team_lead_oid*.

        Applies proactive refresh if the token expires within 5 minutes.
        Raises ``TokenUnavailableError`` if no token exists for the OID.
        """
        meta = self._store.get_json(self._meta_key(team_lead_oid))
        if meta is None:
            raise TokenUnavailableError(
                f"No token metadata found for oid={team_lead_oid}. "
                "The team lead must complete the OAuth consent flow first."
            )

        expires_at: float = meta["expires_at"]
        now = time.time()

        if expires_at - now < _PROACTIVE_REFRESH_MARGIN_SECS:
            logger.info(
                "TokenManager: proactive refresh triggered oid=%s "
                "seconds_until_expiry=%.0f",
                team_lead_oid,
                expires_at - now,
            )
            return self.refresh_token(team_lead_oid)

        access_token = self._store.get(self._access_key(team_lead_oid))
        if not access_token:
            logger.info(
                "TokenManager: access token missing, forcing refresh oid=%s",
                team_lead_oid,
            )
            return self.refresh_token(team_lead_oid)

        logger.info("TokenManager: access token retrieved oid=%s", team_lead_oid)
        return access_token

    def refresh_token(self, oid: str) -> str:
        """Exchange the stored refresh token for a new token set.

        Returns the new access token.
        Raises ``TokenUnavailableError`` if no refresh token is stored.
        Raises ``TokenRefreshError`` if the token endpoint returns an error.
        """
        stored_refresh = self._store.get(self._refresh_key(oid))
        if not stored_refresh:
            raise TokenUnavailableError(
                f"No refresh token found for oid={oid}. "
                "Re-authentication required."
            )

        endpoint = _TOKEN_ENDPOINT.format(tenant_id=self._tenant_id)
        payload = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "client_secret": self._client_secret_value,
            "refresh_token": stored_refresh,
            "scope": (
                "openid profile email offline_access "
                "User.Read Mail.ReadWrite Mail.Send"
            ),
        }

        logger.info("TokenManager: requesting token refresh oid=%s", oid)
        response = httpx.post(endpoint, data=payload, timeout=15)

        if response.status_code != 200:
            logger.error(
                "TokenManager: refresh failed oid=%s status=%s",
                oid,
                response.status_code,
            )
            raise TokenRefreshError(
                f"Token refresh failed for oid={oid}: "
                f"HTTP {response.status_code} — {response.text}"
            )

        data = response.json()
        new_access = data["access_token"]
        new_refresh = data.get("refresh_token", stored_refresh)
        expires_in: int = data.get("expires_in", 3600)
        expires_at = time.time() + expires_in
        scope = data.get("scope", "")

        # Atomic-write: store new refresh BEFORE returning new access token
        self.store_tokens(oid, new_access, new_refresh, expires_at, scope)
        logger.info(
            "TokenManager: refresh successful oid=%s expires_at=%s", oid, expires_at
        )
        return new_access

    def invalidate_tokens(self, oid: str) -> None:
        """Remove all stored tokens for *oid* (e.g. on user sign-out)."""
        self._store.delete(self._access_key(oid))
        self._store.delete(self._refresh_key(oid))
        self._store.delete(self._meta_key(oid))
        logger.info("TokenManager: invalidated all tokens oid=%s", oid)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TokenUnavailableError(RuntimeError):
    """Raised when no token exists for the requested OID."""


class TokenRefreshError(RuntimeError):
    """Raised when the token endpoint returns a non-200 response."""
