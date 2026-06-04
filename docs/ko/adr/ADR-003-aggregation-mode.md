---
id: ADR-003
title: 취합 모드 결정: 마감 시점 (13:00)
status: Accepted
date: 2026-06-04
---

# ADR-003: 취합 모드 결정: 마감 시점 (13:00)

## 상태
확정 (Accepted)

## 맥락

TeamReport의 aggregation_mode는 AUTO 또는 MANUAL로 나뉜다.

- **AUTO:** 모든 팀원이 목 13:00 이전에 제출 완료 → 13:00에 자동으로 LLM 취합 시작
- **MANUAL:** 목 13:00 이후 지연 제출 발생 → 팀장이 수동으로 취합 시작

**문제:** 모드를 언제 결정할 것인가?

옵션 1: 13:00에 한 번만 결정 (이후 변경 불가)
옵션 2: 지연 제출 발생할 때마다 동적 결정 (AUTO → MANUAL 가능)
옵션 3: 처음부터 MANUAL로 설정 (팀장이 항상 제어)

## 결정

**13:00에 한 번만 aggregation_mode를 결정한다. 결정 후 MANUAL → AUTO로의 역전은 없다.**

deadline_service.check_deadline() 호출 시 (Thu 13:00 KST):
- 모든 팀원이 제출했으면 → aggregation_mode = AUTO (자동 LLM 취합 시작)
- 미제출자 있으면 → aggregation_mode = MANUAL (팀장 수동 대기)

13:00 이후 지연 제출 발생하면:
- TeamReport.status는 AUTO_AGGREGATING → MANUAL_PENDING로 전이 가능
- 하지만 aggregation_mode는 이미 MANUAL로 고정
- 팀장이 수동으로 aggregation_service.aggregate() 호출

## 근거

### 1. 경합(Race Condition) 방지
- 13:00 전후 제출이 동시에 발생하면, AUTO vs MANUAL 모드 판단이 불명확함
- 한 번만 결정하면 결정 로직이 명확하고 idempotent함

### 2. 팀장 제어권 유지
- 13:00 마감을 넘으면 팀장이 어느 정도의 신뢰성이 필요한지 판단
- "미제출자가 1명뿐인데 왜 자동 취합?"라는 불만 방지
- 팀장이 최종 결정 권한을 보유

### 3. 상태 머신 단순성
```
13:00 전: COLLECTING
13:00 정확히:
  - 모두 제출: AUTO_AGGREGATING 진입, LLM 자동 취합
  - 미제출자 있음: MANUAL_PENDING 진입, 팀장 대기

13:00 이후 지연 제출:
  - aggregation_mode는 이미 결정됨 (변경 불가)
  - TeamReport.status만 업데이트 (상태 머신 전이)
```

### 4. 운영 정책 명확성
- "13:00 기준으로 자동/수동 결정"이 이해하기 쉬움
- 정책을 문서화하고 사용자에게 설명하기 편함

## 결과

### 긍정
- **명확성:** 언제 결정되는지 명확
- **예측성:** 사용자가 언제 자동 vs 수동인지 미리 알 수 있음
- **단순성:** state machine 로직 간단함

### 부작용
- **경직성:** 13:00 정각에 결정 후 변경 불가
- **팀장 부담:** MANUAL 모드 시 팀장이 수동 취합 클릭 필수
- **지연 제출 복잡도:** 13:00 전후로 로직 분리 필요 (충분한 test coverage 필수)

### 제약
- **마감 시간 변경 불가:** 요구사항으로 고정된 13:00 KST
- **대체 모드 없음:** 한 번 결정되면 변경 정책 없음 (새 주(week)까지 기다려야 함)

## 상태 머신 (13:00 중심)

```
Before 13:00:
  COLLECTING (모든 팀원 제출 대기)
    │
    ├─ (person submits before 13:00)
    │   → PersonalReport.submitted_at 기록 (13:00 이전)
    │
    └─ (person misses 13:00)
        → 여전히 COLLECTING 유지

Exactly 13:00 (deadline_service.check_deadline() called):
  Check: 모든 ChannelReportTarget이 PersonalReport 보유?
    │
    ├─ YES → aggregation_mode = AUTO
    │        TeamReport.status = AUTO_AGGREGATING
    │        aggregation_service.aggregate() 시작
    │
    └─ NO → aggregation_mode = MANUAL
            TeamReport.status = MANUAL_PENDING
            팀장에게 "미제출자 N명, 수동 취합 필요" 카드

After 13:00:
  aggregation_mode는 이미 결정됨 (변경 불가)

  Late submission 발생:
    → aggregation_mode = MANUAL (이미 결정)
    → TeamReport.status 업데이트 (MANUAL_PENDING 유지 또는 전이)
    → 팀장에게 알림 발송
```

## 참고

- ADR-007: 보고 주간 경계 (week_key, 13:00 마감)
- [phase-1-architecture.md](../../phase_outputs/phase-1-architecture.md) — 취합 상태 머신 섹션
