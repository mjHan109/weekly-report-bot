"""
Template-copy based report submission.

Flow
----
1. /주간보고 → bot sends DM with template + [지난주 보고 불러오기] button
2. User optionally clicks [불러오기] to pre-fill with last week's content
3. User edits/fills template and pastes back in DM
4. Bot parses the template and asks for confirmation
5. User confirms → report saved
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

TEMPLATE = """\
[완료]
-
-

[진행중]
-

[다음주]
-

[이슈]
-
"""

_SECTION_PATTERN = re.compile(
    r"\[(완료|진행중|다음주|이슈)\]\s*(.*?)(?=\[(?:완료|진행중|다음주|이슈)\]|$)",
    re.DOTALL,
)

_SECTION_MAP = {
    "완료": "완료한 업무",
    "진행중": "진행 중인 업무",
    "다음주": "다음 주 계획",
    "이슈": "이슈",
}

# Reverse map: DB section name → template key
_REVERSE_SECTION_MAP = {v: k for k, v in _SECTION_MAP.items()}


def parse_template(text: str) -> dict[str, str] | None:
    """Parse filled template. Returns None if template not detected."""
    if not re.search(r"\[(완료|진행중|다음주|이슈)\]", text):
        return None

    result = {}
    for m in _SECTION_PATTERN.finditer(text):
        key = _SECTION_MAP[m.group(1)]
        content = m.group(2).strip()
        # Remove empty bullet lines
        lines = [l for l in content.splitlines() if l.strip() not in ("", "-", "- ")]
        result[key] = "\n".join(lines)
    return result


def build_content(sections: dict[str, str]) -> str:
    """Convert parsed sections to the standard report content format."""
    parts = []
    if sections.get("완료한 업무"):
        parts.append(f"[완료한 업무]\n{sections['완료한 업무']}")
    if sections.get("진행 중인 업무"):
        parts.append(f"[진행 중인 업무]\n{sections['진행 중인 업무']}")
    if sections.get("다음 주 계획"):
        parts.append(f"[다음 주 계획]\n{sections['다음 주 계획']}")
    if sections.get("이슈"):
        parts.append(f"[이슈]\n{sections['이슈']}")
    return "\n\n".join(parts)


def _report_to_template(content: str) -> str:
    """Convert saved report content (DB format) back to copy-paste template format."""
    # Parse existing DB-format sections
    sections: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip("[] \t")
        if stripped in ("완료한 업무", "진행 중인 업무", "다음 주 계획", "이슈"):
            if current and lines:
                sections[current] = "\n".join(lines).strip()
            current = stripped
            lines = []
        elif current:
            lines.append(line)
    if current and lines:
        sections[current] = "\n".join(lines).strip()

    # Rebuild in template format
    parts = []
    for db_key, tmpl_key in [
        ("완료한 업무", "완료"),
        ("진행 중인 업무", "진행중"),
        ("다음 주 계획", "다음주"),
        ("이슈", "이슈"),
    ]:
        body = sections.get(db_key, "-")
        parts.append(f"[{tmpl_key}]\n{body if body else '-'}")
    return "\n\n".join(parts)


async def _fetch_last_week_report(user_id: str, channel_id: str) -> str | None:
    """Return last week's report content string, or None if not found."""
    try:
        from src.infra.db import _get_session_factory
        from src.services.reports.week_utils import previous_week_key
        from src.domain.repositories.personal_report_repo import PersonalReportRepository
        from src.domain.enums import ReportStatus

        factory = _get_session_factory()
        async with factory() as session:
            repo = PersonalReportRepository(session)
            report = await repo.get(channel_id, previous_week_key(), user_id)
            if report and report.status in (ReportStatus.SUBMITTED, ReportStatus.LATE_SUBMITTED):
                return report.content
    except Exception as e:
        logger.warning("_fetch_last_week_report error: %s", e)
    return None


async def send_template_dm(user_id: str, channel_id: str, is_late: bool, client) -> None:
    """Open DM and send the copy-paste template with a [지난주 불러오기] button."""
    dm = await client.conversations_open(users=user_id)
    dm_channel = dm["channel"]["id"]

    late_note = "\n⚠️ _마감 후 제출입니다._" if is_late else ""
    load_payload = json.dumps({"channel_id": channel_id, "is_late": is_late})

    await client.chat_postMessage(
        channel=dm_channel,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"📋 *주간 보고 템플릿*{late_note}\n\n"
                        "아래 템플릿을 *복사*해서 내용을 채운 후 *이 DM에 붙여넣기* 해주세요."
                    ),
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{TEMPLATE}```",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "load_last_week_report",
                        "text": {"type": "plain_text", "text": "지난주 보고 불러오기"},
                        "value": load_payload,
                    }
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 빈 항목은 그냥 두거나 삭제해도 됩니다.",
                    }
                ],
            },
        ],
        text="주간 보고 템플릿",
        metadata={
            "event_type": "weekly_report_template",
            "event_payload": {"channel_id": channel_id, "is_late": is_late},
        },
    )

    logger.info("Template DM sent | user=%s | channel=%s", user_id, channel_id)


async def send_last_week_prefilled(
    user_id: str,
    dm_channel: str,
    channel_id: str,
    is_late: bool,
    client,
) -> None:
    """
    Fetch last week's report and post it as a pre-filled template.
    Called when user clicks [지난주 보고 불러오기].
    """
    content = await _fetch_last_week_report(user_id, channel_id)

    if not content:
        await client.chat_postMessage(
            channel=dm_channel,
            text="지난주 제출한 보고서가 없습니다. 템플릿을 직접 작성해주세요.",
        )
        return

    prefilled = _report_to_template(content)

    await client.chat_postMessage(
        channel=dm_channel,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "📂 *지난주 보고서를 불러왔습니다.*\n"
                        "아래 내용을 *복사*해서 이번 주 변경사항만 수정한 후 *이 DM에 붙여넣기* 해주세요."
                    ),
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{prefilled}```"},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "💡 변경된 항목만 수정하고 그대로 붙여넣으면 됩니다."}
                ],
            },
        ],
        text="지난주 보고서",
        metadata={
            "event_type": "weekly_report_template",
            "event_payload": {"channel_id": channel_id, "is_late": is_late},
        },
    )

    logger.info("Last-week prefill sent | user=%s | channel=%s", user_id, channel_id)


async def handle_template_paste(
    user_id: str,
    dm_channel: str,
    text: str,
    channel_id: str,
    is_late: bool,
    client,
) -> bool:
    """
    Try to parse pasted template from DM message.
    Returns True if parsed successfully (so caller skips other handlers).
    """
    sections = parse_template(text)
    if not sections:
        return False

    content = build_content(sections)
    if not content.strip():
        await client.chat_postMessage(
            channel=dm_channel,
            text="내용이 비어있습니다. 템플릿을 채워서 다시 보내주세요.",
        )
        return True

    # Show preview with confirm/cancel
    preview = "\n".join(f"*{k}*\n{v}" for k, v in sections.items() if v)

    payload = json.dumps({
        "channel_id": channel_id,
        "is_late": is_late,
        "content": content,
    })

    await client.chat_postMessage(
        channel=dm_channel,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"📋 *작성 내용 확인*\n\n{preview}"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": "template_submit",
                        "text": {"type": "plain_text", "text": "제출"},
                        "style": "primary",
                        "value": payload,
                    },
                    {
                        "type": "button",
                        "action_id": "template_retry",
                        "text": {"type": "plain_text", "text": "다시 작성"},
                        "value": json.dumps({"channel_id": channel_id, "is_late": is_late}),
                    },
                ],
            },
        ],
        text="주간 보고 확인",
    )
    return True
