# Document and Folder Structure Guide

> **Documentation sync:** Sync with `docs/ko/04_document_folder_structure.md`

## 1. Project Root (Claude Code / Agent Teams)

```text
메일 연동/
├── CLAUDE.md
├── README.md
├── .claude/
│   ├── settings.json
│   ├── agents/                    # Subagents (@product-manager, etc.)
│   ├── prompts/                   # Phase 0–3 prompts
│   └── rules/documentation-sync.md
├── docs/ko/  +  docs/en/          # 1:1 synced specs
├── src/
├── teams-app/manifest/
└── infra/
```

See ko version §1 for full tree. **Deprecated:** old `docs/.../claude/` path — use `.claude/` only.

## 2. Documentation Principles
- Mandatory ko/en sync (§2.1 in ko doc)
- Phase outputs under `docs/ko/phase_outputs/` and `docs/en/phase_outputs/`

## 3. ADR Status
- Task Module, team lead manual registration, Thu deadline, channel alerts, send blocking → see `05`

## 4. Implementation Phases
Phase 0 → 1 → 2 → 3 with ko/en docs at each Phase end
