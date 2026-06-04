---
id: ADR-SEC-007
title: Bot Endpoint JWT 검증: Mandatory Pre-Route Middleware
status: Accepted
date: 2026-06-04
---

# ADR-SEC-007: Bot Endpoint JWT 검증: Mandatory Pre-Route Middleware

## 상태
확정 (Accepted)

## 맥락

Bot Framework의 모든 진입점 (`POST /api/messages`)은 Microsoft Bot Framework Activity를 받는다. Activity는 JWT로 서명되어 있다.

**질문:** JWT 검증을 어디서 해야 하는가?

옵션 1: 각 route handler에서 검증
옵션 2: Middleware에서 검증
옵션 3: 검증 skip 가능 (경로별로)

## 결정

**모든 `/api/` 및 `/internal/` 엔드포인트 이전에 필수 middleware로 JWT 검증한다. 검증을 건너뛸 수 없다.**

### Middleware 구현

```python
# src/adapters/teams/middleware.py
from fastapi import Request, HTTPException

class BotFrameworkJWTMiddleware:
    def __init__(self, app, jwt_verifier):
        self.app = app
        self.jwt_verifier = jwt_verifier

    async def __call__(self, request: Request, call_next):
        # 경로 확인
        if not request.url.path.startswith(("/api/", "/internal/")):
            # public endpoint → skip
            return await call_next(request)

        # JWT 헤더 추출
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing JWT")

        token = auth_header[7:]

        # JWT 검증
        try:
            claims = await self.jwt_verifier.verify_and_decode(token)
        except JWTError as e:
            raise HTTPException(status_code=401, detail="Invalid JWT")

        # claim 검증 (Bot Framework specific)
        if claims.get("aud") != BOT_ID:
            raise HTTPException(status_code=401, detail="Invalid audience")

        # Activity를 request context에 저장
        request.state.bot_activity = claims

        return await call_next(request)

# FastAPI app에 등록
app.add_middleware(BotFrameworkJWTMiddleware, jwt_verifier=verifier)
```

### JWT 검증 (Production vs Development)

**Production: Microsoft Public Key**
```python
class MicrosoftJWTVerifier:
    async def verify_and_decode(self, token: str) -> dict:
        # Microsoft JWT key 엔드포인트에서 공개 키 가져오기
        # https://login.microsoftonline.com/botframework.com/v2.0/.well-known/openid-configuration
        keys = await self._get_microsoft_keys()

        # token의 kid (key ID) 찾기
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = keys[kid]

        # 공개 키로 서명 검증
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
        # App Password로 HMAC 검증 (개발용)
        # 프로덕션에서는 이 방식 사용 금지
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

## 근거

### 1. 신뢰 경계 (Trust Boundary)
- Bot Framework JWT는 Microsoft가 발급한 신뢰 경계
- 이를 지나면서 Activity identity를 검증해야 함

### 2. 조기 검증 (Fail Fast)
- Middleware에서 검증 → 모든 route handler가 신뢰할 수 있음
- 각 handler에서 검증하면 누락 가능성

### 3. 건너뛸 수 없는 설계 (Non-Bypassable)
- middleware는 route handler보다 먼저 실행
- route handler가 검증 skip 불가능

### 4. Production vs Development 분리
- Production: Microsoft 공개 키 (금고 표준)
- Development: App Password (로컬 테스트용)

## 결과

### 긍정
- **보안:** 모든 Bot API 요청 인증됨
- **신뢰성:** Activity identity 보장
- **개발 경험:** Development JWT verifier로 쉬운 테스트

### 부작용
- **성능:** JWT 검증 비용 (보통 10-50ms)
- **복잡도:** Microsoft JWT 검증 로직

### 제약
- **Health Check:** `/health` endpoint도 인증 필요 (또는 경로 제외)

## 구현 체크리스트

- [ ] BotFrameworkJWTMiddleware 구현
- [ ] MicrosoftJWTVerifier 구현 (production)
- [ ] DevelopmentJWTVerifier 구현 (development)
- [ ] Middleware 등록 (app.add_middleware)
- [ ] `/health` endpoint 제외 (선택)
- [ ] Error handling (401, 403)
- [ ] Audit log: JWT 검증 실패

## 감시 로그

- action: "bot_jwt_verification_failed"
- reason: "missing_token" | "invalid_token" | "invalid_audience"
- timestamp

## 참고

- [Microsoft Bot Framework Security](https://learn.microsoft.com/en-us/azure/bot-service/bot-service-authentication?view=azure-bot-service-4.0)
- [JWT.io](https://jwt.io/)
