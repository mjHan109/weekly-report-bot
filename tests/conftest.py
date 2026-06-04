"""Shared pytest fixtures for all test modules.

Provides:
- async_session: in-memory SQLite AsyncSession (no real DB required).
- channel_config: a sample active ChannelConfig.
- channel_report_target: a sample ChannelReportTarget linked to the above.
- mock_activity: a minimal Bot Framework Activity stub with aad_object_id.
"""

import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Patch settings before any src import that calls get_settings() at import time
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AZURE_TENANT_ID", "test-tenant")
os.environ.setdefault("AZURE_CLIENT_ID", "test-client")
os.environ.setdefault("AZURE_CLIENT_SECRET", "test-secret")
os.environ.setdefault("BOT_APP_ID", "test-bot-id")
os.environ.setdefault("BOT_APP_PASSWORD", "test-bot-pw")
os.environ.setdefault("SCHEDULER_HMAC_SECRET", "test-hmac-secret")
os.environ.setdefault("INITIAL_ADMIN_USER_IDS", "admin-aad-001")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

from src.domain.models.base import Base
from src.domain.models.channel_config import ChannelConfig
from src.domain.models.channel_report_target import ChannelReportTarget
from src.domain.models.personal_report import PersonalReport
from src.domain.models.team_report import TeamReport
from src.domain.enums import ReportStatus, TeamReportStatus

# Import all models so Base.metadata is complete before table creation
import src.domain.models.mail_draft  # noqa: F401
import src.domain.models.audit_log  # noqa: F401
import src.domain.models.reminder_log  # noqa: F401
import src.domain.models.revision_history  # noqa: F401


# ---------------------------------------------------------------------------
# Engine & Session factory
# ---------------------------------------------------------------------------

TEST_CHANNEL_ID = "19:test-channel-aad@thread.tacv2"
TEST_WEEK_KEY = "2026-W23"
TEAM_LEAD_AAD = "team-lead-aad-001"
MEMBER_AAD_1 = "member-aad-001"
MEMBER_AAD_2 = "member-aad-002"
SEED_ADMIN_AAD = "admin-aad-001"


@pytest_asyncio.fixture
async def async_session():
    """In-memory async SQLite session with all tables created.

    Each test gets a fresh database; no real DB connection is required.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Domain object fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def channel_config(async_session: AsyncSession) -> ChannelConfig:
    """Persist and return a sample active ChannelConfig."""
    config = ChannelConfig(
        channel_id=TEST_CHANNEL_ID,
        channel_name="Test Channel",
        team_lead_aad_id=TEAM_LEAD_AAD,
        is_active=True,
        service_url="https://smba.trafficmanager.net/test/",
    )
    async_session.add(config)
    await async_session.flush()
    await async_session.refresh(config)
    return config


@pytest_asyncio.fixture
async def channel_report_target(
    async_session: AsyncSession, channel_config: ChannelConfig
) -> ChannelReportTarget:
    """Persist and return a single active ChannelReportTarget (member-aad-001)."""
    target = ChannelReportTarget(
        channel_id=TEST_CHANNEL_ID,
        aad_object_id=MEMBER_AAD_1,
        display_name="Test Member 1",
        email="member1@test.example",
        is_active=True,
    )
    async_session.add(target)
    await async_session.flush()
    await async_session.refresh(target)
    return target


@pytest_asyncio.fixture
async def two_report_targets(
    async_session: AsyncSession, channel_config: ChannelConfig
) -> list[ChannelReportTarget]:
    """Persist and return two active ChannelReportTargets."""
    targets = []
    for aad_id, name, email in [
        (MEMBER_AAD_1, "Test Member 1", "member1@test.example"),
        (MEMBER_AAD_2, "Test Member 2", "member2@test.example"),
    ]:
        t = ChannelReportTarget(
            channel_id=TEST_CHANNEL_ID,
            aad_object_id=aad_id,
            display_name=name,
            email=email,
            is_active=True,
        )
        async_session.add(t)
        targets.append(t)
    await async_session.flush()
    return targets


@pytest_asyncio.fixture
async def collecting_team_report(
    async_session: AsyncSession, channel_config: ChannelConfig
) -> TeamReport:
    """Persist and return a TeamReport in COLLECTING status."""
    tr = TeamReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        status=TeamReportStatus.COLLECTING,
    )
    async_session.add(tr)
    await async_session.flush()
    await async_session.refresh(tr)
    return tr


@pytest_asyncio.fixture
async def pending_personal_report(
    async_session: AsyncSession,
    channel_config: ChannelConfig,
    collecting_team_report: TeamReport,
) -> PersonalReport:
    """Persist and return a PENDING PersonalReport for MEMBER_AAD_1."""
    pr = PersonalReport(
        channel_id=TEST_CHANNEL_ID,
        week_key=TEST_WEEK_KEY,
        aad_object_id=MEMBER_AAD_1,
        status=ReportStatus.PENDING,
        submitted_after_deadline=False,
    )
    async_session.add(pr)
    await async_session.flush()
    await async_session.refresh(pr)
    return pr


# ---------------------------------------------------------------------------
# Bot Framework Activity stub
# ---------------------------------------------------------------------------

class _AadFrom:
    def __init__(self, aad_object_id: str) -> None:
        self.aad_object_id = aad_object_id


class MockActivity:
    """Minimal Bot Framework Activity stub."""

    def __init__(self, aad_object_id: str) -> None:
        self.from_property = _AadFrom(aad_object_id)
        self.channel_id = "msteams"
        self.conversation = MagicMock()
        self.service_url = "https://smba.trafficmanager.net/test/"


@pytest.fixture
def mock_activity():
    """Return a MockActivity for MEMBER_AAD_1."""
    return MockActivity(aad_object_id=MEMBER_AAD_1)
