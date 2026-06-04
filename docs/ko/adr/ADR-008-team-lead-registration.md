---
id: ADR-008
title: 팀장 등록 부트스트랩: INITIAL_ADMIN_USER_IDS vs 자가 등록
status: Accepted
date: 2026-06-04
---

# ADR-008: 팀장 등록 부트스트랩: INITIAL_ADMIN_USER_IDS vs 자가 등록

## 상태
확정 (Accepted)

## 맥락

새 채널이 시스템에 추가되면 누가 팀장으로 등록하는가?

옵션 1: 관리자가 미리 env var에 등록 (INITIAL_ADMIN_USER_IDS)
옵션 2: 누구나 자가 등록 가능 (보안 위험)
옵션 3: 팀장이 자신을 등록 가능, 이후 전이만 가능

**문제:** 보안과 편의성 균형

## 결정

**이중 게이트 방식:**

1. **신규 채널 (첫 팀장 등록):**
   - INITIAL_ADMIN_USER_IDS에 있는 사용자만 등록 가능
   - 또는 자가 등록 허용 (채널에 팀장 없을 때만)
   - env var 누락 시 시작 실패

2. **기존 채널 (팀장 변경):**
   - 현재 팀장만 변경 가능 (자신의 역할을 다른 사람으로 전이)
   - 새로운 팀장이 다시 등록할 수 없음 (overwrite 방지)

### 구현 로직

```python
async def register_team_lead(
    channel_id: str,
    user_aad_id: str,  # from Activity
    activity: Activity
) -> ChannelConfig:
    # Activity에서만 user_aad_id 추출 (payload 무시)
    requester_aad_id = activity.from.aadObjectId

    # 채널 설정 조회
    channel_config = await self.channel_repo.find_by_channel_id(channel_id)

    if not channel_config:
        # 신규 채널: INITIAL_ADMIN_USER_IDS 또는 자가 등록
        initial_admins = os.getenv("INITIAL_ADMIN_USER_IDS", "").split(",")

        if requester_aad_id not in initial_admins:
            # 자가 등록 (첫 팀장이 없을 때만)
            raise PermissionDenied(
                "Not in INITIAL_ADMIN_USER_IDS. "
                "Channel must have at least one initial admin."
            )

        channel_config = ChannelConfig(
            channel_id=channel_id,
            team_lead_aad_id=requester_aad_id,
            team_name="Team"  # default
        )
    else:
        # 기존 채널: 현재 팀장만 변경 가능
        if requester_aad_id != channel_config.team_lead_aad_id:
            raise PermissionDenied(
                "Only current team lead can transfer ownership"
            )

        # 현재 팀장이 다른 사람으로 전이
        channel_config.team_lead_aad_id = user_aad_id

    await self.channel_repo.save(channel_config)
    return channel_config
```

## 근거

### 1. 보안: 권한 없는 등록 방지
- INITIAL_ADMIN_USER_IDS는 조직에서 관리
- env var 누락 시 시작 실패 → 부재 감시

### 2. 편의성: 자가 등록
- 첫 팀장이 스스로 등록 가능
- 관리자 개입 최소화
- 빠른 온보딩

### 3. 전이 보안: 현재 팀장만 변경
- 팀장이 자신의 역할을 다른 사람으로 전이
- 무단 등록 방지 (overwrite 불가)

### 4. 감시: Activity 출처 검증
- payload의 user_aad_id는 무시
- Activity.from.aadObjectId만 신뢰 (Bot Framework 검증)

## 결과

### 긍정
- **보안:** 무단 팀장 등록 방지
- **감시:** 부트스트랩 미설정 즉시 탐지 (startup failure)
- **유연성:** 첫 팀장은 자가 등록, 이후는 팀장 제어

### 부작용
- **운영 복잡도:** env var 관리 필수
- **마이그레이션:** 기존 팀장 없는 채널은 INITIAL_ADMIN_USER_IDS 설정 필요

### 제약
- **팀장 자동 감지:** 채널에서 팀장을 자동으로 판단할 수 없음 (명시적 등록 필수)
- **공동 팀장:** 현재 구조에서 1명만 가능 (2인 이상 팀장은 새 ADR 필요)

## 부트스트랩 체크리스트

- [ ] INITIAL_ADMIN_USER_IDS env var 정의 (쉼표 구분, e.g., "aad-id-1,aad-id-2")
- [ ] startup hook: INITIAL_ADMIN_USER_IDS 검증 (없으면 오류)
- [ ] team_lead_service.register_team_lead() 구현
- [ ] 감시 로그: 팀장 등록/변경 기록 (actor, target, action)
- [ ] 문서: 운영자를 위한 INITIAL_ADMIN_USER_IDS 설정 가이드

## 예시 환경 변수

```bash
# .env (production)
INITIAL_ADMIN_USER_IDS=8d8c6be0-8af4-4f9f-b5ea-8d3c2e5c3f4a,9e9d7cf1-9bg5-5g0g-c6fb-9e4d3f6d4g5b

# 또는 비어두기 (자가 등록만 허용)
INITIAL_ADMIN_USER_IDS=
```

## 참고

- ADR-SEC-002: team-lead registration ACL (보안 관점)
- Bot Framework Activity: from.aadObjectId (신뢰할 수 있는 출처)
- AuditLog: action="team_lead_registered", "team_lead_transferred"
