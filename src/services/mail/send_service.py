"""Triple-gate verified mail send service.

The gate_check() method re-verifies all three conditions from the database
before sending.  Client state is never trusted.

Triple-gate conditions (ADR-SEC-003)
-------------------------------------
1. TeamReport.status == AWAITING_APPROVAL
2. All ChannelReportTargets have a PersonalReport for the given week_key
3. actor_aad_id == ChannelConfig.team_lead_aad_id for the channel

Any gate failure raises a GateCheckError; the draft is NOT sent.

No direct httpx calls are made here — all Graph interactions go through
GraphClient.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Protocol, runtime_checkable

from .graph_client import GraphClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain status enum (mirrors DB enum)
# ---------------------------------------------------------------------------

class TeamReportStatus(str, Enum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SENT = "SENT"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Repository protocols (concrete implementations live in src/repositories/)
# ---------------------------------------------------------------------------

@runtime_checkable
class TeamReportRepository(Protocol):
    def get_status(self, channel_id: str, week_key: str) -> TeamReportStatus | None:
        """Return the current status of the team report, or None if not found."""
        ...

    def get_message_id(self, channel_id: str, week_key: str) -> str | None:
        """Return the Graph message_id stored for this draft."""
        ...

    def get_team_lead_oid(self, channel_id: str, week_key: str) -> str | None:
        """Return the team lead OID associated with the report."""
        ...

    def mark_sent(self, channel_id: str, week_key: str) -> None:
        """Update TeamReport.status to SENT."""
        ...


@runtime_checkable
class ChannelConfigRepository(Protocol):
    def get_team_lead_aad_id(self, channel_id: str) -> str | None:
        """Return the registered team lead AAD ID for a channel."""
        ...

    def get_report_target_oids(self, channel_id: str) -> list[str]:
        """Return the list of member OIDs who must submit reports."""
        ...


@runtime_checkable
class PersonalReportRepository(Protocol):
    def has_report(self, member_oid: str, channel_id: str, week_key: str) -> bool:
        """Return True if the member has submitted a report for week_key."""
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GateCheckError(RuntimeError):
    """Raised when one or more triple-gate conditions are not satisfied."""

    def __init__(self, gate: int, reason: str) -> None:
        super().__init__(f"Gate {gate} failed: {reason}")
        self.gate = gate
        self.reason = reason


class SendError(RuntimeError):
    """Raised when the Graph send call fails after gate checks pass."""


# ---------------------------------------------------------------------------
# Send service
# ---------------------------------------------------------------------------

class SendService:
    """Sends a reviewed draft mail after re-verifying all triple-gate conditions.

    Parameters
    ----------
    graph_client:
        Authenticated GraphClient instance.
    team_report_repo:
        Repository for TeamReport records.
    channel_config_repo:
        Repository for ChannelConfig records.
    personal_report_repo:
        Repository for PersonalReport records.
    """

    def __init__(
        self,
        graph_client: GraphClient,
        team_report_repo: TeamReportRepository,
        channel_config_repo: ChannelConfigRepository,
        personal_report_repo: PersonalReportRepository,
    ) -> None:
        self._gc = graph_client
        self._tr_repo = team_report_repo
        self._cc_repo = channel_config_repo
        self._pr_repo = personal_report_repo

    def gate_check(
        self,
        channel_id: str,
        week_key: str,
        actor_aad_id: str,
    ) -> None:
        """Re-verify all triple-gate conditions from the database.

        Raises GateCheckError immediately on the first failing gate.
        Does NOT trust any client-supplied state.

        Parameters
        ----------
        channel_id:
            Teams channel ID.
        week_key:
            ISO week string, e.g. "2026-W23".
        actor_aad_id:
            AAD ID of the user requesting the send (must be team lead).
        """
        # ------------------------------------------------------------------
        # Gate 1: TeamReport.status == AWAITING_APPROVAL
        # ------------------------------------------------------------------
        status = self._tr_repo.get_status(channel_id, week_key)
        if status != TeamReportStatus.AWAITING_APPROVAL:
            logger.warning(
                "SendService: gate 1 failed channel=%s week=%s status=%s",
                channel_id,
                week_key,
                status,
            )
            raise GateCheckError(
                gate=1,
                reason=(
                    f"TeamReport status is '{status}', expected AWAITING_APPROVAL. "
                    "The report may not yet be ready for sending."
                ),
            )
        logger.info(
            "SendService: gate 1 passed channel=%s week=%s", channel_id, week_key
        )

        # ------------------------------------------------------------------
        # Gate 2: All ChannelReportTargets have a PersonalReport for week_key
        # ------------------------------------------------------------------
        target_oids = self._cc_repo.get_report_target_oids(channel_id)
        missing = [
            oid
            for oid in target_oids
            if not self._pr_repo.has_report(oid, channel_id, week_key)
        ]
        if missing:
            logger.warning(
                "SendService: gate 2 failed channel=%s week=%s missing_oids=%s",
                channel_id,
                week_key,
                missing,
            )
            raise GateCheckError(
                gate=2,
                reason=(
                    f"{len(missing)} member(s) have not submitted a report for "
                    f"week {week_key}: {missing}"
                ),
            )
        logger.info(
            "SendService: gate 2 passed channel=%s week=%s targets=%d",
            channel_id,
            week_key,
            len(target_oids),
        )

        # ------------------------------------------------------------------
        # Gate 3: actor_aad_id == ChannelConfig.team_lead_aad_id
        # ------------------------------------------------------------------
        registered_lead = self._cc_repo.get_team_lead_aad_id(channel_id)
        if registered_lead != actor_aad_id:
            logger.warning(
                "SendService: gate 3 failed channel=%s actor=%s registered_lead=%s",
                channel_id,
                actor_aad_id,
                registered_lead,
            )
            raise GateCheckError(
                gate=3,
                reason=(
                    f"Actor '{actor_aad_id}' is not the registered team lead "
                    f"for channel '{channel_id}'."
                ),
            )
        logger.info(
            "SendService: gate 3 passed channel=%s actor=%s", channel_id, actor_aad_id
        )

    def send(
        self,
        channel_id: str,
        week_key: str,
        actor_aad_id: str,
    ) -> None:
        """Run triple-gate check then send the draft.

        Steps
        -----
        1. gate_check() — raises GateCheckError on any failure.
        2. Retrieve message_id and team_lead_oid from the DB.
        3. Call GraphClient.send_draft() — delegated Mail.Send scope only.
        4. Mark TeamReport.status = SENT in the DB.

        Raises
        ------
        GateCheckError
            If any gate condition is not met.
        SendError
            If the Graph API call fails after all gates pass.
        """
        # Triple-gate re-verification (server-side, from DB)
        self.gate_check(channel_id, week_key, actor_aad_id)

        # Retrieve message_id and team lead OID from DB
        message_id = self._tr_repo.get_message_id(channel_id, week_key)
        if not message_id:
            raise SendError(
                f"No draft message_id found for channel={channel_id} week={week_key}. "
                "The draft may not have been created yet."
            )

        team_lead_oid = self._tr_repo.get_team_lead_oid(channel_id, week_key)
        if not team_lead_oid:
            raise SendError(
                f"No team_lead_oid found for channel={channel_id} week={week_key}."
            )

        logger.info(
            "SendService: sending draft channel=%s week=%s message_id=%s oid=%s",
            channel_id,
            week_key,
            message_id,
            team_lead_oid,
        )

        try:
            self._gc.send_draft(oid=team_lead_oid, message_id=message_id)
        except Exception as exc:
            logger.error(
                "SendService: send failed channel=%s week=%s error=%s",
                channel_id,
                week_key,
                exc,
            )
            raise SendError(f"Graph send_draft failed: {exc}") from exc

        # Mark as sent in the DB
        self._tr_repo.mark_sent(channel_id, week_key)
        logger.info(
            "SendService: mail sent and status updated channel=%s week=%s",
            channel_id,
            week_key,
        )
