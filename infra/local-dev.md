# 로컬 개발

- Claude Code: 프로젝트 루트에서 `CLAUDE.md` + `.claude/agents/` 사용
- Teams Bot: ngrok/dev tunnel → Backend webhook
- 스케줄러: 로컬에서는 curl로 reminder API 수동 트리거 (목 10:00 / 13:00 job)
- DB: SQLite 또는 Docker PostgreSQL

상세는 Phase 1 `docs/ko/phase_outputs/phase-1-architecture.md` 참조.
