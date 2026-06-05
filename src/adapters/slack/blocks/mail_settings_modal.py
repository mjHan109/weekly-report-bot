"""
Block Kit builder — /설정 통합 설정 모달.

팀장이 채널별 보고 일정, 템플릿, 메일 설정을 한 곳에서 관리한다.
"""

from __future__ import annotations

from src.domain.models.mail_settings import MailSettings

_WEEKDAY_OPTIONS = [
    {"text": {"type": "plain_text", "text": "월요일"}, "value": "0"},
    {"text": {"type": "plain_text", "text": "화요일"}, "value": "1"},
    {"text": {"type": "plain_text", "text": "수요일"}, "value": "2"},
    {"text": {"type": "plain_text", "text": "목요일"}, "value": "3"},
    {"text": {"type": "plain_text", "text": "금요일"}, "value": "4"},
]

_TEMPLATE_HINT = "팀원이 [빠른 작성] 선택 시 이 양식이 기본 입력값으로 표시됩니다."
_SUBJECT_HINT  = "사용 가능한 변수: {year} {month} {week} {team_name} {sender_name} {week_key}"
_GREETING_HINT = "사용 가능한 변수: {sender_name} {team_name} {month} {week} {week_key} {year}"
_REMIND_HINT   = "쉼표로 구분. 예) 3,1 → 마감 3시간 전, 1시간 전에 DM 발송. 비우면 리마인드 없음."


def _select_option(options: list[dict], value: str) -> dict:
    """Return the option dict whose value matches, defaulting to first."""
    for opt in options:
        if opt["value"] == str(value):
            return opt
    return options[0]


def build_mail_settings_modal(settings: MailSettings) -> dict:
    """Build the full /설정 modal with all configurable fields."""
    return {
        "type": "modal",
        "callback_id": "mail_settings_modal",
        "private_metadata": settings.channel_id,
        "title": {"type": "plain_text", "text": "채널 설정"},
        "submit": {"type": "plain_text", "text": "저장"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": [
            # ── 팀 정보 ───────────────────────────────────────────────────────
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "팀 정보"},
            },
            {
                "type": "input",
                "block_id": "team_name",
                "label": {"type": "plain_text", "text": "팀명"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "initial_value": settings.team_name or "",
                    "placeholder": {"type": "plain_text", "text": "예: 개발3팀"},
                },
            },
            {
                "type": "input",
                "block_id": "sender_name",
                "label": {"type": "plain_text", "text": "발신자 이름"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "initial_value": settings.sender_name or "",
                    "placeholder": {"type": "plain_text", "text": "예: 홍길동"},
                },
            },

            # ── 보고 일정 ─────────────────────────────────────────────────────
            {"type": "divider"},
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "보고 일정"},
            },
            {
                "type": "input",
                "block_id": "deadline_weekday",
                "label": {"type": "plain_text", "text": "마감 요일"},
                "element": {
                    "type": "static_select",
                    "action_id": "value",
                    "options": _WEEKDAY_OPTIONS,
                    "initial_option": _select_option(
                        _WEEKDAY_OPTIONS, settings.deadline_weekday
                    ),
                },
            },
            {
                "type": "input",
                "block_id": "deadline_hour",
                "label": {"type": "plain_text", "text": "마감 시각 (KST, 0~23)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "initial_value": str(settings.deadline_hour),
                    "placeholder": {"type": "plain_text", "text": "13"},
                },
                "hint": {"type": "plain_text", "text": "기본값: 13 (오후 1시)"},
            },
            {
                "type": "input",
                "block_id": "reminder_hours",
                "label": {"type": "plain_text", "text": "리마인드 시간 (마감 N시간 전)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "initial_value": settings.reminder_hours or "",
                    "placeholder": {"type": "plain_text", "text": "3,1"},
                },
                "hint": {"type": "plain_text", "text": _REMIND_HINT},
            },

            # ── 보고 템플릿 ───────────────────────────────────────────────────
            {"type": "divider"},
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "보고 템플릿"},
            },
            {
                "type": "input",
                "block_id": "report_template",
                "label": {"type": "plain_text", "text": "기본 보고 양식"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "multiline": True,
                    "initial_value": settings.report_template or "",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "[완료한 업무]\n1. \n\n[진행 중인 업무]\n1. \n\n[다음 주 계획]\n1. ",
                    },
                },
                "hint": {"type": "plain_text", "text": _TEMPLATE_HINT},
            },

            # ── 메일 설정 ─────────────────────────────────────────────────────
            {"type": "divider"},
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "메일 설정"},
            },
            {
                "type": "input",
                "block_id": "mail_subject_format",
                "label": {"type": "plain_text", "text": "메일 제목 형식"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "initial_value": settings.mail_subject_format or "",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "[주간보고] {year}년 {month}월 {week}주차 {team_name} 주간보고서",
                    },
                },
                "hint": {"type": "plain_text", "text": _SUBJECT_HINT},
            },
            {
                "type": "input",
                "block_id": "greeting",
                "label": {"type": "plain_text", "text": "메일 서두"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "multiline": True,
                    "initial_value": settings.greeting or "",
                },
                "hint": {"type": "plain_text", "text": _GREETING_HINT},
            },
            {
                "type": "input",
                "block_id": "closing",
                "label": {"type": "plain_text", "text": "메일 끝맺음"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "multiline": True,
                    "initial_value": settings.closing or "",
                },
            },

            # ── 수신자 ────────────────────────────────────────────────────────
            {"type": "divider"},
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "기본 수신자"},
            },
            {
                "type": "input",
                "block_id": "default_mail_to",
                "label": {"type": "plain_text", "text": "수신 (쉼표 구분)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "initial_value": settings.default_mail_to or "",
                    "placeholder": {"type": "plain_text", "text": "boss@company.com"},
                },
            },
            {
                "type": "input",
                "block_id": "default_mail_cc",
                "label": {"type": "plain_text", "text": "참조 (쉼표 구분)"},
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "value",
                    "initial_value": settings.default_mail_cc or "",
                    "placeholder": {"type": "plain_text", "text": "cc@company.com"},
                },
            },
            {
                "type": "input",
                "block_id": "auto_cc_team_lead",
                "label": {"type": "plain_text", "text": "팀장 자동 참조"},
                "optional": True,
                "element": {
                    "type": "checkboxes",
                    "action_id": "value",
                    "options": [{
                        "text": {"type": "plain_text", "text": "메일 발송 시 팀장 자동 참조에 추가"},
                        "value": "yes",
                    }],
                    "initial_options": (
                        [{"text": {"type": "plain_text", "text": "메일 발송 시 팀장 자동 참조에 추가"},
                          "value": "yes"}]
                        if settings.auto_cc_team_lead else []
                    ),
                },
            },
        ],
    }
