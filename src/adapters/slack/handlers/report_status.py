"""ReportStatusHandler — /보고현황 slash command.

팀장이 이번 주 제출 현황을 한눈에 확인하고,
미제출자 리마인드 및 취합을 바로 실행할 수 있다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ReportStatusHandler:

    async def handle(self, body: dict, client, logger) -> None:
        user_id: str = body["user_id"]
        channel_id: str = body["channel_id"]

        from src.services.reports.report_service import ReportService
        svc = ReportService()

        total = await svc.get_total_reporter_count(channel_id)
        unsubmitted = await svc.get_unsubmitted_with_slack_ids(channel_id)
        submitted_count = total - len(unsubmitted)

        if total == 0:
            await client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text="보고 대상자가 설정되지 않았습니다. `/보고대상` 으로 설정해주세요.",
            )
            return

        # Build status text
        submitted_ratio = f"{submitted_count}/{total}명"
        if unsubmitted:
            unsubmitted_names = "\n".join(
                f"  • <@{u['slack_user_id']}>" if u.get("slack_user_id") else f"  • {u['display_name']}"
                for u in unsubmitted
            )
            status_text = (
                f"📊 *이번 주 보고 현황*\n\n"
                f"✅ 제출 완료: *{submitted_count}명*\n"
                f"⏳ 미제출: *{len(unsubmitted)}명*\n\n"
                f"*미제출자 목록*\n{unsubmitted_names}"
            )
        else:
            status_text = (
                f"📊 *이번 주 보고 현황*\n\n"
                f"✅ 전원 제출 완료! ({submitted_ratio})"
            )

        has_slack_linked = any(u.get("slack_user_id") for u in unsubmitted)

        # Action buttons
        elements = []
        if unsubmitted and has_slack_linked:
            elements.append({
                "type": "button",
                "action_id": "send_reminder_dms",
                "text": {"type": "plain_text", "text": "📨 미제출자 DM 리마인드"},
                "value": channel_id,
                "style": "primary",
            })
        elements.append({
            "type": "button",
            "action_id": "status_aggregate_trigger",
            "text": {"type": "plain_text", "text": "📋 팀 보고 취합"},
            "value": channel_id,
        })

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": status_text},
            },
        ]
        if elements:
            blocks.append({"type": "actions", "elements": elements})

        await client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            blocks=blocks,
            text=f"보고 현황: {submitted_ratio} 제출",
        )
        logger.info(
            "ReportStatusHandler: shown | channel=%s user=%s submitted=%d total=%d",
            channel_id, user_id, submitted_count, total,
        )
