# Teams 주간 보고 자동화

Microsoft Teams Bot 기반 주간 보고 작성·취합·Outlook 메일 발송 자동화 프로젝트.

## Claude Code / Agent Teams

```text
메일 연동/
├── CLAUDE.md                 # 프로젝트 지침 (Claude Code 진입점)
├── .claude/
│   ├── settings.json         # 권한, Agent Teams env
│   ├── agents/               # 서브에이전트 정의 (@name)
│   ├── prompts/              # Phase 0–3 실행 프롬프트
│   └── rules/                # 공통 규칙 (문서 동기화 등)
├── docs/
│   ├── ko/                   # 한국어 명세 (en과 1:1 동기화)
│   └── en/
├── src/                      # Backend·서비스 코드
├── teams-app/manifest/       # Teams 앱 manifest
└── infra/                    # 배포·스케줄러
```

Agent Teams 활성화: `.claude/settings.json`의 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`

## 핵심 문서
- [요구사항 (ko)](docs/ko/01_requirements_spec.md)
- [확정 결정 (ko)](docs/ko/05_project_decisions.md)
- [폴더·Phase 가이드 (ko)](docs/ko/04_document_folder_structure.md)

## MVP 요약
- **보고 대상:** 팀장 `보고 대상 지정`
- **13:00 전 on-time 전원 → 자동 취합**
- **미제출/late → 본인 제출 대기, 팀장 수동 취합** (대리 제출 없음)
- **팀장 카드:** 제출 대기 → 취합·메일 작성 안내
- Task Module 입력 | 팀장 `팀장 등록` (관리자·팀장 본인)
