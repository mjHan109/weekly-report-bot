---
id: ADR-SEC-003
title: 메일 발송 삼중 게이트: 상태 + 완성도 + 권한
status: Accepted
date: 2026-06-04
---

# ADR-SEC-003: 메일 발송 삼중 게이트: 상태 + 완성도 + 권한

## 상태
확정 (Accepted)

## 맥락

취합된 팀 보고를 메일로 발송할 때, 다음을 확인해야 한다:

1. **상태 게이트:** TeamReport.status == AWAITING_APPROVAL인가?
2. **완성도 게이트:** 모든 팀원이 보고를 제출했는가?
3. **권한 게이트:** 행위자가 팀장인가?

**문제:** 이 게이트들을 클라이언트(카드)에만 표시하면, 카드 상태를 조작해서 무단 메일 발송이 가능한가?

## 결정

**메일 발송 직전에 서버에서 3가지 조건을 재검증한다. 카드 state는 신뢰하지 않는다.**

```python
async def send_team_report(
    channel_id: str,
    team_report_id: UUID,
    actor_aad_id: str,  # from Activity
    activity: Activity
) -> Mail:
    # Gate 1: 상태 검증
    team_report = await team_report_repo.find_by_id(channel_id, team_report_id)
    if team_report.status != TeamReportStatus.AWAITING_APPROVAL:
        raise ConflictError("Report not in approval-waiting state")

    # Gate 2: 완성도 검증
    targets = await channel_target_repo.find_all_for_channel(channel_id)
    for target in targets:
        report = await personal_report_repo.find_by_channel_owner_week(
            channel_id, target.target_aad_id, team_report.week_key
        )
        if not report or report.status != ReportStatus.SUBMITTED:
            raise ConflictError(f"Missing report from {target.target_aad_id}")

    # Gate 3: 권한 검증
    channel = await channel_repo.find_by_channel_id(channel_id)
    if actor_aad_id != channel.team_lead_aad_id:
        raise PermissionDenied("Not authorized as team lead")

    # 모든 게이트 통과 → 메일 발송
    mail = await mail_send_service.send(channel_id, team_report_id, actor_aad_id)
    return mail
```

## 근거

### 1. 상태 재현 공격 방지
- 클라이언트 카드 상태는 조작 가능
- 브라우저 개발자 도구에서 카드 JSON 수정 가능
- "AWAITING_APPROVAL" 상태로 위조하여 메일 발송 시도

### 2. DB 상태만 신뢰
- 서버가 관리하는 state는 신뢰할 수 있음
- 클라이언트 상태는 display용일 뿐

### 3. 완성도 재검증
- 메일 발송 후 개인 보고 추가 가능한 race condition 방지
- 발송 직전에 모든 보고가 있는지 확인

### 4. 권한 재검증
- Activity를 다시 검증하여 권한 위조 방지
- 팀장 변경 후 옛날 Activity로 발송 시도 방지

## 결과

### 긍정
- **보안:** 상태 조작으로 메일 발송 불가능
- **데이터 무결성:** 완성도 보장
- **권한 명확:** 팀장만 발송 가능

### 부작용
- **성능:** 메일 발송 전 3회 DB 조회 필요
- **복잡도:** 3개 조건 검증 로직
- **Deadlock 위험:** 동시성 높을 시 lock contention

### 제약
- **Race Condition:** 완성도 검증 후 발송 전에 보고 추가되면?
  → Transaction 또는 optimistic lock 필요

## 구현 세부사항

### Transaction 보호

```python
async def send_team_report(...) -> Mail:
    async with db.transaction():
        # Gate 1, 2, 3 검증
        ...

        # 메일 발송 (Graph API)
        # 만약 실패하면 transaction rollback
        ...

        # TeamReport.status = MAIL_SENT 업데이트
        ...
```

### Optimistic Lock

```python
class TeamReport:
    version: int  # optimistic lock

async def send_team_report(...):
    # ... gates ...

    # UPDATE with version check
    updated = await team_report_repo.update_with_version(
        channel_id,
        team_report_id,
        new_status=TeamReportStatus.MAIL_SENT,
        expected_version=team_report.version
    )

    if not updated:
        raise ConflictError("Report was modified")
```

## 감시 로그

- action: "mail_send_attempted"
- gates_passed: [1, 2, 3] or specific failure
- actor_aad_id: 시도자
- team_report_id: 대상 보고

## 참고

- ADR-SEC-003 메일 발송 삼중 게이트 (보안 enforcer)
