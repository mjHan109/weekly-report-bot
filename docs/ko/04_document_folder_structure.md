# 문서 및 폴더 구성 가이드

> **문서 동기화:** `docs/en/04_document_folder_structure.md`와 동기화

## 1. 프로젝트 루트 구조 (Claude Code / Agent Teams)

```text
메일 연동/
├── CLAUDE.md                      # Claude Code 프로젝트 지침 (필수)
├── README.md
├── .claude/
│   ├── settings.json              # Agent Teams env, permissions
│   ├── agents/                    # 서브에이전트 (@product-manager 등)
│   │   ├── product-manager.md
│   │   ├── software-architect.md
│   │   ├── backend-developer.md
│   │   ├── teams-integration-engineer.md
│   │   ├── graph-api-engineer.md
│   │   ├── prompt-engineer.md
│   │   ├── qa-engineer.md
│   │   ├── security-reviewer.md
│   │   └── knowledge-manager.md
│   ├── prompts/                   # Phase 0–3 실행 프롬프트
│   │   ├── phase-0-discovery.md
│   │   ├── phase-1-architecture.md
│   │   ├── phase-2-mvp-implementation.md
│   │   └── phase-3-test-and-hardening.md
│   └── rules/
│       └── documentation-sync.md  # ko/en 동기화 규칙
├── docs/
│   ├── ko/
│   │   ├── 01_requirements_spec.md
│   │   ├── 02_required_environment.md
│   │   ├── 03_agent_roles.md
│   │   ├── 04_document_folder_structure.md
│   │   ├── 05_project_decisions.md
│   │   ├── phase_outputs/
│   │   └── adr/
│   └── en/                        # ko와 1:1 동기화
├── src/
│   ├── adapters/teams/
│   ├── services/reports|mail|llm/
│   ├── models/, repositories/, api/
├── teams-app/manifest/
└── infra/
```

### 1.1 Claude Agent Teams 사용
| 경로 | 용도 |
|---|---|
| `.claude/agents/*.md` | YAML frontmatter + 역할별 system prompt. `/agents` 또는 `@name`으로 호출 |
| `.claude/prompts/phase-*.md` | Phase별 오케스트레이션 프롬프트 |
| `CLAUDE.md` | 모든 세션에 로드되는 프로젝트 컨텍스트 |
| `.claude/settings.json` | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` |

**이전 `docs/.../claude/` 경로는 폐기.** 에이전트·프롬프트는 `.claude/`만 사용한다.

## 2. 문서 관리 원칙
### 2.1 한·영 동기화 (Mandatory)
- 모든 명세·Phase 산출물은 `docs/ko/` + `docs/en/` 동시 작성
- 한쪽만 수정 = incomplete

### 2.2 Phase별 문서
| Phase | ko + en 산출물 |
|---|---|
| 0 | `phase_outputs/phase-0-summary.md` |
| 1 | `phase-1-architecture.md`, `adr/*` |
| 2 | `phase-2-<role>.md` |
| 3 | `phase-3-test-report.md` |

## 3. ADR 확정 현황
- Task Module, 팀장 수동 등록(관리자·본인), 목 13:00 마감, 채널 알림, 발송 차단 → `05` 참조

## 4. 구현 단계
Phase 0 Discovery → Phase 1 Architecture → Phase 2 MVP → Phase 3 Test  
각 Phase 종료 시 ko/en 문서 + knowledge-manager 동기화 검수
