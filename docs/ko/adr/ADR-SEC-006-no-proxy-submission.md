---
id: ADR-SEC-006
title: 대리 제출 금지: Reporter Identity Pinning (보안 관점)
status: Accepted
date: 2026-06-04
---

# ADR-SEC-006: 대리 제출 금지: Reporter Identity Pinning (보안 관점)

## 상태
확정 (Accepted)

## 맥락

ADR-006은 기술적 결정이고, 본 ADR-SEC-006은 보안 관점이다.

**대리 제출 금지는 hardcoded invariant이다.**

## 결정

**activity.from.aadObjectId == report_slot.owner_aad_id 반드시 만족. 이 불변식은 변경 불가능하다.**

### 검증 로직 (변경 불가능)

```python
# submission_service.submit() 내
if activity.from.aadObjectId != report_slot.owner_aad_id:
    # 무조건 거부
    raise PermissionDenied("No proxy submission allowed")
    # 이 로직은 new ADR 없이는 변경 불가
```

## 근거

### 1. 보안 정책 (Policy as Code)
- "팀장 대리 제출 없음"을 코드로 강제
- 정책 변경 시 ADR 검토 필수 (사회적 계약)

### 2. 책임 추적성 (Accountability)
- 보고서 저자 = 제출자 (항상 일치)
- 저자를 부정할 수 없음

### 3. 규정 준수 (Compliance)
- 감시 로그: 모든 보고 제출 기록
- "내가 아니라 팀장이 제출했어" 변명 불가능

### 4. 사회적 계약
- 개발 팀과 조직이 합의한 보안 정책
- Hardcoded이므로 "예외"를 구실로 우회 불가능

## 결과

### 긍정
- **정책 강화:** 코드가 정책 강제
- **무변증성:** 정책이 명시적이고 불변
- **감시:** 모든 대리 제출 시도 탐지

### 부작용
- **운영 경직성:** 예외 상황 대응 어려움
- **팀장 부담:** 미제출자 독려해도 제출 못 하면 끝

## 위반 시 처리

**위반 시도:**
```python
await audit_log_repo.log(
    channel_id=channel_id,
    action="proxy_submit_attempt",
    actor_aad_id=activity.from.aadObjectId,
    details={
        "target_owner_aad_id": report_slot.owner_aad_id,
        "week_key": week_key
    }
)
```

**감시:**
- AuditLog.action = "proxy_submit_attempt"
- 정기적 감시 리포트 생성
- 보안 팀에 이상 패턴 보고

## 정책 변경 절차

만약 향후 팀장 대리 제출을 허용하려면:

1. **새 ADR 작성** (ADR-009 또는 동등)
2. **CTO 승인**
3. **보안 팀 감사**
4. **Compliance 검토**
5. **코드 수정**
6. **감시 로그 업데이트** (action name 변경)

## 참고

- ADR-006: no proxy submission (기술 관점)
- 정책: 05_project_decisions.md "팀장 대리 제출 없음"
