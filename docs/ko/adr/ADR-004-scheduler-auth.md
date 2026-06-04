---
id: ADR-004
title: 스케줄러 인증: HMAC-SHA256
status: Accepted
date: 2026-06-04
---

# ADR-004: 스케줄러 인증: HMAC-SHA256

## 상태
확정 (Accepted)

## 맥락

Cloud Scheduler는 다음 2개 엔드포인트를 호출한다:
- `POST /internal/scheduler/reminder` — 목 10:00
- `POST /internal/scheduler/deadline` — 목 13:00

이 엔드포인트는 권한 없는 외부 호출로부터 보호되어야 한다.

**문제:** Cloud Scheduler → 백엔드 인증 방식?

옵션 1: OIDC/OAuth token (Cloud Scheduler가 bearer token 발급)
옵션 2: HMAC 서명 (stateless, secret key 이용)
옵션 3: IP 화이트리스트만 (클라우드 환경에서 취약)
옵션 4: 상호 TLS (mTLS)

## 결정

**HMAC-SHA256 서명을 X-Scheduler-Sig 헤더에 포함시켜 인증한다.**

구현:
```
X-Scheduler-Sig: HMAC-SHA256(body, SCHEDULER_HMAC_SECRET)
```

Secret:
- SCHEDULER_HMAC_SECRET 환경 변수 (GCP Secret Manager에 저장)
- 90일마다 rotation (표준 앱 secrets 정책)

검증 로직:
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

## 근거

### 1. Cloud Scheduler의 제약
- Cloud Scheduler는 bearer token을 자동으로 발급하지 않음
- OIDC/OAuth token 사용 시 별도 서비스 계정 설정 필수
- 설정 복잡도 높음, 유지보수 부담

### 2. HMAC은 stateless
- Secret key만 알면 인증 가능 (DB 조회 불필요)
- 높은 처리량 환경에서 성능 우수
- 회전(rotation) 정책이 명확함

### 3. 내부 엔드포인트만 대상
- /internal/* 경로는 reverse proxy에서 제한 (외부 접근 차단)
- HMAC은 추가 보안층 (defense in depth)
- stateless 특성으로 마이크로서비스 아키텍처에 적합

### 4. 표준 관행
- API 서명 표준 (AWS SigV4, GitHub webhooks 등)
- 구현 검증 라이브러리 많음

## 결과

### 긍정
- **단순성:** HMAC 구현 간단, 의존성 적음
- **성능:** DB 조회 불필요, 높은 처리량
- **보안:** 서명 위조 거의 불가능 (SHA256 강도)
- **운영:** 환경 변수로 관리, rotation 자동화 용이

### 부작용
- **Secret 관리:** SCHEDULER_HMAC_SECRET 유출 시 문제
- **로깅:** secret을 로그에 출력 절대 금지 (sanitization 필수)
- **Cloud Scheduler 설정:** header 추가 필요 (Terraform에 코드화)

### 제약
- **알고리즘 고정:** SHA256만 지원 (향후 변경 어려움)
- **로테이션 복잡도:** 새 secret 배포 중 일시적 실패 가능 (graceful rollover 구현 필요)

## 구현 체크리스트

- [ ] SCHEDULER_HMAC_SECRET 환경 변수 정의
- [ ] GCP Secret Manager에 secret 저장
- [ ] FastAPI middleware: verify_scheduler_request() 호출 (모든 /internal/* 엔드포인트)
- [ ] Terraform: Cloud Scheduler HTTP 타겟에 X-Scheduler-Sig 헤더 추가
- [ ] Unit test: HMAC 검증 로직
- [ ] E2E test: Cloud Scheduler 호출 시나리오

## Secret Rotation 정책

- **초기 secret 생성:** 배포 시점
- **Rotation 주기:** 90일
- **Graceful rollover:** 기존 + 신규 secret 동시 수락 (N일간)
- **폐기:** rotation 후 N일 경과 후 기존 secret 제거

## 참고

- [HMAC RFC 2104](https://tools.ietf.org/html/rfc2104)
- [Python hmac module](https://docs.python.org/3/library/hmac.html)
- [Cloud Scheduler HTTP targets](https://cloud.google.com/scheduler/docs/http-requests)
