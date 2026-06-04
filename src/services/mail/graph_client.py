"""Microsoft Graph HTTP client with auth injection, retry, and circuit breaker.

Design
------
- All Graph calls in the mail service layer go through this client.
- No direct httpx calls are permitted in draft_service or send_service.
- Retry policy: exponential backoff starting at 500 ms, multiplier 2x, max 3
  attempts (4 total calls including the first).
- Circuit breaker: opens after 5 consecutive failures; half-open after 60 s.
- On HTTP 401: single reactive refresh via TokenManager, then one retry.
- Delegated token injected per-request via Authorization: Bearer header.

Supported methods
-----------------
  get_channel_members(team_id, channel_id)
  create_draft(oid, to, cc, subject, body)
  update_draft(oid, message_id, body)
  send_draft(oid, message_id)
  delete_draft(oid, message_id)
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from .token_manager import TokenManager, TokenUnavailableError

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Retry configuration (ADR confirmed values)
_RETRY_INITIAL_DELAY_MS = 500
_RETRY_MULTIPLIER = 2
_RETRY_MAX_ATTEMPTS = 3  # retries after the first attempt

# Circuit breaker configuration
_CB_FAILURE_THRESHOLD = 5
_CB_RECOVERY_TIMEOUT_SECS = 60


class CircuitOpenError(RuntimeError):
    """Raised when the circuit breaker is open."""


class GraphAPIError(RuntimeError):
    """Raised on a non-retryable Graph API error."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class GraphClient:
    """Authenticated Microsoft Graph client.

    Parameters
    ----------
    token_manager:
        TokenManager instance used to obtain / refresh delegated tokens.
    """

    def __init__(self, token_manager: TokenManager) -> None:
        self._tm = token_manager
        self._http = httpx.Client(timeout=30)

        # Circuit breaker state
        self._cb_failures = 0
        self._cb_open_since: float | None = None

    # ------------------------------------------------------------------
    # Circuit breaker helpers
    # ------------------------------------------------------------------

    def _cb_check(self) -> None:
        """Raise CircuitOpenError if the circuit is open and not yet half-open."""
        if self._cb_open_since is None:
            return
        elapsed = time.time() - self._cb_open_since
        if elapsed < _CB_RECOVERY_TIMEOUT_SECS:
            raise CircuitOpenError(
                f"Circuit breaker is open. "
                f"Retry after {_CB_RECOVERY_TIMEOUT_SECS - elapsed:.0f}s."
            )
        # Half-open: allow one probe request through
        logger.info("GraphClient: circuit half-open, allowing probe request")

    def _cb_record_success(self) -> None:
        if self._cb_open_since is not None:
            logger.info("GraphClient: circuit breaker reset after successful probe")
        self._cb_failures = 0
        self._cb_open_since = None

    def _cb_record_failure(self) -> None:
        self._cb_failures += 1
        logger.warning(
            "GraphClient: consecutive failure count=%d", self._cb_failures
        )
        if self._cb_failures >= _CB_FAILURE_THRESHOLD:
            self._cb_open_since = time.time()
            logger.error(
                "GraphClient: circuit breaker OPENED after %d failures",
                self._cb_failures,
            )

    # ------------------------------------------------------------------
    # Core request method
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        oid: str,
        *,
        json: dict | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> httpx.Response:
        """Execute an authenticated Graph request with retry + circuit breaker.

        On HTTP 401 a single token refresh is attempted before the retry loop.
        """
        self._cb_check()

        url = f"{_GRAPH_BASE}{path}"
        delay_secs = _RETRY_INITIAL_DELAY_MS / 1000
        last_exc: Exception | None = None
        refreshed = False

        for attempt in range(_RETRY_MAX_ATTEMPTS + 1):
            try:
                access_token = self._tm.get_access_token(oid)
                headers = {"Authorization": f"Bearer {access_token}"}

                logger.info(
                    "GraphClient: %s %s attempt=%d oid=%s",
                    method,
                    path,
                    attempt + 1,
                    oid,
                )
                response = self._http.request(
                    method, url, headers=headers, json=json
                )

                # Reactive refresh on 401 (once per request chain)
                if response.status_code == 401 and not refreshed:
                    logger.info(
                        "GraphClient: 401 received, reactive refresh oid=%s", oid
                    )
                    self._tm.refresh_token(oid)
                    refreshed = True
                    continue  # retry immediately with fresh token

                if response.status_code in expected_statuses:
                    self._cb_record_success()
                    return response

                # Non-retryable client errors (4xx except 429/401)
                if 400 <= response.status_code < 500 and response.status_code not in (
                    401,
                    429,
                ):
                    self._cb_record_failure()
                    raise GraphAPIError(
                        f"Graph API error: {method} {path} -> "
                        f"HTTP {response.status_code}: {response.text}",
                        response.status_code,
                    )

                # 5xx or 429 — record failure and retry
                logger.warning(
                    "GraphClient: retryable status=%d attempt=%d",
                    response.status_code,
                    attempt + 1,
                )
                last_exc = GraphAPIError(
                    f"HTTP {response.status_code}", response.status_code
                )

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "GraphClient: network error attempt=%d error=%s",
                    attempt + 1,
                    exc,
                )
                last_exc = exc

            # Backoff before next attempt (skip sleep after last attempt)
            if attempt < _RETRY_MAX_ATTEMPTS:
                time.sleep(delay_secs)
                delay_secs *= _RETRY_MULTIPLIER

        # All attempts exhausted
        self._cb_record_failure()
        raise last_exc or GraphAPIError(
            f"All {_RETRY_MAX_ATTEMPTS + 1} attempts failed: {method} {path}", 0
        )

    # ------------------------------------------------------------------
    # Graph API methods
    # ------------------------------------------------------------------

    def get_channel_members(
        self, team_id: str, channel_id: str, oid: str
    ) -> list[dict[str, Any]]:
        """Return the member list for a Teams channel.

        Parameters
        ----------
        oid:
            OID of the calling user (team lead) whose delegated token is used.
        """
        path = f"/teams/{team_id}/channels/{channel_id}/members"
        response = self._request("GET", path, oid, expected_statuses=(200,))
        return response.json().get("value", [])

    def create_draft(
        self,
        oid: str,
        to: list[str],
        cc: list[str],
        subject: str,
        body: str,
        body_type: str = "HTML",
    ) -> dict[str, Any]:
        """Create an Outlook draft message in the team lead's mailbox.

        Parameters
        ----------
        oid:
            Team lead's AAD object ID — their delegated token is used.
        to:
            List of recipient email addresses.
        cc:
            List of CC email addresses.
        body_type:
            "HTML" or "Text".

        Returns
        -------
        The created message object from Graph (includes ``id``).
        """
        payload: dict[str, Any] = {
            "subject": subject,
            "body": {"contentType": body_type, "content": body},
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in to
            ],
            "ccRecipients": [
                {"emailAddress": {"address": addr}} for addr in cc
            ],
        }
        response = self._request(
            "POST",
            f"/users/{oid}/messages",
            oid,
            json=payload,
            expected_statuses=(201,),
        )
        message = response.json()
        logger.info(
            "GraphClient: draft created oid=%s message_id=%s",
            oid,
            message.get("id"),
        )
        return message

    def update_draft(
        self, oid: str, message_id: str, body: str, body_type: str = "HTML"
    ) -> dict[str, Any]:
        """Update the body of an existing draft message.

        Returns the updated message object.
        """
        payload: dict[str, Any] = {
            "body": {"contentType": body_type, "content": body}
        }
        response = self._request(
            "PATCH",
            f"/users/{oid}/messages/{message_id}",
            oid,
            json=payload,
            expected_statuses=(200,),
        )
        logger.info(
            "GraphClient: draft updated oid=%s message_id=%s", oid, message_id
        )
        return response.json()

    def send_draft(self, oid: str, message_id: str) -> None:
        """Send a saved draft message via the delegated Mail.Send scope.

        No application permission is used — this is a delegated call only.
        """
        self._request(
            "POST",
            f"/users/{oid}/messages/{message_id}/send",
            oid,
            expected_statuses=(202,),
        )
        logger.info(
            "GraphClient: draft sent oid=%s message_id=%s", oid, message_id
        )

    def delete_draft(self, oid: str, message_id: str) -> None:
        """Delete a draft message (e.g. on cancellation)."""
        self._request(
            "DELETE",
            f"/users/{oid}/messages/{message_id}",
            oid,
            expected_statuses=(204,),
        )
        logger.info(
            "GraphClient: draft deleted oid=%s message_id=%s", oid, message_id
        )
