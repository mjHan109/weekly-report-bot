"""Domain-level enumerations shared across models and services."""

import enum


class AggregationMode(str, enum.Enum):
    """How a TeamReport was (or will be) aggregated.

    AUTO   — all members submitted on time; system aggregated automatically.
    MANUAL — one or more members missed the deadline; team lead aggregates manually.
    """

    AUTO = "auto"
    MANUAL = "manual"


class ReportStatus(str, enum.Enum):
    """Lifecycle status of an individual PersonalReport.

    PENDING        — not yet submitted (default at week start).
    SUBMITTED      — submitted on or before Thursday 13:00 KST.
    LATE_SUBMITTED — submitted after the deadline (self-submit only, no proxy).
    """

    PENDING = "pending"
    SUBMITTED = "submitted"
    LATE_SUBMITTED = "late_submitted"


class TeamReportStatus(str, enum.Enum):
    """State machine for the weekly TeamReport aggregate.

    COLLECTING        — week is open; members can submit on time.
    AUTO_AGGREGATING  — deadline passed with full submission; system aggregating.
    MANUAL_PENDING    — deadline passed with missing submissions; awaiting late submits.
    AWAITING_APPROVAL — draft ready; team lead must review before mail send.
    MAIL_SENT         — mail dispatched successfully.
    CANCELLED         — week cancelled (e.g., holiday override by team lead).
    """

    COLLECTING = "collecting"
    AUTO_AGGREGATING = "auto_aggregating"
    MANUAL_PENDING = "manual_pending"
    AWAITING_APPROVAL = "awaiting_approval"
    MAIL_SENT = "mail_sent"
    CANCELLED = "cancelled"
