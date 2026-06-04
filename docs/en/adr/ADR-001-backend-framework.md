---
id: ADR-001
title: Backend Framework: FastAPI (Python)
status: Accepted
date: 2026-06-04
---

# ADR-001: Backend Framework: FastAPI (Python)

## Status
Accepted

## Context

The Teams Weekly Report Automation project has the following technical requirements:

1. **LLM Integration:** Anthropic Claude for automated report aggregation
2. **Microsoft Graph API:** Teams and mail service integration
3. **OAuth 2.0 + PKCE:** Team lead mail authentication
4. **async Processing:** high concurrency (Bot Framework webhook, Cloud Scheduler)
5. **Type Safety:** data validation and serialization

Runtime candidates:
- Python (FastAPI, Django, Flask)
- Node.js (Express, NestJS, Fastify)
- Go (Gin, Echo)

## Decision

**FastAPI (Python 3.12+) is selected as the sole backend runtime.**

- ORM: SQLAlchemy 2.x (async) + Alembic (migrations)
- LLM SDK: Anthropic anthropic-sdk (Claude Sonnet)
- Validation: Pydantic v2
- Database: PostgreSQL (async driver: asyncpg)

## Rationale

### 1. Anthropic Python SDK Native Support
- Anthropic maintains Python SDK as first-class, latest features reflected quickly
- Node.js is second-generation, Go is unsupported
- Python SDK has async/await support for seamless FastAPI integration

### 2. msgraph-sdk-python Excellence
- msgraph-sdk-python is Python-first designed, OAuth token refresh and Graph API calls are explicit
- msgraph-sdk-js (Node.js) still in beta, lower maturity
- msgraph-sdk-go lacks queue concepts, Teams bot integration difficult

### 3. async/await Native
- FastAPI is ASGI framework, async/await based
- Optimal for I/O-heavy workloads: Bot Framework webhooks (concurrent channel messages), Cloud Scheduler callbacks, Graph API calls
- Node.js viable but Python ecosystem more mature

### 4. Pydantic Unified Solution
- Pydantic v2 solves data validation and serialization in one model
- 8 ORM entities + API DTOs cleanly separated, validation rules declarative
- Reduces errors in channel isolation (ADR-002) and security validation

### 5. SQLAlchemy 2.x async Maturity
- SQLAlchemy 2.0 provides async first-class support
- Alembic migration tool highly mature
- ORM-level channel isolation enforcement (ChannelScopedRepository pattern)

## Consequences

### Positive
- **Fast Development:** Python developer productivity high, syntax clear
- **LLM Integration Easy:** Anthropic SDK latest features immediately available
- **Graph API Reliability:** msgraph-sdk-python proven implementation
- **async Optimized:** high concurrency handling
- **Type Safety:** Pydantic validation reduces security mistakes

### Drawbacks
- **Deployment Complexity:** Docker/Kubernetes operations experience required
- **Performance Cost:** Node.js startup overhead (usually negligible)
- **Library Choices:** large ecosystem but many options require decision
- **Team Capability:** Python dev experience needed

### Constraints
- **Dev Environment:** Python 3.12+ required
- **Deployment:** ASGI web server (Uvicorn, etc.)
- **DB Support:** async driver required (PostgreSQL + asyncpg)

## References

- [FastAPI Official](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [msgraph-sdk-python](https://github.com/microsoftgraph/msgraph-sdk-python)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
