"""
GraphAppClient — Microsoft Graph client using Application permissions.

Uses client_credentials flow (no user context required).
Suitable for tenant-wide operations: GET /users, etc.

Required Azure AD app permissions (Application, not Delegated):
  User.Read.All
  Directory.Read.All (optional — needed for manager lookup)

Environment variables
---------------------
  AZURE_TENANT_ID
  AZURE_CLIENT_ID
  AZURE_CLIENT_SECRET
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterator

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SCOPE = "https://graph.microsoft.com/.default"


class GraphAppClient:
    """Tenant-wide Graph client using client credentials (app-only auth)."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = httpx.Client(timeout=30)

        self._access_token: str = ""
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _ensure_token(self) -> str:
        """Return a valid app-level access token, refreshing if needed."""
        if time.time() < self._token_expires_at - 60:
            return self._access_token

        url = _TOKEN_URL.format(tenant_id=self._tenant_id)
        resp = self._http.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": _SCOPE,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        logger.info("GraphAppClient: obtained app token (expires_in=%s)", data.get("expires_in"))
        return self._access_token

    def _get(self, path: str, params: dict | None = None, *, _max_retries: int = 3) -> dict:
        """GET with automatic retry on 429 (honours Retry-After) and 5xx."""
        delay = 1.0
        for attempt in range(_max_retries + 1):
            token = self._ensure_token()
            resp = self._http.get(
                f"{_GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params or {},
                timeout=30,
            )
            if resp.status_code == 429:
                try:
                    wait = float(resp.headers.get("Retry-After", delay))
                except (ValueError, TypeError):
                    wait = delay
                wait = min(wait, 120.0)
                logger.warning(
                    "GraphAppClient: 429 rate-limited path=%s retry_after=%.1fs attempt=%d",
                    path, wait, attempt + 1,
                )
                if attempt < _max_retries:
                    time.sleep(wait)
                    delay *= 2
                    continue
            if resp.status_code >= 500 and attempt < _max_retries:
                logger.warning(
                    "GraphAppClient: %d server error path=%s attempt=%d — retrying in %.1fs",
                    resp.status_code, path, attempt + 1, delay,
                )
                time.sleep(delay)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()  # final raise after exhausting retries
        return resp.json()  # unreachable but satisfies type checker

    # ------------------------------------------------------------------
    # User directory
    # ------------------------------------------------------------------

    def list_users_pages(
        self,
        select: str = "id,displayName,mail,department,jobTitle",
        page_size: int = 999,
    ) -> Iterator[list[dict[str, Any]]]:
        """Yield pages of user records. Handles @odata.nextLink pagination."""
        # First request uses path + params
        url: str = f"{_GRAPH_BASE}/users"
        params: dict | None = {
            "$select": select,
            "$top": str(page_size),
        }

        _max_retries = 3
        while url:
            delay = 1.0
            for attempt in range(_max_retries + 1):
                token = self._ensure_token()
                resp = self._http.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout=30,
                )
                if resp.status_code == 429:
                    try:
                        wait = float(resp.headers.get("Retry-After", delay))
                    except (ValueError, TypeError):
                        wait = delay
                    wait = min(wait, 120.0)
                    logger.warning(
                        "GraphAppClient: 429 rate-limited (pagination) retry_after=%.1fs attempt=%d",
                        wait, attempt + 1,
                    )
                    if attempt < _max_retries:
                        time.sleep(wait)
                        delay *= 2
                        continue
                if resp.status_code >= 500 and attempt < _max_retries:
                    logger.warning(
                        "GraphAppClient: %d server error (pagination) attempt=%d — retrying in %.1fs",
                        resp.status_code, attempt + 1, delay,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                resp.raise_for_status()
                break

            data = resp.json()
            page = data.get("value", [])
            if page:
                yield page

            # nextLink is a full URL — use it directly; clear params
            url = data.get("@odata.nextLink", "")
            params = None

    def get_manager(self, user_aad_id: str) -> dict[str, Any] | None:
        """Return manager's {id, displayName, mail} or None if not set."""
        try:
            return self._get(
                f"/users/{user_aad_id}/manager",
                params={"$select": "id,displayName,mail"},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
