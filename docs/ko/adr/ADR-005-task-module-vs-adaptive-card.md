---
id: ADR-005
title: 입출력 UI: Task Module vs Adaptive Card
status: Accepted
date: 2026-06-04
---

# ADR-005: 입출력 UI: Task Module vs Adaptive Card

## 상태
확정 (Accepted)

## 맥락

Teams 봇은 두 가지 UI 메커니즘을 제공한다:

1. **Task Module:** 채널 메시지에서 "작업" 버튼 클릭 → 모달 폼 펼침
   - 장점: 다중 필드 입력 가능
   - 단점: 미리보기, 상태 표시 어려움

2. **Adaptive Card:** 채널 메시지 자체가 카드 → 버튼, 상태 표시 포함
   - 장점: 미리보기, 상태, 액션 표시 명확함
   - 단점: 복잡한 폼 구현 어려움

**문제:** 어느 UI를 어디에 사용할 것인가?

## 결정

**입력(데이터 수집)에는 Task Module, 출력(상태/액션)에는 Adaptive Card를 사용한다.**

| 기능 | 사용처 | UI 타입 | 이유 |
|---|---|---|---|
| 개인 보고 작성 | 팀원 | Task Module | 다중 필드 입력 (제목, 내용, 첨부) |
| 보고 대상 지정 | 팀장 | Task Module | 사용자 선택 (다중 선택) |
| 팀장 등록 | 관리자/본인 | Adaptive Card | 간단 폼 (채널 ID, 팀 이름) |
| 개인 보고 미리보기 | 팀원 | Adaptive Card | 제출됨 상태, "수정 요청" 버튼 |
| 팀장 상태 카드 | 팀장 | Adaptive Card | 미제출자 목록, 취합 버튼 |
| 취합 보고 미리보기 | 팀장 | Adaptive Card | 취합됨 상태, "승인" 버튼 |
| 정기 알림 | 팀원 | Adaptive Card | "아직 미제출" 상태, 제출 버튼 |
| 마감 알림 | 팀원 | Adaptive Card | "자동/수동 취합 시작" 알림 |

## 근거

### 1. Task Module은 데이터 수집 최적화
- HTML form 렌더링 → 필드 검증 가능
- 다중 필드 입력 자연스러움 (보고 제목, 내용 등)
- 모달 UI로 대화 방해 최소화
- submit → fetch/submit invoke 명확한 flow

### 2. Adaptive Card는 상태 표시 최적화
- 카드 자체가 상태를 시각화 (제출됨, 승인 대기, 메일 발송됨)
- 버튼 액션 (승인, 수정 요청, 취합) 명확함
- 목록 표시 (미제출자 N명) 보기 좋음
- 정기 알림 (목 10:00, 13:00)에 자연스러움

### 3. 두 가지 조합으로 사용자 경험 향상
- 작성 → Task Module (침침하지 않음)
- 상태 확인 → Adaptive Card (한눈에 파악)
- 모달 피로도 감소

### 4. 구현 복잡도 균형
- Task Module: fetch (HTML 렌더링), submit (JSON 파싱)
- Adaptive Card: JSON 정의, action invoke 핸들러
- 서로 다른 패턴으로 코드 중복 감소

## 결과

### 긍정
- **UX 명확성:** 입력과 출력이 명확히 분리됨
- **구현 단순성:** 각 UI 타입이 최적화된 목적을 가짐
- **사용자 피로도:** 모달 노출 최소화

### 부작용
- **두 가지 핸들링:** bot_handler가 task와 adaptive card 양쪽 처리
- **테스트 복잡도:** 두 가지 flow 테스트 필요

### 제약
- Task Module은 제출만 가능 (실시간 상태 표시 불가)
- Adaptive Card는 많은 필드 입력에 부적합

## 구현 세부사항

### Task Module (입력)

**Fetch:**
```
POST /api/messages
{
  "type": "invoke",
  "name": "task/fetch",
  "value": {
    "data": {
      "action": "write_report"  // or "assign_targets", "register_lead"
    }
  }
}

Response:
{
  "task": {
    "type": "continue",
    "value": {
      "title": "주간 보고 작성",
      "height": "medium",
      "url": "https://backend/task-module?action=write_report"
    }
  }
}
```

**Submit:**
```
POST /api/messages
{
  "type": "invoke",
  "name": "task/submit",
  "value": {
    "data": {
      "action": "write_report",
      "title": "이번 주 주요 성과",
      "content": "..."
    }
  }
}
```

### Adaptive Card (출력)

```json
{
  "type": "message",
  "attachments": [
    {
      "contentType": "application/vnd.microsoft.card.adaptive",
      "contentUrl": null,
      "content": {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
          {
            "type": "TextBlock",
            "text": "개인 보고 - 제출됨",
            "weight": "bolder"
          }
        ],
        "actions": [
          {
            "type": "Action.OpenUrl",
            "title": "수정 요청",
            "url": "..."
          }
        ]
      }
    }
  ]
}
```

## 참고

- [Teams Task Module](https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/task-modules/task-modules-bots)
- [Adaptive Cards](https://adaptivecards.io/)
- [Bot Framework Card Actions](https://learn.microsoft.com/en-us/microsoftteams/platform/task-modules-and-cards/cards/cards-actions)
