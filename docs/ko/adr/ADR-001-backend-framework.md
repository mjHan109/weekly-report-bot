---
id: ADR-001
title: 백엔드 프레임워크: FastAPI (Python)
status: Accepted
date: 2026-06-04
---

# ADR-001: 백엔드 프레임워크: FastAPI (Python)

## 상태
확정 (Accepted)

## 맥락

Teams 주간 보고 자동화 프로젝트는 다음 기술 요구사항을 가진다:

1. **LLM 통합:** Anthropic Claude를 이용한 보고 자동 취합
2. **Microsoft Graph API:** Teams, 메일 서비스 통합
3. **OAuth 2.0 + PKCE:** 팀장 메일 인증
4. **async 처리:** 높은 동시성 (Bot Framework webhook, Cloud Scheduler)
5. **타입 안정성:** 데이터 검증 및 직렬화

런타임 선택지:
- Python (FastAPI, Django, Flask)
- Node.js (Express, NestJS, Fastify)
- Go (Gin, Echo)

## 결정

**FastAPI (Python 3.12+) 를 유일한 백엔드 런타임으로 선택한다.**

- ORM: SQLAlchemy 2.x (async) + Alembic (마이그레이션)
- LLM SDK: Anthropic anthropic-sdk (Claude Sonnet)
- 검증: Pydantic v2
- 데이터베이스: PostgreSQL (async driver: asyncpg)

## 근거

### 1. Anthropic Python SDK 네이티브 지원
- Anthropic은 Python SDK를 1순위로 유지보수하고 최신 기능을 빠르게 반영
- Node.js는 후발 지원, Go는 미지원
- Python SDK는 async/await 지원으로 FastAPI 통합이 자연스러움

### 2. msgraph-sdk-python 우수성
- msgraph-sdk-python은 Python-first 설계로 OAuth token refresh, Graph API call이 명확함
- msgraph-sdk-js (Node.js)는 아직 beta 상태, 완성도 낮음
- msgraph-sdk-go는 대기열(queue) 개념 부족, Teams 봇 통합 어려움

### 3. async/await 네이티브
- FastAPI는 ASGI 프레임워크로 async/await 기반
- Bot Framework webhook (동시 채널 메시지), Cloud Scheduler 콜백, Graph API 호출 등 I/O 대량 작업에 최적
- Node.js도 가능하지만 Python ecosystem이 더 성숙함

### 4. Pydantic 동시 해결
- Pydantic v2는 데이터 검증과 직렬화를 하나의 모델로 해결
- 8개 ORM 엔티티 + API DTO가 명확히 분리되고 검증 규칙이 선언적임
- 이는 채널 격리(ADR-002) 및 보안 검증의 실수를 줄임

### 5. SQLAlchemy 2.x async 성숙도
- SQLAlchemy 2.0은 async first-class support 제공
- Alembic 마이그레이션 도구 성숙도 높음
- ORM-level 채널 격리 강제 (ChannelScopedRepository pattern)

## 결과

### 긍정
- **빠른 개발:** Python 개발자 생산성 높음, 문법이 명확함
- **LLM 통합 용이:** Anthropic SDK 최신 기능 즉시 사용
- **Graph API 신뢰성:** msgraph-sdk-python 검증된 구현
- **async 최적화:** 높은 동시성 처리 가능
- **타입 안정성:** Pydantic 검증으로 보안 실수 감소

### 부작용
- **배포 복잡도:** Docker/Kubernetes 운영 경험 필요
- **성능 비용:** Node.js 대비 약간의 startup overhead (보통 무시 가능한 수준)
- **라이브러리 선택:** 생태계가 크지만 선택지 많아 결정 필요
- **팀 역량:** Python 개발 경험이 있는 팀원 필요

### 제약
- **개발 환경:** Python 3.12+ 필수
- **배포 환경:** ASGI 웹 서버 (Uvicorn 등)
- **DB 지원:** async driver 필요 (PostgreSQL + asyncpg)

## 참고

- [FastAPI Official](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [msgraph-sdk-python](https://github.com/microsoftgraph/msgraph-sdk-python)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
