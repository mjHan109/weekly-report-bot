# Phase 3 Security Patches — Code Fix Recommendations

**Date:** 2026-06-04
**Author:** @security-reviewer
**Reference:** phase-3-security-report.md

Source files are not modified in this review. The code below represents changes the responsible developer must apply.

---

## Fix-A: Unify env variable name (Issue #2, ADR-SEC-002)

**Target file:** `src/adapters/teams/handlers/register_team_lead.py`

**Problem:** Line 112 reads `INITIAL_ADMIN_AAD_IDS` directly from `os.environ`.
**Correct variable name:** `INITIAL_ADMIN_USER_IDS` (matching the alias in `config.py`).

```python
# Current code (register_team_lead.py lines 110-114) — MUST CHANGE
def _is_initial_admin(aad_id: str) -> bool:
    """Check the INITIAL_ADMIN_AAD_IDS environment variable."""
    admin_ids_raw = os.environ.get("INITIAL_ADMIN_AAD_IDS", "")
    admin_ids = {aid.strip() for aid in admin_ids_raw.split(",") if aid.strip()}
    return aad_id in admin_ids

# Recommended fix — use Settings object as single source of truth
def _is_initial_admin(aad_id: str) -> bool:
    """Check INITIAL_ADMIN_USER_IDS via Settings (single source of truth)."""
    from src.infra.config import get_settings
    return aad_id in get_settings().initial_admin_user_ids
```

**Verification:** With `INITIAL_ADMIN_USER_IDS=uid1,uid2` set, a registration attempt by `uid1` on a new channel must be allowed. An attempt by `uid3` must be rejected.

---

## Fix-B: Add audit log on team lead registration failure (Issue #3, ADR-SEC-002)

**Target file:** `src/adapters/teams/handlers/register_team_lead.py`

ADR-SEC-002 required audit actions: `unauthorized_team_lead_registration`, `unauthorized_team_lead_transfer`.

```python
# Current code (lines 51-55) — no audit log on rejection
allowed, reason = await _check_registration_acl(aad_id, channel_id)
if not allowed:
    await _reply(turn_context, f"팀장 등록 권한이 없습니다. ({reason})")
    return

# Recommended fix — log security event on rejection
allowed, reason = await _check_registration_acl(aad_id, channel_id)
if not allowed:
    logger.warning(
        "SECURITY: unauthorized team lead registration attempt | "
        "aad_id=%s | channel=%s | reason=%s",
        aad_id,
        channel_id,
        reason,
    )
    # When AuditLogRepository is available, persist the event:
    # await _write_audit_log(
    #     channel_id=channel_id,
    #     action="unauthorized_team_lead_registration",
    #     actor_aad_id=aad_id,
    #     details={"reason": reason},
    # )
    await _reply(turn_context, f"팀장 등록 권한이 없습니다. ({reason})")
    return
```

**Also apply** the same audit log pattern at the `TeamLeadRegistrationError` raise point in `team_lead_service.py` lines 114–118.

---

## Fix-C: ActivityValidator channel isolation middleware (Issue #4, ADR-SEC-005)

**New file recommendation:** `src/adapters/teams/activity_validator.py`

```python
"""Activity channel isolation validator — ADR-SEC-005."""
from __future__ import annotations

import logging
from botbuilder.core import TurnContext

logger = logging.getLogger(__name__)


class ChannelMismatchError(PermissionError):
    """Raised when the activity channel_id does not match the service channel_id."""


def extract_channel_id_from_activity(turn_context: TurnContext) -> str:
    """Extract channel_id from Bot Framework activity (trusted source only).

    Prefers teamsChannelId from channelData; falls back to conversation.id.
    Never trusts a caller-supplied channel_id without cross-checking this value.

    Raises:
        ValueError: If channel_id cannot be determined from the activity.
    """
    channel_data = getattr(turn_context.activity, "channel_data", None) or {}
    teams_channel_id = (
        channel_data.get("teamsChannelId")
        if isinstance(channel_data, dict)
        else None
    )

    if teams_channel_id:
        return teams_channel_id

    conversation = getattr(turn_context.activity, "conversation", None)
    conv_id = getattr(conversation, "id", None) if conversation else None
    if conv_id:
        return conv_id

    raise ValueError("Cannot extract channel_id from Bot Framework activity.")


def assert_channel_matches(
    activity_channel_id: str,
    payload_channel_id: str,
    actor_aad_id: str,
) -> None:
    """Raise ChannelMismatchError if the two channel IDs do not match.

    Args:
        activity_channel_id: channel_id derived from Bot Framework activity
                             (trusted).
        payload_channel_id:  channel_id from request payload or query param
                             (untrusted).
        actor_aad_id:        For audit log context.

    Raises:
        ChannelMismatchError: If IDs differ. Caller must reject the request.
    """
    if activity_channel_id != payload_channel_id:
        logger.warning(
            "SECURITY: cross-channel attempt blocked | "
            "actor=%s | activity_channel=%s | payload_channel=%s",
            actor_aad_id,
            activity_channel_id,
            payload_channel_id,
        )
        raise ChannelMismatchError(
            f"Activity channel '{activity_channel_id}' does not match "
            f"payload channel '{payload_channel_id}'. Request rejected."
        )
```

**Integration points:** Call `assert_channel_matches()` in every Bot handler before passing `channel_id` to any service method. In `SubmissionService.submit()` callers and `RegisterTeamLeadHandler.handle()`, use `extract_channel_id_from_activity()` as the sole source of `channel_id`.

---

## Fix-D: Fail startup on empty APP_ID (Issue #5, ADR-SEC-007)

**Target file:** `src/api/routes/bot.py`

```python
# Current code (lines 44-51) — empty string silently accepted
_APP_ID: str = os.environ.get("MICROSOFT_APP_ID", "")
_APP_PASSWORD: str = os.environ.get("MICROSOFT_APP_PASSWORD", "")

# Recommended fix — hard fail at module load if credentials are missing
_APP_ID: str = os.environ.get("MICROSOFT_APP_ID", "")
_APP_PASSWORD: str = os.environ.get("MICROSOFT_APP_PASSWORD", "")

if not _APP_ID or not _APP_PASSWORD:
    raise RuntimeError(
        "MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD must be set. "
        "An empty App ID disables Bot Framework JWT verification entirely, "
        "violating ADR-SEC-007. "
        "For local emulator use, set USE_EMULATOR=true and handle it explicitly."
    )
```

**Alternative:** `bot.py` should read from `get_settings()` (whose fields `bot_app_id` and `bot_app_password` are already declared in `config.py` lines 41–42) instead of accessing `os.environ` directly. This eliminates the divergence between the two paths.

---

## Fix-E: HMAC timestamp freshness validation (Issue #6)

**Target file:** `src/api/dependencies.py`

```python
# Current code (lines 83-112) — no timestamp freshness check

# Recommended fix — add freshness window to verify_hmac_signature()
import time as _time

_HMAC_TIMESTAMP_TOLERANCE_SECS = 300  # 5-minute replay window

def verify_hmac_signature(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
    provided_sig: str,
) -> None:
    # 1. Timestamp freshness check (replay attack defence)
    try:
        ts_float = float(timestamp)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Scheduler-Ts header is not a valid unix timestamp.",
        )
    age = abs(_time.time() - ts_float)
    if age > _HMAC_TIMESTAMP_TOLERANCE_SECS:
        logger.warning(
            "Scheduler HMAC timestamp outside accepted window: age=%.1fs", age
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Scheduler HMAC timestamp is outside the accepted window.",
        )

    # 2. Existing HMAC signature check (unchanged)
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
```

---

## Fix Priority Summary

| Fix | Issue | Severity | Recommended Timing |
|---|---|---|---|
| Fix-A | Env variable name mismatch | High | Phase 3 immediately |
| Fix-D | Empty APP_ID accepted | High | Phase 3 immediately |
| Fix-C | ActivityValidator not implemented | High | Phase 3 immediately |
| Fix-B | Audit log on registration failure | Medium | Phase 3 |
| Fix-E | HMAC timestamp freshness | Medium | Phase 3 |
| Fix-F (Issue #7) | Redis-backed state store | Medium | Before Phase 4 deployment |
