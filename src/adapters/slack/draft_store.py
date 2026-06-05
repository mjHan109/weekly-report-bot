"""
In-memory store for email draft state.

Drafts are created when aggregation completes and deleted after send/cancel.
Server restart clears all drafts — team lead must re-run /취합.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class MailDraft:
    draft_id: str
    channel_id: str
    report_week: str
    mail_to: str
    mail_cc: str
    mail_subject: str
    mail_body: str
    # Populated after draft preview message is posted to channel
    preview_channel: str = ""
    preview_ts: str = ""
    # Idempotency flag — set to True when send is in progress to block double-clicks
    is_sending: bool = False


_drafts: dict[str, MailDraft] = {}


def create_draft(
    channel_id: str,
    report_week: str,
    mail_to: str,
    mail_subject: str,
    mail_body: str,
    mail_cc: str = "",
) -> MailDraft:
    draft_id = uuid.uuid4().hex[:8]
    draft = MailDraft(
        draft_id=draft_id,
        channel_id=channel_id,
        report_week=report_week,
        mail_to=mail_to,
        mail_cc=mail_cc,
        mail_subject=mail_subject,
        mail_body=mail_body,
    )
    _drafts[draft_id] = draft
    return draft


def get_draft(draft_id: str) -> MailDraft | None:
    return _drafts.get(draft_id)


def update_draft(draft_id: str, **kwargs) -> MailDraft | None:
    draft = _drafts.get(draft_id)
    if not draft:
        return None
    for k, v in kwargs.items():
        if hasattr(draft, k):
            setattr(draft, k, v)
    return draft


def delete_draft(draft_id: str) -> None:
    _drafts.pop(draft_id, None)
