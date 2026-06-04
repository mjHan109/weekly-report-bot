"""Prompt template for formatting the aggregated report as a professional email body."""

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

MAIL_BODY_SYSTEM = (
    "당신은 팀 주간 보고서를 전문적인 한국어 이메일 본문으로 변환하는 작성 도우미입니다. "
    "격식체(합쇼체)를 사용하고, 인사말·보고 내용·맺음말을 포함한 완성된 이메일 본문을 작성합니다. "
    "마크다운 문법 없이 평문으로 출력합니다."
)

# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------

_MAIL_BODY_TEMPLATE = """\
아래 팀 주간 보고 내용을 이메일 본문으로 작성해 주세요.

수신: {to_recipients}
참조: {cc_recipients}
보고 주차: {week_period}
발신 팀: {team_name}

=== 보고 내용 ===
{aggregate_content}
=================

---
출력 형식:

안녕하십니까,
{team_name} 주간 보고를 드립니다.

(보고 주차: {week_period})

[팀 전체 요약]
(이번 주 주요 성과 요약)

[다음 주 팀 계획]
(다음 주 목표 요약)

[공통 이슈 / 블로커]
(공통 이슈 요약 또는 없음)

[개인별 보고 요약]
(팀원별 한 줄 요약)

확인해 주시면 감사하겠습니다.

{team_name} 드림
"""


def build_mail_body_user(
    team_name: str,
    week_period: str,
    aggregate_content: str,
    to_recipients: list[str],
    cc_recipients: list[str] | None = None,
) -> str:
    """Build the user-turn prompt for email body generation.

    Args:
        team_name: Display name of the team / channel.
        week_period: Human-readable week range, e.g. "2026-06-01 ~ 2026-06-05".
        aggregate_content: The LLM-generated team aggregate report text.
        to_recipients: List of To recipient display names or email addresses.
        cc_recipients: Optional list of CC recipient display names or email addresses.

    Returns:
        Formatted user prompt string.
    """
    to_str = ", ".join(to_recipients) if to_recipients else "(없음)"
    cc_str = ", ".join(cc_recipients) if cc_recipients else "(없음)"

    return _MAIL_BODY_TEMPLATE.format(
        team_name=team_name,
        week_period=week_period,
        aggregate_content=aggregate_content.strip(),
        to_recipients=to_str,
        cc_recipients=cc_str,
    )
