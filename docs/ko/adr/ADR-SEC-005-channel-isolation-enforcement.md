---
id: ADR-SEC-005
title: 채널 격리 강제: ORM + 감시 로그
status: Accepted
date: 2026-06-04
---

# ADR-SEC-005: 채널 격리 강제: ORM + 감시 로그

## 상태
확정 (Accepted)

## 맥락

ADR-002는 channel_id를 파티션 키로 정의했다. 이것을 **강제**하는 메커니즘은?

옵션 1: Service 계층에서만 검증 (channel_id 필수 인수)
옵션 2: ORM 계층에서 강제 (ChannelScopedRepository)
옵션 3: 옵션 1 + 옵션 2 (다층 방어)

## 결정

**ORM 계층에서 강제하고, 크로스 채널 시도는 감시 로그에 기록한다.**

### 강제 메커니즘

**ChannelScopedRepository base class:**
```python
class ChannelScopedRepository(Generic[T]):
    async def find_by_id(self, channel_id: str, id: UUID) -> Optional[T]:
        """Find entity, MANDATORY channel_id"""
        stmt = select(self.model).where(
            self.model.channel_id == channel_id,
            self.model.id == id
        )
        return await session.scalar(stmt)

    # find_all_for_channel만 존재, find_all은 없음
    async def find_all_for_channel(self, channel_id: str) -> List[T]:
        """Find all for a channel, MANDATORY channel_id"""
        stmt = select(self.model).where(
            self.model.channel_id == channel_id
        )
        return await session.scalars(stmt).all()

    # update_for_channel만 존재
    async def update_for_channel(
        self, channel_id: str, id: UUID, **updates
    ) -> Optional[T]:
        stmt = (
            update(self.model)
            .where(
                self.model.channel_id == channel_id,
                self.model.id == id
            )
            .values(**updates)
            .returning(self.model)
        )
        return await session.scalar(stmt)
```

### 크로스 채널 시도 감시

```python
# Service 계층에서 ActivityValidator 미들웨어
async def validate_channel_context(activity: Activity, request_channel_id: str):
    """
    Validate Activity channel_id matches request channel_id.
    Log if mismatch.
    """
    activity_channel_id = activity.channelData.teamsChannelId

    if activity_channel_id != request_channel_id:
        # Cross-channel attempt
        await audit_log_repo.log(
            channel_id=activity_channel_id,  # actual channel
            action="cross_channel_attempt",
            actor_aad_id=activity.from.aadObjectId,
            details={
                "requested_channel_id": request_channel_id,
                "actual_channel_id": activity_channel_id
            }
        )
        raise PermissionDenied(
            "Activity channel does not match request"
        )
```

## 근거

### 1. ORM 계층 강제의 이점
- 개발자가 실수로 channel_id 없이 쿼리할 수 없음
- 메서드 시그니처가 강제 (IDE autocomplete도 도움)
- 코드 리뷰 시 누락 방지

### 2. 감시 로그의 중요성
- 크로스 채널 시도 탐지
- 보안 사건 대응 시 증거
- 악의적 사용자 식별

### 3. 다층 방어
- Service 계층: 비즈니스 로직 검증
- ORM 계층: 데이터 접근 강제
- 감시 로그: 사건 기록

## 결과

### 긍정
- **보안:** 크로스 채널 접근 기술적으로 불가능
- **개발 안전성:** 메서드 시그니처로 강제
- **감시:** 크로스 채널 시도 기록

### 부작용
- **복잡도:** 모든 repository method에 channel_id 전달
- **테스트:** channel_id별 격리된 test data 관리

## 구현 체크리스트

- [ ] ChannelScopedRepository base class 정의
- [ ] 모든 repository가 ChannelScopedRepository 상속
- [ ] find_all, update (without channel_id) 제거
- [ ] ActivityValidator middleware 구현
- [ ] Audit log schema: action="cross_channel_attempt"
- [ ] Test: channel_id mismatch 케이스

## 감시 로그 예시

```json
{
  "channel_id": "channel-A",
  "action": "cross_channel_attempt",
  "actor_aad_id": "user-123",
  "details": {
    "requested_channel_id": "channel-B",
    "actual_channel_id": "channel-A"
  },
  "timestamp": "2026-06-04T10:30:00Z"
}
```

## 참고

- ADR-002: channel isolation as partition key (설계)
- ChannelScopedRepository: base class pattern
