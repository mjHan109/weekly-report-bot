# Phase 2 산출물 — LLM 통합 레이어

작성일: 2026-06-04
담당: @prompt-engineer
모델: claude-sonnet-4-6

---

## 1. 개요

Teams 주간 보고 자동화 프로젝트의 LLM 통합 레이어를 구현하였다.
개인 보고서 포매팅, 팀 취합 보고서 생성, 이메일 본문 작성의 세 가지
생성 기능을 비동기(async) API로 제공한다.

---

## 2. 생성된 파일 목록

| 파일 경로 | 역할 |
|---|---|
| `src/services/llm/__init__.py` | 패키지 진입점, 공개 심볼 노출 |
| `src/services/llm/client.py` | `LLMClient` — anthropic SDK 래퍼, 최대 2회 재시도 |
| `src/services/llm/generation_service.py` | 고수준 async 생성 함수 3종 |
| `src/services/llm/prompts/__init__.py` | 프롬프트 패키지 진입점 |
| `src/services/llm/prompts/personal_report.py` | 개인 보고서 프롬프트 템플릿 |
| `src/services/llm/prompts/team_aggregate.py` | 팀 취합 보고서 프롬프트 템플릿 |
| `src/services/llm/prompts/mail_body.py` | 이메일 본문 프롬프트 템플릿 |

---

## 3. 모듈 설계

### 3-1. LLMClient (`client.py`)

- `anthropic.Anthropic` 동기 클라이언트를 래핑한다.
- `complete(system, user, max_tokens, temperature)` — 동기 호출, 재시도 포함.
- `complete_async(...)` — `asyncio.get_running_loop().run_in_executor`로 비동기 노출.
- 재시도 대상 예외: `RateLimitError`, `APIStatusError`, `APIConnectionError`.
- 최대 시도 횟수: 3회 (초기 1회 + 재시도 2회), 재시도 간격 2초(선형 백오프).
- 모듈 수준 싱글턴 `get_default_client()`로 API 키를 환경변수 `ANTHROPIC_API_KEY`에서 로딩.

### 3-2. 생성 서비스 (`generation_service.py`)

#### 도메인 모델 (임시 dataclass)

```
PersonalReport
  name: str          # 제출자 이름
  week_period: str   # "YYYY-MM-DD ~ YYYY-MM-DD"
  this_week: str     # 이번 주 한 일
  next_week: str     # 다음 주 할 일
  issues: str        # 이슈/블로커 (기본값 "")
  notes: str         # 특이사항 (기본값 "")
  is_late: bool      # 목요일 13:00 이후 제출 여부

ChannelConfig
  team_name: str
  week_period: str
  to_recipients: list[str]
  cc_recipients: list[str]
```

#### 공개 async 함수

| 함수 | 입력 | 출력 | 토큰 상한 |
|---|---|---|---|
| `generate_personal_summary(report, client?)` | `PersonalReport` | 섹션별 포매팅된 한국어 보고 | 512 |
| `generate_team_aggregate(reports, channel_config, client?)` | `list[PersonalReport]`, `ChannelConfig` | 4개 섹션 팀 보고서 (~1500자) | 2048 |
| `generate_mail_body(aggregate_content, channel_config, client?)` | `str`, `ChannelConfig` | 완성된 이메일 본문 | 1024 |

`generate_team_aggregate`는 내부적으로 `asyncio.gather`로 개인 요약을 병렬 생성한 후
팀 취합 프롬프트에 전달한다.

---

## 4. 프롬프트 설계

### 4-1. 개인 보고서 (`personal_report.py`)

- **시스템:** 전문 비즈니스 보고서 작성 도우미, 섹션별 100~200자, 이메일 적합 형식.
- **사용자 템플릿:** 제출자명, 보고 주차, 4개 입력 필드. 지각 시 이름 옆 `[지각 제출]` 뱃지 자동 삽입.
- **출력:** `**이번 주 한 일**`, `**다음 주 할 일**`, `**이슈 / 블로커**`, `**특이사항**` 4개 섹션.

### 4-2. 팀 취합 보고서 (`team_aggregate.py`)

- **시스템:** 경영진용 공식 한국어, 전체 1500자 이내.
- **사용자 템플릿:** 팀명, 주차, 제출 인원/지각 인원 수, 개인별 포매팅된 보고 블록.
- **출력 4개 섹션:**
  1. 팀 전체 요약 (이번 주 주요 성과)
  2. 다음 주 팀 계획
  3. 공통 이슈 / 블로커
  4. 개인별 보고 요약 (불릿 리스트, 지각자 `[지각]` 태그)

### 4-3. 이메일 본문 (`mail_body.py`)

- **시스템:** 격식체(합쇼체), 마크다운 없는 평문 이메일.
- **사용자 템플릿:** 수신/참조, 팀명, 주차, 취합 보고서 내용.
- **출력:** 인사말 → 보고 내용 4섹션 → 맺음말 구조의 완성형 이메일 본문.

---

## 5. 공통 파라미터

| 파라미터 | 값 |
|---|---|
| 모델 | `claude-sonnet-4-6` |
| Temperature | `0.3` (일관된 포매팅) |
| 언어 | 한국어 (모든 프롬프트) |
| 템플릿 방식 | Python `str.format()` (Jinja 미사용) |

---

## 6. 목요일 13:00 취합 로직과의 연동

- `PersonalReport.is_late = True`이면 개인 보고서에 `[지각 제출]` 뱃지가 삽입된다.
- 팀 취합 보고서에서도 `[지각]` 태그가 개인별 요약에 유지된다.
- 전원 정시 제출(13:00 이전) 시 `is_late=False`로 뱃지 없이 생성된다.

---

## 7. 다음 단계 연동 포인트

- `src/services/reports/` — `ReportService`가 DB에서 `PersonalReport` 목록을 로딩하여
  `generate_team_aggregate`를 호출한다.
- `src/services/mail/` — `generate_mail_body` 출력을 Graph API 메일 발송 본문으로 사용한다.
- `src/models/` — Phase 2 진행 중 공유 모델 패키지가 완성되면 `generation_service.py`의
  임시 dataclass를 교체한다.
