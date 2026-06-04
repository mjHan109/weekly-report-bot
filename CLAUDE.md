# Teams 주간 보고 자동화 — Claude Code 프로젝트 지침

## 프로젝트 목표
Microsoft Teams Bot으로 채널별 주간 보고 작성·취합·메일 발송(팀장 승인)을 자동화한다.

## 필수 참조 문서 (ko/en 동기화)
| 문서 | 경로 |
|---|---|
| 요구사항 | `docs/ko/01_requirements_spec.md` |
| 환경·Graph | `docs/ko/02_required_environment.md` |
| 에이전트 역할 | `docs/ko/03_agent_roles.md` |
| 폴더 구조 | `docs/ko/04_document_folder_structure.md` |
| 확정 결정 | `docs/ko/05_project_decisions.md` |

영문은 `docs/en/`에 동일 구조로 유지한다. **한쪽만 수정 금지.**

## Agent Teams 사용법
1. Phase 프롬프트: `.claude/prompts/phase-N-*.md`
2. 역할별 서브에이전트: `.claude/agents/*.md` (`@product-manager` 등)
3. Phase별 병렬 작업 후 `docs/ko/phase_outputs/` (및 en)에 산출물 작성
4. knowledge-manager가 Phase 종료 시 ko/en 동기화 검수

## 확정 MVP 핵심
- **보고 대상:** 팀장 `보고 대상 지정`
- **13:00 전 전원 on-time → 자동 취합** | **미제출/late → 본인 제출 대기 + 팀장 수동 취합**
- **팀장 대리 제출 없음** — 미제출자 본인 late 제출
- **팀장 Adaptive Card:** 제출 대기 → 취합·메일 작성 안내
- 알림: 목 10:00·13:00 채널 | 미제출 시 메일 불가

## Claude Code Hooks (`.claude/hooks/`)
- **PreToolUse** `security_guard.py` — 위험 Bash·시크릿 파일 쓰기 차단
- **SessionStart** `reinject_context.py` (`compact`) — 압축 후 프로젝트 규칙 재주입
- **PostToolUse** `doc_sync_warn.py` — `docs/ko` 편집 시 `docs/en` 페어 경고
- 설정: `.claude/settings.json` | 세션 재시작 또는 `/hooks` 로 반영

## 코드 구조
- `src/adapters/teams/` — Bot, Task Module, 카드, 알림
- `src/services/reports/` — 보고·취합·마감
- `src/services/mail/` — Graph 메일
- `src/services/llm/` — 프롬프트·생성
- `teams-app/manifest/` — Teams 앱 패키지
- `infra/` — 배포·스케줄러

## 작업 원칙
- `05_project_decisions.md` 확정 사항을 임의 변경하지 않는다.
- DB 상세 스키마는 Phase 2와 병행한다.
- 모든 Phase/역할 작업 종료 시 ko/en 문서를 함께 갱신한다.
