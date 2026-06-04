# Phase 2 산출물 — @prompt-engineer 역할 보고

작성일: 2026-06-04
담당: @prompt-engineer
보고 주차: 2026-06-01 ~ 2026-06-05 (목 13:00 취합 기준)

---

## 1. 이번 주 완료 작업

### LLM 통합 레이어 전체 구현

| 항목 | 세부 내용 |
|---|---|
| 프롬프트 설계 | 개인 보고서 / 팀 취합 / 이메일 본문 3종 프롬프트 템플릿 작성 |
| LLM 클라이언트 | anthropic SDK 래퍼, 재시도(max 2), 동기·비동기 인터페이스 |
| 생성 서비스 | 3개 async 함수, 병렬 개인 요약 후 팀 취합 파이프라인 |
| 문서화 | ko/en phase_outputs 동기화 작성 |

### 프롬프트 핵심 설계 결정

- 모든 프롬프트는 **한국어**로 작성하며 격식체(합쇼체) 사용.
- 섹션 구분에 마크다운 헤더(#) 대신 `** **` 굵은 제목 사용 — 이메일 본문 호환성 확보.
- **지각 제출 표시:** 개인 보고서 `[지각 제출]`, 팀 취합 `[지각]` 태그 자동 삽입.
- Temperature `0.3` — 창의성보다 일관된 포매팅 우선.
- Python `str.format()` 템플릿 — Jinja 의존성 없이 단순하게 유지.

---

## 2. 다음 주 할 일

- `src/services/reports/` ReportService와 `generate_team_aggregate` 연동 검증
- `src/services/mail/` Graph API 메일 발송 모듈과 `generate_mail_body` 출력 연결
- 공유 모델 패키지(`src/models/`) 확정 시 임시 dataclass 교체
- 단위 테스트 작성 (`tests/services/llm/`)
- 실제 API 호출 기반 프롬프트 품질 검토 및 조정

---

## 3. 이슈 / 블로커

- 없음 — anthropic SDK 인터페이스가 안정적이며 명세가 명확함.

---

## 4. 특이사항

- `generate_team_aggregate`의 병렬 개인 요약 생성은 팀원 수가 많을 경우
  API Rate Limit에 도달할 수 있음. 추후 세마포어 제한을 고려할 것.
- 임시 dataclass(`PersonalReport`, `ChannelConfig`)는 `src/models/` 패키지가
  완성되면 import 경로만 교체하면 되도록 동일 필드명으로 설계함.

---

## 5. 관련 산출물 파일

- `docs/ko/phase_outputs/phase-2-llm.md` (기술 상세)
- `docs/en/phase_outputs/phase-2-llm.md` (영문 동기화)
- `src/services/llm/` 디렉터리 전체 (7개 파일)
