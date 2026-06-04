"""Prompt template for individual (personal) weekly report formatting."""

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

PERSONAL_REPORT_SYSTEM = (
    "당신은 전문 비즈니스 보고서 작성 도우미입니다. "
    "주간 업무 보고를 명확하고 간결한 한국어로 정리합니다. "
    "각 섹션은 100~200자 내외로 작성하고, 불필요한 수식어 없이 핵심 내용만 전달합니다. "
    "마크다운 헤더(#) 대신 굵은 제목(** **)과 줄바꿈을 사용하여 이메일 본문에 적합한 형식으로 출력합니다."
)

# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------

_PERSONAL_REPORT_TEMPLATE = """\
아래 정보를 바탕으로 주간 업무 보고서를 작성해 주세요.

제출자: {name}{late_badge}
보고 주차: {week_period}

[이번 주 한 일]
{this_week}

[다음 주 할 일]
{next_week}

[이슈 / 블로커]
{issues}

[특이사항]
{notes}

---
출력 형식:
**이번 주 한 일**
(요약)

**다음 주 할 일**
(요약)

**이슈 / 블로커**
(요약, 없으면 "없음")

**특이사항**
(요약, 없으면 "없음")
"""

_LATE_BADGE = " [지각 제출]"


def build_personal_report_user(
    name: str,
    week_period: str,
    this_week: str,
    next_week: str,
    issues: str,
    notes: str,
    is_late: bool = False,
) -> str:
    """Build the user-turn prompt for personal report formatting.

    Args:
        name: Submitter's display name.
        week_period: Human-readable week range, e.g. "2026-06-01 ~ 2026-06-05".
        this_week: Raw text for "이번 주 한 일".
        next_week: Raw text for "다음 주 할 일".
        issues: Raw text for "이슈/블로커".
        notes: Raw text for "특이사항".
        is_late: Whether the submission arrived after the 13:00 Thursday deadline.

    Returns:
        Formatted user prompt string.
    """
    late_badge = _LATE_BADGE if is_late else ""
    return _PERSONAL_REPORT_TEMPLATE.format(
        name=name,
        late_badge=late_badge,
        week_period=week_period,
        this_week=this_week.strip() or "내용 없음",
        next_week=next_week.strip() or "내용 없음",
        issues=issues.strip() or "없음",
        notes=notes.strip() or "없음",
    )
