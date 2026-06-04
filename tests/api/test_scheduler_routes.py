"""Tests for scheduler API routes — FR-013 (10:00 reminder) and FR-015 (13:00 deadline).

FR-013: The /reminder endpoint is protected by HMAC and dispatches to active channels.
FR-015: The /deadline endpoint is protected by HMAC and calls DeadlineService.

Both endpoints return HTTP 401 when HMAC headers are absent or invalid.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Env vars must be set before the app is imported
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AZURE_TENANT_ID", "test-tenant")
os.environ.setdefault("AZURE_CLIENT_ID", "test-client")
os.environ.setdefault("AZURE_CLIENT_SECRET", "test-secret")
os.environ.setdefault("BOT_APP_ID", "test-bot-id")
os.environ.setdefault("BOT_APP_PASSWORD", "test-bot-pw")
os.environ.setdefault("SCHEDULER_HMAC_SECRET", "test-hmac-secret-value")
os.environ.setdefault("INITIAL_ADMIN_USER_IDS", "admin-aad-001")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

_HMAC_SECRET = "test-hmac-secret-value"
_TIMESTAMP = "1717459200"


# ---------------------------------------------------------------------------
# HMAC helpers (mirrors production logic)
# ---------------------------------------------------------------------------

def _make_sig(body_bytes: bytes, secret: str = _HMAC_SECRET, ts: str = _TIMESTAMP) -> str:
    message = f"{ts}:".encode() + body_bytes
    return hmac_lib.new(secret.encode(), message, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# App fixture — mount only the scheduler router to avoid full app startup
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """TestClient with scheduler router mounted and infrastructure mocked."""
    from fastapi import FastAPI
    app = FastAPI()

    # Patch get_settings so the app does not try to read .env
    mock_settings = MagicMock()
    mock_settings.scheduler_hmac_secret = _HMAC_SECRET

    with patch("src.infra.config.get_settings", return_value=mock_settings), \
         patch("src.api.routes.scheduler.get_settings", return_value=mock_settings):
        from src.api.routes.scheduler import router
        app.include_router(router)
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# FR-013 — /reminder endpoint: HMAC required
# ---------------------------------------------------------------------------

def test_reminder_endpoint_requires_hmac(client: TestClient):
    """FR-013: POST /internal/scheduler/reminder must return HTTP 401 when
    X-Scheduler-Sig and X-Scheduler-Ts headers are absent."""
    response = client.post(
        "/internal/scheduler/reminder",
        json={},
    )
    assert response.status_code == 401


def test_reminder_endpoint_rejects_invalid_hmac(client: TestClient):
    """FR-013: POST /internal/scheduler/reminder must return HTTP 401 when
    the provided X-Scheduler-Sig does not match the expected HMAC digest."""
    body = json.dumps({}).encode()
    response = client.post(
        "/internal/scheduler/reminder",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Scheduler-Sig": "deadbeefdeadbeef",   # invalid signature
            "X-Scheduler-Ts": _TIMESTAMP,
        },
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# FR-015 — /deadline endpoint: HMAC required
# ---------------------------------------------------------------------------

def test_deadline_endpoint_requires_hmac(client: TestClient):
    """FR-015: POST /internal/scheduler/deadline must return HTTP 401 when
    HMAC headers are absent."""
    response = client.post(
        "/internal/scheduler/deadline",
        json={},
    )
    assert response.status_code == 401


def test_deadline_endpoint_calls_deadline_service(client: TestClient):
    """FR-015: POST /internal/scheduler/deadline with a valid HMAC and a
    specific channel_ids list must invoke DeadlineService.run() for that
    channel and return HTTP 200 with a summary."""
    from src.domain.enums import TeamReportStatus

    body_dict = {"channel_ids": ["19:test@thread.tacv2"], "week_key": "2026-W23"}
    body_bytes = json.dumps(body_dict).encode()
    sig = _make_sig(body_bytes)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()

    mock_deadline_svc = MagicMock()
    mock_deadline_svc.run = AsyncMock(return_value=TeamReportStatus.AUTO_AGGREGATING)

    mock_factory = MagicMock(return_value=mock_session)

    with patch(
        "src.api.routes.scheduler._get_session_factory",
        return_value=mock_factory,
    ), patch(
        "src.api.routes.scheduler.DeadlineService",
        return_value=mock_deadline_svc,
    ):
        response = client.post(
            "/internal/scheduler/deadline",
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Scheduler-Sig": sig,
                "X-Scheduler-Ts": _TIMESTAMP,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["week_key"] == "2026-W23"
    assert data["processed"] >= 1
