---
id: ADR-004
title: Scheduler Authentication: HMAC-SHA256
status: Accepted
date: 2026-06-04
---

# ADR-004: Scheduler Authentication: HMAC-SHA256

## Status
Accepted

## Context

Cloud Scheduler invokes two endpoints:
- `POST /internal/scheduler/reminder` — Thu 10:00
- `POST /internal/scheduler/deadline` — Thu 13:00

These endpoints must be protected from unauthorized external calls.

**Question:** how to authenticate Cloud Scheduler → backend?

Option 1: OIDC/OAuth token (Cloud Scheduler issues bearer token)
Option 2: HMAC signature (stateless, secret key)
Option 3: IP whitelist only (vulnerable in cloud)
Option 4: mutual TLS (mTLS)

## Decision

**HMAC-SHA256 signature included in X-Scheduler-Sig header for authentication.**

Implementation:
```
X-Scheduler-Sig: HMAC-SHA256(body, SCHEDULER_HMAC_SECRET)
```

Secret:
- SCHEDULER_HMAC_SECRET environment variable (stored in GCP Secret Manager)
- Rotate every 90 days (standard app secrets policy)

Verification logic:
```python
import hmac
import hashlib

def verify_scheduler_request(body: bytes, sig_header: str) -> bool:
    secret = os.getenv("SCHEDULER_HMAC_SECRET")
    expected_sig = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig_header, expected_sig)
```

## Rationale

### 1. Cloud Scheduler Constraints
- Cloud Scheduler does not auto-issue bearer tokens
- OIDC/OAuth requires separate service account setup
- High configuration complexity, maintenance burden

### 2. HMAC is Stateless
- Only need secret key to authenticate (no DB lookup)
- Excellent performance for high-throughput
- Clear rotation policy

### 3. Internal Endpoints Only
- /internal/* paths restricted at reverse proxy (external access blocked)
- HMAC provides additional security layer (defense in depth)
- Stateless suitable for microservices architecture

### 4. Standard Practice
- API signature standard (AWS SigV4, GitHub webhooks, etc.)
- Many verification libraries available

## Consequences

### Positive
- **Simplicity:** HMAC implementation straightforward, minimal dependencies
- **Performance:** no DB lookup, high throughput
- **Security:** signature forgery virtually impossible (SHA256 strength)
- **Operations:** managed via env var, rotation easily automated

### Drawbacks
- **Secret Management:** SCHEDULER_HMAC_SECRET leak is critical
- **Logging:** never output secret to logs (sanitization required)
- **Cloud Scheduler Setup:** header addition needed (code in Terraform)

### Constraints
- **Algorithm Fixed:** SHA256 only (future changes difficult)
- **Rotation Complexity:** temporary failures during new secret deployment (graceful rollover needed)

## Implementation Checklist

- [ ] Define SCHEDULER_HMAC_SECRET environment variable
- [ ] Store secret in GCP Secret Manager
- [ ] FastAPI middleware: call verify_scheduler_request() (all /internal/* endpoints)
- [ ] Terraform: add X-Scheduler-Sig header to Cloud Scheduler HTTP target
- [ ] Unit test: HMAC verification logic
- [ ] E2E test: Cloud Scheduler invocation scenarios

## Secret Rotation Policy

- **Initial secret creation:** at deployment
- **Rotation period:** 90 days
- **Graceful rollover:** accept both old + new secret temporarily (N days)
- **Disposal:** remove old secret N days after rotation

## References

- [HMAC RFC 2104](https://tools.ietf.org/html/rfc2104)
- [Python hmac module](https://docs.python.org/3/library/hmac.html)
- [Cloud Scheduler HTTP targets](https://cloud.google.com/scheduler/docs/http-requests)
