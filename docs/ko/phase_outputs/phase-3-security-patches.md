# Phase 3 보안 패치 — 코드 수정 권고

**작성일:** 2026-06-04
**작성자:** @security-reviewer
**참조:** phase-3-security-report.md

각 Fix는 source 파일을 직접 수정하지 않는다. 아래 코드는 담당 개발자가 적용해야 할 변경 사항이다.

---

## Fix-A: env 변수 이름 통일 (이슈 #2, ADR-SEC-002)

**대상 파일:** `src/adapters/teams/handlers/register_team_lead.py`

**문제:** 라인 112에서 `INITIAL_ADMIN_AAD_IDS`를 직접 읽음.
**올바른 변수명:** `INITIAL_ADMIN_USER_IDS` (config.py alias와 동일).

```python
# 현재 코드 (register_team_lead.py 라인 110-114) — 수정 필요
def _is_initial_admin(aad_id: str) -> bool:
    """Check the INITIAL_ADMIN_AAD_IDS environment variable."""
    admin_ids_raw = os.environ.get("INITIAL_ADMIN_AAD_IDS", "")
    admin_ids = {aid.strip() for aid in admin_ids_raw.split(",") if aid.strip()}
    return aad_id in admin_ids

# 권고 수정 — Settings 객체 사용으로 단일 진실 원천(Single Source of Truth) 확보
def _is_initial_admin(aad_id: str) -> bool:
    """Check INITIAL_ADMIN_USER_IDS via Settings (single source of truth)."""
    from src.infra.config import get_settings
    return aad_id in get_settings().initial_admin_user_ids
```

**검증 조건:** `INITIAL_ADMIN_USER_IDS=uid1,uid2` 환경변수 설정 후 `uid1`으로 신규 채널에 팀장 등록 시도 시 허용되어야 한다. `uid3`으로 시도 시 거부되어야 한다.

---

## Fix-B: 팀장 등록 실패 감사 로그 추가 (이슈 #3, ADR-SEC-002)

**대상 파일:** `src/adapters/teams/handlers/register_team_lead.py`

ADR-SEC-002가 요구하는 감사 action: `unauthorized_team_lead_registration`, `unauthorized_team_lead_transfer`.

```python
# 현재 코드 (라인 51-55) — 감사 로그 없음
allowed, reason = await _check_registration_acl(aad_id, channel_id)
if not allowed:
    await _reply(turn_context, f"팀장 등록 권한이 없습니다. ({reason})")
    return

# 권고 수정 — 거부 시 감사 로그 기록
allowed, reason = await _check_registration_acl(aad_id, channel_id)
if not allowed:
    logger.warning(
        "SECURITY: unauthorized team lead registration attempt | "
        "aad_id=%s | channel=%s | reason=%s",
        aad_id,
        channel_id,
        reason,
    )
    # AuditLog DB 기록 (audit_log_repo 구현 시)
    # await _write_audit_log(
    #     channel_id=channel_id,
    #     action="unauthorized_team_lead_registration",
    #     actor_aad_id=aad_id,
    #     details={"reason": reason},
    # )
    await _reply(turn_context, f"팀장 등록 권한이 없습니다. ({reason})")
    return
```

**추가:** `team_lead_service.py` 라인 114–118의 `TeamLeadRegistrationError` raise 지점에도 동일한 감사 로그 기록 패턴 적용.

---

## Fix-C: ActivityValidator 채널 격리 미들웨어 (이슈 #4, ADR-SEC-005)

**신규 파일 권고:** `src/adapters/teams/activity_validator.py`

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

    Uses teamsChannelId from channelData if available; falls back to
    conversation.id. Never trusts a caller-supplied channel_id parameter
    without cross-checking this value.

    Raises:
        ValueError: If channel_id cannot be determined from the activity.
    """
    channel_data = getattr(turn_context.activity, "channel_data", None) or {}
    teams_channel_id = channel_data.get("teamsChannelId") if isinstance(channel_data, dict) else None

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

**적용 위치:** `SubmissionService.submit()` 호출 전 핸들러에서, 그리고 `RegisterTeamLeadHandler.handle()` 내 `_get_channel_id()` 호출 직후에 `assert_channel_matches()`를 삽입한다.

---

## Fix-D: APP_ID 빈 문자열 시작 시 실패 처리 (이슈 #5, ADR-SEC-007)

**대상 파일:** `src/api/routes/bot.py`

```python
# 현재 코드 (라인 44-51) — 빈 문자열 묵인
_APP_ID: str = os.environ.get("MICROSOFT_APP_ID", "")
_APP_PASSWORD: str = os.environ.get("MICROSOFT_APP_PASSWORD", "")

# 권고 수정 — 시작 시 필수 값 강제
_APP_ID: str = os.environ.get("MICROSOFT_APP_ID", "")
_APP_PASSWORD: str = os.environ.get("MICROSOFT_APP_PASSWORD", "")

if not _APP_ID or not _APP_PASSWORD:
    raise RuntimeError(
        "MICROSOFT_APP_ID and MICROSOFT_APP_PASSWORD must be set. "
        "An empty App ID disables Bot Framework JWT verification entirely, "
        "which violates ADR-SEC-007. "
        "For local development with the emulator, set USE_EMULATOR=true and "
        "handle that flag explicitly."
    )
```

**대안:** `src/infra/config.py`의 `Settings`에 `bot_app_id`와 `bot_app_password` 필드 검증을 추가하고 `bot.py`는 `get_settings()`에서 읽도록 변경한다. (현재 config.py 라인 41–42에 이미 필드가 선언되어 있으므로 bot.py가 `os.environ` 직접 접근 대신 Settings를 사용하면 된다.)

---

## Fix-E: HMAC 타임스탬프 신선도 검증 (이슈 #6)

**대상 파일:** `src/api/dependencies.py`

```python
# 현재 코드 (라인 83-112) — timestamp 신선도 미검증

# 권고 수정 — verify_hmac_signature() 함수에 신선도 검사 추가
import time as _time

_HMAC_TIMESTAMP_TOLERANCE_SECS = 300  # 5분

def verify_hmac_signature(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
    provided_sig: str,
) -> None:
    # 1. 타임스탬프 신선도 검증 (replay attack 방어)
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
            "Scheduler HMAC timestamp too old or in future: age=%.1fs", age
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Scheduler HMAC timestamp is outside the accepted window.",
        )

    # 2. 기존 HMAC 서명 검증 (변경 없음)
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

## Fix 우선순위 요약

| Fix | 이슈 | 심각도 | 권고 처리 시점 |
|---|---|---|---|
| Fix-A | env 변수 이름 불일치 | 높음 | Phase 3 즉시 |
| Fix-D | APP_ID 빈 문자열 | 높음 | Phase 3 즉시 |
| Fix-C | ActivityValidator 미구현 | 높음 | Phase 3 즉시 |
| Fix-B | 감사 로그 누락 | 중간 | Phase 3 |
| Fix-E | HMAC 타임스탬프 신선도 | 중간 | Phase 3 |
| Fix-F (이슈 #7) | Redis state 저장소 | 중간 | Phase 4 배포 전 |
