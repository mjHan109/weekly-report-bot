# Teams 주간 보고 봇 — 로컬 개발 명령어
# 사용법: make <target>

.PHONY: help install db-up db-down migrate run test tunnel clean

help:
	@echo ""
	@echo "사용 가능한 명령어:"
	@echo "  make install    - Python 패키지 설치"
	@echo "  make db-up      - PostgreSQL Docker 컨테이너 시작"
	@echo "  make db-down    - PostgreSQL Docker 컨테이너 중지"
	@echo "  make migrate    - Alembic DB 마이그레이션 실행"
	@echo "  make run        - FastAPI 앱 실행 (SQLite 기본)"
	@echo "  make run-pg     - FastAPI 앱 실행 (PostgreSQL)"
	@echo "  make test       - pytest 실행"
	@echo "  make test-v     - pytest 상세 출력"
	@echo "  make tunnel     - ngrok 터널 시작 (포트 8000)"
	@echo "  make reminder   - 목 10:00 알림 API 수동 트리거"
	@echo "  make deadline   - 목 13:00 마감 API 수동 트리거"
	@echo "  make clean      - 캐시 파일 정리"
	@echo ""

install:
	pip install -r requirements.txt
	pip install -r requirements-test.txt

# ── DB ──────────────────────────────────────────────────────────────────────

db-up:
	docker compose up -d db
	@echo "PostgreSQL 시작 중... 잠시 기다려 주세요."
	@sleep 3
	@docker compose ps db

db-down:
	docker compose down

migrate:
	alembic upgrade head

# ── 앱 실행 ──────────────────────────────────────────────────────────────────

run:
	@echo "SQLite 모드로 실행 (개발용)"
	DATABASE_URL=sqlite+aiosqlite:///./dev.db \
	MICROSOFT_APP_ID=dev-local \
	MICROSOFT_APP_PASSWORD=dev-local \
	INITIAL_ADMIN_USER_IDS=local-admin \
	ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} \
	uvicorn src.main:app --reload --port 8000

run-pg:
	@echo "PostgreSQL 모드로 실행"
	DATABASE_URL=postgresql+asyncpg://dev:devpassword@localhost:5432/teams_reports \
	MICROSOFT_APP_ID=$${MICROSOFT_APP_ID} \
	MICROSOFT_APP_PASSWORD=$${MICROSOFT_APP_PASSWORD} \
	INITIAL_ADMIN_USER_IDS=$${INITIAL_ADMIN_USER_IDS} \
	ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} \
	uvicorn src.main:app --reload --port 8000

# ── 테스트 ───────────────────────────────────────────────────────────────────

test:
	pytest tests/ -q

test-v:
	pytest tests/ -v --tb=short

test-cov:
	pytest tests/ --cov=src --cov-report=term-missing

# ── ngrok 터널 ────────────────────────────────────────────────────────────────

tunnel:
	@echo "ngrok 터널 시작 (포트 8000)"
	@echo "터널 URL을 Azure Bot Service Messaging endpoint에 등록하세요:"
	@echo "  https://<ngrok-url>/api/messages"
	ngrok http 8000

# ── 스케줄러 수동 트리거 ──────────────────────────────────────────────────────

HMAC_SECRET ?= dev-hmac-secret
CHANNEL_ID ?= test-channel-id

_hmac_sig = $(shell python3 -c "import hmac,hashlib; print(hmac.new(b'$(HMAC_SECRET)', b'', hashlib.sha256).hexdigest())")

reminder:
	@echo "목 10:00 알림 트리거"
	curl -s -X POST http://localhost:8000/internal/scheduler/reminder \
	  -H "Content-Type: application/json" \
	  -H "X-Scheduler-Sig: $$(python3 -c \"import hmac,hashlib,json; body=json.dumps({'channel_id': '$(CHANNEL_ID)'}).encode(); print(hmac.new(b'$(HMAC_SECRET)', body, hashlib.sha256).hexdigest())\")" \
	  -d '{"channel_id": "$(CHANNEL_ID)"}' | python3 -m json.tool

deadline:
	@echo "목 13:00 마감 트리거"
	curl -s -X POST http://localhost:8000/internal/scheduler/deadline \
	  -H "Content-Type: application/json" \
	  -H "X-Scheduler-Sig: $$(python3 -c \"import hmac,hashlib,json; body=json.dumps({'channel_id': '$(CHANNEL_ID)'}).encode(); print(hmac.new(b'$(HMAC_SECRET)', body, hashlib.sha256).hexdigest())\")" \
	  -d '{"channel_id": "$(CHANNEL_ID)"}' | python3 -m json.tool

health:
	curl -s http://localhost:8000/health | python3 -m json.tool

# ── 정리 ─────────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -f dev.db
