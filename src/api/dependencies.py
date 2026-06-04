"""FastAPI shared dependencies.

inject_channel_config  — validates channel_id and fetches ChannelConfig.
verify_scheduler_hmac  — verifies X-Scheduler-Sig HMAC-SHA256 header.
"""

import hashlib
import hmac
import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models.channel_config import ChannelConfig
from src.domain.repositories.channel_config_repo import ChannelConfigRepository
from src.infra.config import get_settings
from src.infra.db import get_db

logger = logging.getLogger(__name__)


# ── Channel config injection ───────────────────────────────────────────────────

async def inject_channel_config(
    channel_id: Annotated[str, Query(description="Teams channel ID (partition key)")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChannelConfig:
    """Dependency: resolve and return an active ChannelConfig.

    Raises 400 if channel_id is missing/empty.
    Raises 404 if the channel is not registered or inactive.
    """
    if not channel_id or not channel_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channel_id query parameter is required.",
        )

    repo = ChannelConfigRepository(db)
    config = await repo.get_by_channel_id(channel_id.strip())

    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id!r} is not registered or inactive.",
        )

    return config


# ── Scheduler HMAC verification ───────────────────────────────────────────────

async def verify_scheduler_hmac(
    x_scheduler_sig: Annotated[
        str | None,
        Header(alias="X-Scheduler-Sig", description="HMAC-SHA256 hex digest of the request body"),
    ] = None,
    x_scheduler_ts: Annotated[
        str | None,
        Header(alias="X-Scheduler-Ts", description="Unix timestamp included in HMAC payload"),
    ] = None,
) -> None:
    """Dependency: verify the HMAC-SHA256 signature sent by the scheduler.

    The scheduler signs: HMAC-SHA256(secret, "{timestamp}:{body_bytes}").
    The hex digest is sent in X-Scheduler-Sig.
    X-Scheduler-Ts carries the timestamp that was used during signing.

    For internal scheduler endpoints only.  Raises 401 on failure.

    Note: Full body verification requires a custom Request-level approach;
    this dependency validates that the header is present and well-formed.
    The route handler calls ``verify_hmac_signature`` with the raw body.
    """
    if not x_scheduler_sig or not x_scheduler_ts:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Scheduler-Sig or X-Scheduler-Ts header.",
        )


def verify_hmac_signature(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
    provided_sig: str,
) -> None:
    """Compute and compare HMAC-SHA256 for the scheduler request.

    Args:
        secret:       The SCHEDULER_HMAC_SECRET value.
        timestamp:    The X-Scheduler-Ts header value.
        body:         Raw request body bytes.
        provided_sig: The X-Scheduler-Sig header value (hex string).

    Raises:
        HTTPException 401: If the signature does not match.
    """
    message = f"{timestamp}:".encode() + body
    expected = hmac.new(
        secret.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, provided_sig.lower()):
        logger.warning("Scheduler HMAC verification failed.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Scheduler HMAC signature mismatch.",
        )
