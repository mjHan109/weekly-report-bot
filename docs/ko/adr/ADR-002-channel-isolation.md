---
id: ADR-002
title: 채널 격리: 파티션 키로서의 channel_id
status: Accepted
date: 2026-06-04
---

# ADR-002: 채널 격리: 파티션 키로서의 channel_id

## 상태
확정 (Accepted)

## 맥락

프로젝트 요구사항: 각 Teams 채널은 독립적인 팀 보고 시스템을 운영한다. 채널 A의 데이터는 채널 B의 사용자가 절대 접근할 수 없어야 한다.

이를 구현하는 방식:
1. **애플리케이션 계층:** 각 API endpoint에서 channel_id 검증
2. **ORM 계층:** 모든 쿼리에 channel_id 필터링
3. **DB 파티션 계층:** 물리적 파티션 (cloud-native 고려)

어느 계층까지 강제할 것인가?

## 결정

**channel_id를 모든 테넌트 범위 데이터베이스 테이블의 파티션 키로 정의하고, ChannelScopedRepository 기본 클래스를 통해 ORM 계층에서 강제한다.**

- 모든 데이터 조회 메서드는 channel_id를 첫 번째 인수로 가진다.
- channel_id 없는 쿼리는 메서드 시그니처 자체로 불가능하다.
- Bot Framework Activity에서만 channel_id를 추출한다 (신뢰할 수 있는 출처).
- 카드 payload, 사용자 입력 channel_id는 무시한다.

## 근거

### 1. 다층 방어 (Defense in Depth)
- 애플리케이션 코드 버그 가능성 있음 → ORM 강제로 2차 방어
- ORM 쿼리 누락 가능성 있음 → DB 파티션으로 3차 방어

### 2. ORM 메서드 시그니처 강제
```python
class ChannelScopedRepository:
    async def find_by_id(self, channel_id: str, id: UUID) -> Optional[T]:
        # channel_id 필수, 생략 불가

    async def find_all(self, channel_id: str) -> List[T]:
        # 이 메서드는 존재하지 않음: 개발자가 find_all_for_channel 사용 강제
```

- 메서드 시그니처가 channel_id 강제
- IDE 자동완성에서 channel_id 없는 호출 추천 불가
- 개발자 실수 방지

### 3. Bot Framework Activity는 신뢰할 수 있는 출처
- Bot Framework는 Microsoft가 검증한 Activity 제공
- Activity.channelData.teamsChannelId는 봇이 수신한 채널
- Activity.from.aadObjectId는 봇이 검증한 발신자
- 클라이언트 payload는 신뢰하지 않음

### 4. 감시 로그 (Audit)
- 크로스 채널 접근 시도는 AuditLog 기록
- 보안 팀이 이상 패턴 감지 가능

## 결과

### 긍정
- **보안:** 채널 격리 보장, 우발적 크로스 채널 접근 불가
- **개발 신뢰성:** ORM이 자동으로 필터링, 쿼리 누락 방지
- **감시:** 모든 크로스 채널 시도 기록
- **확장성:** cloud-native DB (Spanner, DynamoDB 등)로 파티션 key 활용 가능

### 부작용
- **성능:** 모든 쿼리가 channel_id로 필터링 → 인덱스 전략 중요
- **복잡도:** 모든 repository method에 channel_id 전달 필요
- **테스트:** 각 channel_id마다 격리된 테스트 데이터 관리

### 제약
- 채널 간 보고서 비교 불가능 (예: 부서별 비교 보고)
- 향후 다채널 analytics 기능 불가능 (새 ADR 필요)

## 구현 예시

```python
# Layer 4: Domain/Repository
class ChannelScopedRepository(Generic[T]):
    async def find_by_id(self, channel_id: str, id: UUID) -> Optional[T]:
        return await session.scalar(
            select(self.model)
            .where(self.model.channel_id == channel_id)
            .where(self.model.id == id)
        )

    async def find_all_for_channel(self, channel_id: str) -> List[T]:
        return await session.scalars(
            select(self.model).where(self.model.channel_id == channel_id)
        ).all()

# Layer 3: Service
class SubmissionService:
    async def submit(self, channel_id: str, owner_aad_id: str,
                     week_key: str, content: str) -> PersonalReport:
        # channel_id는 Bot Framework Activity에서만 추출
        # repository 호출 시 첫 인수로 전달
        existing_report = await self.report_repo.find_by_channel_owner_week(
            channel_id,  # 첫 인수: 필수
            owner_aad_id,
            week_key
        )
        ...

# Layer 2: API
@router.post("/api/reports/submit")
async def submit_report(activity: Activity, request: SubmitRequest):
    # Activity에서만 channel_id 추출
    channel_id = activity.channelData.teamsChannelId
    owner_aad_id = activity.from.aadObjectId

    # request payload의 channel_id는 무시
    report = await submission_service.submit(
        channel_id,  # Activity 출처
        owner_aad_id,
        request.week_key,
        request.content
    )
```

## 참고

- ADR-005: 채널 격리 enforcement (보안 관점)
- [docs/ko/phase_outputs/phase-1-architecture.md](../../phase_outputs/phase-1-architecture.md) — Layer 4 참고
