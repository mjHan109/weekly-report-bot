# Claude Agent Teams Role Definition

> **Documentation sync rule:** When changing this document, update `docs/ko/03_agent_roles.md` with the same structure and meaning.

## Shared Documentation Obligations
- Agent defs: `.claude/agents/*.md` | Phase prompts: `.claude/prompts/`
- Project instructions: `CLAUDE.md` | Sync rule: `.claude/rules/documentation-sync.md`

## 제품 관리자 / Product Manager
- Main role: User flows, MVP scope, priorities, **acceptance criteria (team lead send approval = complete)**
- Phase outputs: Phase 0 analysis, acceptance criteria list, change proposals (if any)
- Working principle: Do not change confirmed items in `05_project_decisions.md` arbitrarily.

## 소프트웨어 아키텍트 / Software Architect
- Main role: Overall design for Teams Bot, Backend, Delegated Graph, DB, LLM, **channel isolation**
- Phase outputs: Phase 1 architecture, Task Module/reminder/team lead registration design, sequence diagrams
- Working principle: Phase 1 defines entity list only; detailed DB schema parallels Phase 2.

## 백엔드 개발자 / Backend Developer
- Main role: APIs, DB models (parallel with dev), report persistence, revision history, per-channel settings
- Phase outputs: Phase 2 API/model docs, migration records
- Working principle: Apply channel ID isolation to all queries.

## Teams 연동 엔지니어 / Teams Integration Engineer
- Main role: Teams commands, Adaptive Cards, bot scopes, manifest, **per-channel bot behavior**
- Phase outputs: Phase 1 Task Module/reminder flows, Phase 2 bot/card implementation notes
- Working principle: Follow Korean MVP commands and button labels.

## Graph API 엔지니어 / Graph API Engineer
- Main role: **Delegated OAuth**, Outlook draft/send, refresh token management, Graph scopes
- Phase outputs: Phase 1 OAuth flow, Phase 2 Graph integration and error-handling docs
- Working principle: Do not send user mail via application-only permissions.

## 프롬프트 엔지니어 / Prompt Engineer
- Main role: Prompts for personal reports, team aggregation (Thu–Thu), revision application
- Phase outputs: Phase 2 prompt spec, evaluation criteria
- Working principle: Reflect reporting week (Thu–Thu) and aggregation sections in prompts.

## QA 엔지니어 / QA Engineer
- Main role: Team lead permission, channel isolation, send approval, failure-case tests
- Phase outputs: Phase 3 test scenarios, acceptance verification results
- Working principle: Include **successful team lead send approval = complete** in E2E tests.

## 보안 리뷰어 / Security Reviewer
- Main role: Delegated OAuth, refresh tokens, personal data, team lead send approval, channel access control
- Phase outputs: Phase 1/3 security review reports
- Working principle: Verify no auto-send before approval and least-privilege scopes.

## 지식 관리자 / Knowledge Manager
- Main role: **ko/en sync review**, ADRs, Phase output consolidation, handoff docs
- Phase outputs: Document index and sync checklist at each Phase end
- Working principle: Do not mark work complete if ko/en documents diverge.

## Recommended Workflow
1. product-manager and software-architect run Phase 0 in parallel and write **Phase 0 docs (ko/en)**.
2. software-architect finalizes Phase 1 architecture, Task Module, reminder, team lead registration, and OAuth design, and writes **Phase 1 docs (ko/en)**.
3. backend-developer, teams-integration-engineer, graph-api-engineer implement Phase 2 with **parallel docs (ko/en)**.
4. prompt-engineer writes Phase 2 prompt specs (ko/en).
5. qa-engineer writes Phase 3 test and acceptance docs (ko/en).
6. security-reviewer writes OAuth/Graph/send-approval review docs (ko/en).
7. knowledge-manager consolidates ko/en sync and handoff at each Phase end.
