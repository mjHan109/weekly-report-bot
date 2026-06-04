---
id: ADR-SEC-002
title: 팀장 등록 ACL: INITIAL_ADMIN_USER_IDS + 자가 등록 검증
status: Accepted
date: 2026-06-04
---

# ADR-SEC-002: 팀장 등록 ACL: INITIAL_ADMIN_USER_IDS + 자가 등록 검증

## 상태
확정 (Accepted)

## 맥락

팀장 등록은 권한 부여의 첫 단계이다. 누가 팀장이 될 수 있는가?

보안 우려:
- 권한 없는 사용자가 팀장으로 등록되면 안 됨
- bot framework activity는 신뢰할 수 있는가?

## 결정

**팀장 등록 ACL은 이중 게이트:**

1. **Identity Source:** Activity.from.aadObjectId만 신뢰 (카드 payload 제외)
2. **Authorization:**
   - 신규 채널: INITIAL_ADMIN_USER_IDS 또는 첫 사용자
   - 기존 채널: 현재 팀장만 전이 가능
3. **Failure on Missing Env:** INITIAL_ADMIN_USER_IDS 누락 시 시작 실패

## 근거

### 1. Bot Framework Activity는 신뢰할 수 있는 출처
- Microsoft가 검증한 JWT token
- aadObjectId는 Azure AD에서 검증됨
- 조작 불가능 (private key로 서명)

### 2. Payload는 신뢰할 수 없음
```json
// 악의적 payload (조작)
{
  "channel_id": "hacked-channel",
  "team_lead_aad_id": "attacker-aad-id"
}
```

- 클라이언트가 임의로 payload 생성 가능
- Activity context를 무시할 수 없음

### 3. INITIAL_ADMIN_USER_IDS 강제
- env var 누락 시 시작 실패
- 부재 감시 (misconfiguration 즉시 탐지)
- 운영자가 의도적으로 설정

### 4. 첫 팀장 지정의 안정성
- INITIAL_ADMIN_USER_IDS에만 있는 사용자만 첫 등록 가능
- 조직의 신뢰할 수 있는 인물 (관리자 등)

## 결과

### 긍정
- **보안:** 권한 없는 팀장 등록 불가
- **감시:** 미설정 부트스트랩 즉시 탐지
- **투명성:** INITIAL_ADMIN_USER_IDS로 초기 팀장 명시

### 부작용
- **운영:** env var 관리 필수
- **온보딩:** 첫 팀장 등록 전 환경 변수 설정 필요

## 구현

```python
# startup hook
def check_bootstrap():
    initial_admins = os.getenv("INITIAL_ADMIN_USER_IDS")
    if not initial_admins:
        raise RuntimeError(
            "INITIAL_ADMIN_USER_IDS not set. "
            "Cannot bootstrap system without initial admins."
        )

# register endpoint
async def register_team_lead(
    channel_id: str,
    activity: Activity  # Bot Framework Activity (trusted)
):
    # Activity에서만 ID 추출
    requester_aad_id = activity.from.aadObjectId

    channel = await channel_repo.find_by_channel_id(channel_id)

    if not channel:
        # 신규 채널: INITIAL_ADMIN_USER_IDS 검증
        initial_admins = os.getenv("INITIAL_ADMIN_USER_IDS").split(",")
        if requester_aad_id not in initial_admins:
            await audit_log_repo.log(
                channel_id=channel_id,
                action="unauthorized_team_lead_registration",
                actor_aad_id=requester_aad_id
            )
            raise PermissionDenied("Not authorized to register")

    else:
        # 기존 채널: 현재 팀장만
        if requester_aad_id != channel.team_lead_aad_id:
            await audit_log_repo.log(
                channel_id=channel_id,
                action="unauthorized_team_lead_transfer",
                actor_aad_id=requester_aad_id,
                details={"current_lead": channel.team_lead_aad_id}
            )
            raise PermissionDenied("Not current team lead")

    # register/transfer
    ...
```

## 감시 로그

- action: "unauthorized_team_lead_registration"
- actor_aad_id: 무단 등록 시도자
- details: { "channel_id", "timestamp" }

## 참고

- ADR-008: team lead registration (기술 관점)
- Bot Framework JWT verification (신뢰성)
