# Claude Agent Teams 역할 정의

> **문서 동기화 규칙:** 본 문서를 수정할 때는 `docs/en/03_agent_roles.md`를 동일한 구조·의미로 함께 수정한다.

## 공통 문서 작성 의무 (모든 에이전트)
- 에이전트 정의: `.claude/agents/*.md` | Phase 프롬프트: `.claude/prompts/`
- 프로젝트 지침: `CLAUDE.md` | 동기화 규칙: `.claude/rules/documentation-sync.md`

## 제품 관리자 / Product Manager
- 주요 역할: 사용자 흐름, MVP 범위, 우선순위, **수용 기준(전원 제출 + 팀장 발송 승인 = 완료)** 정의
- Phase 산출물: Phase 0 분석, 수용 기준 목록, 요구사항 변경 제안(있을 경우)
- 작업 원칙: `05_project_decisions.md` 확정 사항을 임의로 변경하지 않는다.

## 소프트웨어 아키텍트 / Software Architect
- 주요 역할: Teams Bot, Backend, Delegated Graph, DB, LLM, **채널 격리** 전체 구조 설계
- Phase 산출물: Phase 1 아키텍처, Task Module·알림 스케줄러·팀장 등록 설계, 시퀀스 다이어그램
- 작업 원칙: DB 상세 스키마는 Phase 1에서 엔티티 목록만, 상세는 Phase 2와 병행.

## 백엔드 개발자 / Backend Developer
- 주요 역할: API, DB 모델(개발 병행), 보고서 저장, 수정 이력, 채널별 설정, 서비스 계층
- Phase 산출물: Phase 2 API·모델 문서, 마이그레이션 기록
- 작업 원칙: 채널 ID 기준 데이터 격리를 모든 쿼리에 적용한다.

## Teams 연동 엔지니어 / Teams Integration Engineer
- 주요 역할: Teams 명령어, Adaptive Card, Bot scopes, manifest, **채널별 Bot 동작**
- Phase 산출물: Phase 1 Task Module·알림 플로우, Phase 2 Bot·카드 구현 노트
- 작업 원칙: 한국어 MVP 명령어·버튼 라벨을 준수한다.

## Graph API 엔지니어 / Graph API Engineer
- 주요 역할: **Delegated OAuth**, Outlook 초안·발송, refresh token 관리, Graph scope
- Phase 산출물: Phase 1 OAuth 흐름, Phase 2 Graph 연동·오류 처리 문서
- 작업 원칙: Application permission으로 사용자 메일 발송하지 않는다.

## 프롬프트 엔지니어 / Prompt Engineer
- 주요 역할: 개인 보고, 팀 취합(목~목), 수정 반영 프롬프트 설계
- Phase 산출물: Phase 2 프롬프트 명세, 평가 기준
- 작업 원칙: 보고 주간(목~목)과 취합 섹션 구조를 프롬프트에 반영한다.

## QA 엔지니어 / QA Engineer
- 주요 역할: 팀장 권한, 채널 격리, 발송 승인, 실패 케이스 테스트
- Phase 산출물: Phase 3 테스트 시나리오, 수용 기준 검증 결과
- 작업 원칙: **팀장 발송 승인 성공 = 완료**를 E2E 테스트에 포함한다.

## 보안 리뷰어 / Security Reviewer
- 주요 역할: Delegated OAuth, refresh token, 개인정보, 팀장 발송 승인, 채널 접근 제어
- Phase 산출물: Phase 1/3 보안 검토 보고서
- 작업 원칙: 승인 전 자동 발송 금지, 최소 scope를 검증한다.

## 지식 관리자 / Knowledge Manager
- 주요 역할: **ko/en 동기화 검수**, ADR, Phase 산출물 통합, handoff 문서
- Phase 산출물: Phase 종료마다 문서 인덱스·동기화 체크리스트
- 작업 원칙: ko/en 불일치 발견 시 작업 완료로 처리하지 않는다.

## 권장 작업 흐름
1. product-manager와 software-architect가 Phase 0 분석을 병렬 수행하고 **Phase 0 문서(ko/en)** 를 작성한다.
2. software-architect가 Phase 1 아키텍처·Task Module·알림·팀장 등록·OAuth 설계를 확정하고 **Phase 1 문서(ko/en)** 를 작성한다.
3. backend-developer, teams-integration-engineer, graph-api-engineer가 Phase 2 구현과 **병행 문서(ko/en)** 를 작성한다.
4. prompt-engineer가 Phase 2 프롬프트 명세(ko/en)를 작성한다.
5. qa-engineer가 Phase 3 테스트·수용 검증 문서(ko/en)를 작성한다.
6. security-reviewer가 OAuth·Graph·발송 승인 흐름 검토 문서(ko/en)를 작성한다.
7. knowledge-manager가 Phase 종료마다 ko/en 동기화 및 handoff를 정리한다.
