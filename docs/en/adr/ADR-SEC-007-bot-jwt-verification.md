---
id: ADR-SEC-007
title: Bot Endpoint JWT Verification: Mandatory Pre-Route Middleware
status: Accepted
date: 2026-06-04
---

# ADR-SEC-007: Bot Endpoint JWT Verification: Mandatory Pre-Route Middleware

## Status
Accepted

## Context

All Bot Framework entry points (`POST /api/messages`) receive Microsoft Bot Framework Activity. Activity is JWT-signed.

**Question:** where to verify JWT?

Option 1: verify in each route handler
Option 2: verify in middleware
Option 3: allow skipping (per-path)

## Decision

**Verify JWT via mandatory middleware before all `/api/` and `/internal/` endpoints. Verification cannot be skipped.**

### Middleware Implementation

```python
# src/adapters/teams/middleware.py
from fastapi import Request, HTTPException

class BotFrameworkJWTMiddleware:
    def __init__(self, app, jwt_verifier):
        self.app = app
        self.jwt_verifier = jwt_verifier

    async def __call__(self, request: Request, call_next):
        # Check path
        if not request.url.path.startswith(("/api/", "/internal/")):
            # public endpoint → skip
            return await call_next(request)

        # Extract JWT header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing JWT")

        token = auth_header[7:]

        # Verify JWT
        try:
            claims = await self.jwt_verifier.verify_and_decode(token)
        except JWTError as e:
            raise HTTPException(status_code=401, detail="Invalid JWT")

        # Verify claims (Bot Framework specific)
        if claims.get("aud") != BOT_ID:
            raise HTTPException(status_code=401, detail="Invalid audience")

        # Store Activity in request context
        request.state.bot_activity = claims

        return await call_next(request)

# Register middleware with FastAPI app
app.add_middleware(BotFrameworkJWTMiddleware, jwt_verifier=verifier)
```

### JWT Verification (Production vs Development)

**Production: Microsoft Public Key**
```python
class MicrosoftJWTVerifier:
    async def verify_and_decode(self, token: str) -> dict:
        # Fetch Microsoft JWT keys
        # https://login.microsoftonline.com/botframework.com/v2.0/.well-known/openid-configuration
        keys = await self._get_microsoft_keys()

        # Find key ID in token header
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = keys[kid]

        # Verify signature with public key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=BOT_ID
        )

        return claims
```

**Development: Password-Based Only**
```python
class DevelopmentJWTVerifier:
    def __init__(self, app_password: str):
        self.app_password = app_password

    def verify_and_decode(self, token: str) -> dict:
        # Verify with App Password (dev only)
        # Never use this in production
        try:
            claims = jwt.decode(
                token,
                self.app_password,
                algorithms=["HS256"],
                audience=BOT_ID
            )
            return claims
        except JWTError:
            raise
```

## Rationale

### 1. Trust Boundary
- Bot Framework JWT is Microsoft-issued trust boundary
- Must verify Activity identity crossing this boundary

### 2. Fail Fast
- Middleware verification → all route handlers can trust Activity
- Per-handler verification risks omissions

### 3. Non-Bypassable Design
- Middleware executes before route handlers
- Handlers cannot skip verification

### 4. Production vs Development Separation
- Production: Microsoft public key (gold standard)
- Development: App Password (local testing)

## Consequences

### Positive
- **Security:** all Bot API requests authenticated
- **Reliability:** Activity identity guaranteed
- **DX:** development JWT verifier simplifies testing

### Drawbacks
- **Performance:** JWT verification cost (typically 10-50ms)
- **Complexity:** Microsoft JWT verification logic

### Constraints
- **Health Check:** `/health` endpoint also authenticated (or exclude path)

## Implementation Checklist

- [ ] Implement BotFrameworkJWTMiddleware
- [ ] Implement MicrosoftJWTVerifier (production)
- [ ] Implement DevelopmentJWTVerifier (development)
- [ ] Register middleware (app.add_middleware)
- [ ] Exclude `/health` endpoint (optional)
- [ ] Error handling (401, 403)
- [ ] Audit log: JWT verification failures

## Audit Logging

- action: "bot_jwt_verification_failed"
- reason: "missing_token" | "invalid_token" | "invalid_audience"
- timestamp

## References

- [Microsoft Bot Framework Security](https://learn.microsoft.com/en-us/azure/bot-service/bot-service-authentication?view=azure-bot-service-4.0)
- [JWT.io](https://jwt.io/)
