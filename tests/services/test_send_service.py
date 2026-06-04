"""Tests for SendService (mail/send_service.py) — FR-017 and FR-020.

FR-017: Mail must be blocked when any member has not submitted.
FR-020: Team lead is the only actor allowed to trigger the send.

SendService uses synchronous repository protocols (Protocol classes), so
all dependencies are replaced with MagicMock / spec'd objects.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from tests.conftest import (
    TEST_CHANNEL_ID,
    TEST_WEEK_KEY,
    TEAM_LEAD_AAD,
    MEMBER_AAD_1,
    MEMBER_AAD_2,
)
from src.services.mail.send_service import (
    GateCheckError,
    SendError,
    SendService,
    TeamReportStatus,
)


# ---------------------------------------------------------------------------
# Helpers — build mock repos matching the Protocol interfaces
# ---------------------------------------------------------------------------

def _make_repos(
    *,
    status: TeamReportStatus = TeamReportStatus.AWAITING_APPROVAL,
    message_id: str | None = "msg-001",
    team_lead_oid: str = TEAM_LEAD_AAD,
    target_oids: list[str] | None = None,
    has_report_oids: set[str] | None = None,
    registered_lead: str = TEAM_LEAD_AAD,
):
    """Build MagicMock repository objects that satisfy the Protocol contracts."""
    if target_oids is None:
        target_oids = [MEMBER_AAD_1]
    if has_report_oids is None:
        has_report_oids = set(target_oids)

    tr_repo = MagicMock()
    tr_repo.get_status.return_value = status
    tr_repo.get_message_id.return_value = message_id
    tr_repo.get_team_lead_oid.return_value = team_lead_oid

    cc_repo = MagicMock()
    cc_repo.get_team_lead_aad_id.return_value = registered_lead
    cc_repo.get_report_target_oids.return_value = target_oids

    pr_repo = MagicMock()
    pr_repo.has_report.side_effect = (
        lambda oid, ch, wk: oid in has_report_oids
    )

    gc = MagicMock()

    return gc, tr_repo, cc_repo, pr_repo


def _make_svc(**kwargs) -> SendService:
    gc, tr, cc, pr = _make_repos(**kwargs)
    return SendService(
        graph_client=gc,
        team_report_repo=tr,
        channel_config_repo=cc,
        personal_report_repo=pr,
    ), gc, tr


# ---------------------------------------------------------------------------
# FR-017 + FR-020 — gate passes when all conditions met
# ---------------------------------------------------------------------------

def test_gate_check_passes_when_all_conditions_met():
    """FR-017 + FR-020: gate_check() must succeed (no exception) when:
    - TeamReport.status == AWAITING_APPROVAL (gate 1)
    - All target members have submitted (gate 2)
    - actor_aad_id is the registered team lead (gate 3)"""
    svc, _, _ = _make_svc(
        status=TeamReportStatus.AWAITING_APPROVAL,
        target_oids=[MEMBER_AAD_1],
        has_report_oids={MEMBER_AAD_1},
        registered_lead=TEAM_LEAD_AAD,
    )
    # Must not raise
    svc.gate_check(TEST_CHANNEL_ID, TEST_WEEK_KEY, TEAM_LEAD_AAD)


# ---------------------------------------------------------------------------
# FR-017 — gate 2 fails when pending submitters exist
# ---------------------------------------------------------------------------

def test_gate_check_fails_when_pending_submitters():
    """FR-017: gate_check() must raise GateCheckError(gate=2) when any report
    target has not yet submitted a PersonalReport for the given week_key."""
    svc, _, _ = _make_svc(
        status=TeamReportStatus.AWAITING_APPROVAL,
        target_oids=[MEMBER_AAD_1, MEMBER_AAD_2],
        has_report_oids={MEMBER_AAD_1},   # MEMBER_AAD_2 has NOT submitted
        registered_lead=TEAM_LEAD_AAD,
    )

    with pytest.raises(GateCheckError) as exc_info:
        svc.gate_check(TEST_CHANNEL_ID, TEST_WEEK_KEY, TEAM_LEAD_AAD)

    assert exc_info.value.gate == 2
    assert MEMBER_AAD_2 in exc_info.value.reason


# ---------------------------------------------------------------------------
# FR-020 — gate 1 fails when not AWAITING_APPROVAL
# ---------------------------------------------------------------------------

def test_gate_check_fails_when_not_awaiting_approval():
    """FR-020: gate_check() must raise GateCheckError(gate=1) when the
    TeamReport is not in AWAITING_APPROVAL state (e.g. still MANUAL_PENDING)."""
    svc, _, _ = _make_svc(
        status=TeamReportStatus.DRAFT,   # wrong state
        target_oids=[MEMBER_AAD_1],
        has_report_oids={MEMBER_AAD_1},
        registered_lead=TEAM_LEAD_AAD,
    )

    with pytest.raises(GateCheckError) as exc_info:
        svc.gate_check(TEST_CHANNEL_ID, TEST_WEEK_KEY, TEAM_LEAD_AAD)

    assert exc_info.value.gate == 1


# ---------------------------------------------------------------------------
# FR-020 — gate 3 fails when actor is not team lead
# ---------------------------------------------------------------------------

def test_gate_check_fails_when_actor_not_team_lead():
    """FR-020: gate_check() must raise GateCheckError(gate=3) when the
    requesting actor is not the registered team lead for the channel."""
    svc, _, _ = _make_svc(
        status=TeamReportStatus.AWAITING_APPROVAL,
        target_oids=[MEMBER_AAD_1],
        has_report_oids={MEMBER_AAD_1},
        registered_lead=TEAM_LEAD_AAD,
    )

    with pytest.raises(GateCheckError) as exc_info:
        svc.gate_check(TEST_CHANNEL_ID, TEST_WEEK_KEY, MEMBER_AAD_1)   # not a lead

    assert exc_info.value.gate == 3


# ---------------------------------------------------------------------------
# FR-017 — send() is never called when gate fails
# ---------------------------------------------------------------------------

def test_send_blocked_not_called_when_gate_fails():
    """FR-017: send() must not invoke GraphClient.send_draft() when any gate
    check fails. The draft must remain unsent and the DB must not be updated."""
    gc, tr_repo, cc_repo, pr_repo = _make_repos(
        status=TeamReportStatus.AWAITING_APPROVAL,
        target_oids=[MEMBER_AAD_1, MEMBER_AAD_2],
        has_report_oids={MEMBER_AAD_1},   # member 2 missing — gate 2 fails
        registered_lead=TEAM_LEAD_AAD,
    )
    svc = SendService(
        graph_client=gc,
        team_report_repo=tr_repo,
        channel_config_repo=cc_repo,
        personal_report_repo=pr_repo,
    )

    with pytest.raises(GateCheckError):
        svc.send(TEST_CHANNEL_ID, TEST_WEEK_KEY, TEAM_LEAD_AAD)

    # Graph send_draft must never have been invoked
    gc.send_draft.assert_not_called()
    # mark_sent must never have been invoked
    tr_repo.mark_sent.assert_not_called()
