"""Slack notification helpers for Microsoft Graph auth errors.

When a Graph API call fails due to token expiry or missing consent,
these helpers send a user-friendly ephemeral message guiding the team lead
through re-authentication.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_REAUTH_MESSAGE = (
    "🔐 *Outlook 인증이 만료되었습니다.*\n\n"
    "팀장 계정의 Microsoft 인증을 다시 완료해야 메일 기능을 사용할 수 있습니다.\n\n"
    "아래 단계로 재인증하세요:\n"
    "1. 관리자에게 `/재인증` 링크를 요청하거나\n"
    "2. 봇 관리 페이지에서 *Microsoft 로그인* 버튼을 클릭하세요.\n\n"
    "_문제가 계속되면 IT 담당자에게 문의하세요._"
)

_RATE_LIMIT_MESSAGE = (
    "⏳ *Microsoft Graph API 요청 한도를 초과했습니다.*\n\n"
    "잠시 후 다시 시도해주세요. (통상 1~2분 대기)"
)

_GRAPH_ERROR_MESSAGE = (
    "❌ *Microsoft Graph API 오류가 발생했습니다.*\n\n"
    "오류 내용: {detail}\n\n"
    "문제가 지속되면 IT 담당자에게 문의하세요."
)


async def notify_token_expired(channel_id: str, user_id: str, client) -> None:
    """Send an ephemeral reauth guidance message to the user."""
    try:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=_REAUTH_MESSAGE,
        )
    except Exception as exc:
        logger.warning("notify_token_expired: failed to send ephemeral: %s", exc)


async def notify_rate_limited(channel_id: str, user_id: str, client) -> None:
    """Inform the user that Graph API rate limit was hit."""
    try:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=_RATE_LIMIT_MESSAGE,
        )
    except Exception as exc:
        logger.warning("notify_rate_limited: failed to send ephemeral: %s", exc)


async def notify_graph_error(
    channel_id: str, user_id: str, client, *, detail: str
) -> None:
    """Send a generic Graph API error message with detail."""
    try:
        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=_GRAPH_ERROR_MESSAGE.format(detail=detail),
        )
    except Exception as exc:
        logger.warning("notify_graph_error: failed to send ephemeral: %s", exc)


def is_token_error(exc: Exception) -> bool:
    """Return True if exc is a Graph token unavailability or refresh error."""
    try:
        from src.services.mail.token_manager import TokenUnavailableError, TokenRefreshError
        return isinstance(exc, (TokenUnavailableError, TokenRefreshError))
    except ImportError:
        return False


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True if exc is a Graph 429 rate limit error."""
    try:
        from src.services.mail.graph_client import GraphAPIError
        return isinstance(exc, GraphAPIError) and exc.status_code == 429
    except ImportError:
        return False
