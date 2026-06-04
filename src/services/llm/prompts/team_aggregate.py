"""Prompt template for team-level weekly report aggregation."""

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

TEAM_AGGREGATE_SYSTEM = (
    "당신은 팀의 주간 업무 보고를 경영진용으로 요약하는 전문 작성 도우미입니다. "
    "공식적인 한국어(격식체)로 작성하며, 전체 출력은 1500자 이내로 유지합니다. "
    "마크다운 헤더(#) 대신 굵은 제목(** **)과 줄바꿈을 사용하여 이메일 본문에 적합한 형식으로 출력합니다. "
    "지각 제출자는 이름 옆에 [지각] 태그를 유지합니다."
)

# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------

_TEAM_AGGREGATE_TEMPLATE = """\
아래 개인별 주간 보고를 바탕으로 팀 전체 주간 보고서를 작성해 주세요.

팀명: {team_name}
보고 주차: {week_period}
제출 인원: {member_count}명 (지각 제출: {late_count}명)

=== 개인별 보고 ===
{individual_reports}
===================

---
출력 형식 (아래 4개 섹션을 반드시 포함):

**팀 전체 요약 (이번 주 주요 성과)**
(팀 전체의 핵심 성과를 3~5문장으로 요약)

**다음 주 팀 계획**
(팀 전체의 다음 주 주요 목표 및 계획을 3~5문장으로 요약)

**공통 이슈 / 블로커**
(팀원 간 공통되거나 팀 전체에 영향을 미치는 이슈. 없으면 "없음")

**개인별 보고 요약**
• {member_list_hint}
(각 팀원별 한 줄 요약. 지각 제출자는 이름 옆에 [지각] 표시)
"""


def build_team_aggregate_user(
    team_name: str,
    week_period: str,
    individual_reports: list[tuple[str, str, bool]],
) -> str:
    """Build the user-turn prompt for team aggregate report.

    Args:
        team_name: Display name of the team / channel.
        week_period: Human-readable week range, e.g. "2026-06-01 ~ 2026-06-05".
        individual_reports: List of (member_name, formatted_report_text, is_late) tuples.
            formatted_report_text is the output from the personal report prompt.

    Returns:
        Formatted user prompt string.
    """
    member_count = len(individual_reports)
    late_count = sum(1 for _, _, late in individual_reports if late)

    report_blocks: list[str] = []
    member_names: list[str] = []
    for name, report_text, is_late in individual_reports:
        badge = " [지각]" if is_late else ""
        member_names.append(f"{name}{badge}")
        report_blocks.append(
            f"[{name}{badge}]\n{report_text.strip()}"
        )

    joined_reports = "\n\n".join(report_blocks)
    member_list_hint = ", ".join(member_names)

    return _TEAM_AGGREGATE_TEMPLATE.format(
        team_name=team_name,
        week_period=week_period,
        member_count=member_count,
        late_count=late_count,
        individual_reports=joined_reports,
        member_list_hint=member_list_hint,
    )
