---
id: ADR-006
title: 대리 제출 금지: Reporter Identity Pinning
status: Accepted
date: 2026-06-04
---

# ADR-006: 대리 제출 금지: Reporter Identity Pinning

## 상태
확정 (Accepted)

## 맥락

프로젝트 요구사항에서 명확하게 정의된 사항:
**팀장은 미제출자를 대신해서 보고를 제출할 수 없다. 미제출자는 본인이 늦게라도 제출해야 한다.**

기술적 구현 방식:

옵션 1: 팀장이 다른 사람 이름으로 제출 가능 (추적 레코드만 유지)
옵션 2: 팀장 대리 제출 불가 (hardcoded invariant)
옵션 3: 정책 설정 가능 (채널별로 다름)

## 결정

**대리 제출은 불가능한 hardcoded invariant이다. activity.from.aadObjectId == PersonalReport.owner_aad_id 를 반드시 만족해야 한다.**

submission_service.submit() 내에서:
```python
if activity.from.aadObjectId != report_slot.owner_aad_id:
    raise PermissionDenied("No proxy submission allowed")
```

위반 시:
- HTTP 403 Forbidden 응답
- AuditLog 기록: action="proxy_submit_attempt"
- 보안 팀에 알림 (필요 시)

## 근거

### 1. 책임 추적성 (Accountability)
- 누가 보고를 제출했는가가 명확해야 함
- 팀장이 다른 사람 이름으로 제출하면 추적 불가능
- 조직 감시(compliance) 요구사항

### 2. 보고의 신뢰성
- "내가 작성한 보고"인지 "팀장이 대신 작성한 보고"인지 구분 필요
- 대리 제출 시 내용의 정확성 보장 불가
- 팀장의 편향된 작성 가능성

### 3. 정책 명확성
- 요구사항에서 "본인 제출"로 명확히 정의
- 운영 정책: 미제출자는 자신이 책임짐
- 팀장은 독려/독촉만 가능

### 4. 감시(Audit) 추적
- 모든 제출 기록에 aadObjectId 저장
- 법적 분쟁 시 증거 자료로 활용 가능

## 결과

### 긍정
- **책임 명확:** 누가 제출했는가 불명확하지 않음
- **정책 강제:** 코드 자체가 정책을 구현
- **감시:** 대리 제출 시도 탐지 가능

### 부작용
- **팀장 부담:** 미제출자 독려해도 본인이 제출 안 하면 끝
- **마감 연장 불가:** 팀장이 대신 제출할 수 없어 마감 재검토 불가
- **운영 유연성:** 예외 상황 대응 어려움 (새 ADR 필요)

### 제약
- **변경 정책:** 이 invariant는 hardcoded이므로 변경 시 코드 수정 필수
- **향후 feature:** "팀장 등록자 대리 제출" 같은 기능 추가 시 새 ADR 필요

## 구현 예시

```python
# Layer 3: Service
class SubmissionService:
    async def submit(
        self,
        channel_id: str,
        activity: Activity,  # Bot Framework Activity
        week_key: str,
        content: str
    ) -> PersonalReport:
        # Activity에서 추출한 발신자
        owner_aad_id = activity.from.aadObjectId

        # 보고 슬롯 조회 (해당 owner_aad_id의 슬롯)
        report_slot = await self.slot_repo.find_by_channel_owner_week(
            channel_id,
            owner_aad_id,
            week_key
        )

        if not report_slot:
            raise NotFound("No report slot for this user")

        # ADR-006: 대리 제출 금지
        # Activity 발신자와 슬롯 소유자 반드시 일치
        if activity.from.aadObjectId != report_slot.owner_aad_id:
            # 보안 감시 로그
            await self.audit_log_repo.log(
                channel_id=channel_id,
                action="proxy_submit_attempt",
                actor_aad_id=activity.from.aadObjectId,
                details={
                    "target_owner_aad_id": report_slot.owner_aad_id,
                    "week_key": week_key
                }
            )
            raise PermissionDenied(
                "Proxy submission not allowed. Please submit your own report."
            )

        # 제출 후 submitted_after_deadline 판단
        now_kst = datetime.now(timezone("Asia/Seoul"))
        deadline = self._get_week_deadline(week_key)  # Thu 13:00 KST
        submitted_after_deadline = now_kst > deadline

        # PersonalReport 생성
        report = PersonalReport(
            channel_id=channel_id,
            report_slot_id=report_slot.id,
            owner_aad_id=owner_aad_id,
            week_key=week_key,
            content=content,
            submitted_at=now_kst,
            submitted_after_deadline=submitted_after_deadline,
            status=ReportStatus.SUBMITTED
        )

        await self.report_repo.save(report)

        # Late submit event
        if submitted_after_deadline:
            await self.event_bus.emit(LateSubmissionEvent(...))

        return report
```

## 참고

- [05_project_decisions.md](../../05_project_decisions.md) — "팀장 대리 제출 없음" 확정 사항
- ADR-SEC-006: no proxy submission (보안 관점)
- AuditLog: proxy_submit_attempt 감시
