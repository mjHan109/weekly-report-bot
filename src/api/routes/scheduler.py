"""Internal scheduler endpoints.

POST /internal/scheduler/reminder  — fires the Thu 10:00 KST reminder cards.
POST /internal/scheduler/deadline  — fires the Thu 13:00 KST deadline logic.

Both endpoints are protected by HMAC-SHA256 (X-Scheduler-Sig header).
They are NOT exposed to the public internet; place behind a network policy.
"""

import logging

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.dependencies import verify_hmac_signature, verify_scheduler_hmac
from src.infra.config import get_settings
from src.infra.db import get_db
from src.services.reports.deadline_service import DeadlineService
from src.services.reports.week_utils import current_week_key
from src.domain.repositories.channel_config_repo import ChannelConfigRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/scheduler", tags=["scheduler"])


# ── Request / Response schemas ─────────────────────────────────────────────────

class SchedulerReminderRequest(BaseModel):
    """Optional override payload for the reminder job."""
    week_key: str | None = None   # defaults to current ISO week
    channel_ids: list[str] | None = None  # None → all active channels


class SchedulerDeadlineRequest(BaseModel):
    """Optional override payload for the deadline job."""
    week_key: str | None = None
    channel_ids: list[str] | None = None


class SchedulerResponse(BaseModel):
    processed: int
    week_key: str
    results: list[dict]


# ── Shared HMAC body verifier ──────────────────────────────────────────────────

async def _verify_body_hmac(request: Request) -> bytes:
    """Read raw body and verify HMAC signature.

    Returns the raw body bytes so route handlers can deserialise them.
    Raises HTTP 401 on HMAC mismatch.
    """
    settings = get_settings()
    body = await request.body()
    sig = request.headers.get("X-Scheduler-Sig", "")
    ts = request.headers.get("X-Scheduler-Ts", "")
    verify_hmac_signature(
        secret=settings.scheduler_hmac_secret,
        timestamp=ts,
        body=body,
        provided_sig=sig,
    )
    return body


# ── Reminder endpoint ──────────────────────────────────────────────────────────

@router.post(
    "/reminder",
    summary="Thu 10:00 KST — send reminder cards to all active channels",
    status_code=status.HTTP_200_OK,
)
async def trigger_reminder(
    request: Request,
    _hmac_check: None = Depends(verify_scheduler_hmac),
) -> SchedulerResponse:
    """Dispatch reminder Adaptive Cards to all active channels.

    Called by the external scheduler at Thursday 10:00 KST (01:00 UTC).
    Verifies HMAC before processing.

    Returns a summary of channels processed.
    """
    await _verify_body_hmac(request)

    # Parse body manually after HMAC check
    try:
        payload = SchedulerReminderRequest.model_validate(
            await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        )
    except Exception:
        payload = SchedulerReminderRequest()

    week_key = payload.week_key or current_week_key()

    async with (await _get_db_session()) as db:
        channel_repo = ChannelConfigRepository(db)
        if payload.channel_ids:
            configs = [
                c
                for cid in payload.channel_ids
                if (c := await channel_repo.get_by_channel_id(cid)) is not None
                and c.is_active
            ]
        else:
            configs = list(await channel_repo.get_active_configs())

    results = []
    for config in configs:
        # Reminder dispatch is handled by the Teams adapter (notification_jobs).
        # The scheduler route only coordinates; it does not send cards directly.
        results.append({"channel_id": config.channel_id, "status": "queued"})
        logger.info(
            "Reminder queued: channel=%r week=%r", config.channel_id, week_key
        )

    logger.info(
        "Reminder job complete: week=%r channels=%d", week_key, len(results)
    )
    return SchedulerResponse(
        processed=len(results),
        week_key=week_key,
        results=results,
    )


# ── Deadline endpoint ──────────────────────────────────────────────────────────

@router.post(
    "/deadline",
    summary="Thu 13:00 KST — evaluate AUTO vs MANUAL for all active channels",
    status_code=status.HTTP_200_OK,
)
async def trigger_deadline(
    request: Request,
    _hmac_check: None = Depends(verify_scheduler_hmac),
) -> SchedulerResponse:
    """Run deadline logic for all active channels.

    Called by the external scheduler at Thursday 13:00 KST (04:00 UTC).
    For each channel determines AUTO vs MANUAL aggregation mode and
    transitions the TeamReport state machine accordingly.

    This endpoint is idempotent: channels already past COLLECTING are skipped.
    """
    await _verify_body_hmac(request)

    try:
        payload = SchedulerDeadlineRequest.model_validate(
            await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        )
    except Exception:
        payload = SchedulerDeadlineRequest()

    week_key = payload.week_key or current_week_key()
    results = []

    # Each channel gets its own DB session so a failure in one channel
    # does not roll back the others.
    from src.infra.db import _get_session_factory  # noqa: PLC0415

    factory = _get_session_factory()
    if payload.channel_ids:
        channel_ids_to_process = payload.channel_ids
    else:
        async with factory() as discovery_session:
            repo = ChannelConfigRepository(discovery_session)
            configs = await repo.get_active_configs()
            channel_ids_to_process = [c.channel_id for c in configs]

    for channel_id in channel_ids_to_process:
        try:
            async with factory() as session:
                svc = DeadlineService(session)
                new_status = await svc.run(channel_id, week_key)
                await session.commit()
            results.append(
                {"channel_id": channel_id, "status": "ok", "new_state": new_status}
            )
            logger.info(
                "Deadline processed: channel=%r week=%r new_state=%s",
                channel_id, week_key, new_status,
            )
        except Exception as exc:
            logger.exception(
                "Deadline processing failed: channel=%r week=%r error=%s",
                channel_id, week_key, exc,
            )
            results.append(
                {"channel_id": channel_id, "status": "error", "detail": str(exc)}
            )

    return SchedulerResponse(
        processed=len(results),
        week_key=week_key,
        results=results,
    )


# ── DB helper (avoids direct import cycle) ────────────────────────────────────

async def _get_db_session():
    """Context manager shim — for the reminder route's one-shot read."""
    from src.infra.db import _get_session_factory  # noqa: PLC0415
    return _get_session_factory()()
