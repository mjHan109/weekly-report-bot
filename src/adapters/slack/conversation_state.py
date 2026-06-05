"""
In-memory conversation state store for DM-based report submission.

State per user:
  step        : "done" | "inprogress" | "plan" | "confirm"
  data        : {"완료한 업무": str, "진행 중인 업무": str, "다음 주 계획": str}
  channel_id  : original slash command channel
  is_late     : bool
"""

from __future__ import annotations

STEPS = ["done", "inprogress", "plan", "confirm"]

STEP_LABELS = {
    "done":       "완료한 업무",
    "inprogress": "진행 중인 업무",
    "plan":       "다음 주 계획",
}

STEP_PROMPTS = {
    "done": (
        "✅ *완료한 업무*를 입력해주세요.\n"
        "예)\n"
        "1. Chat eval 품질 개선\n"
        "    - 평가 점수 81% → 100% 달성\n"
        "2. 모델 성능 측정\n\n"
        "_입력 후 메시지를 전송하면 다음 단계로 넘어갑니다._"
    ),
    "inprogress": (
        "🔄 *진행 중인 업무*를 입력해주세요.\n"
        "예)\n"
        "1. 모델 평가 품질 지표 정리\n\n"
        "_입력 후 메시지를 전송하면 다음 단계로 넘어갑니다._"
    ),
    "plan": (
        "📅 *다음 주 계획*을 입력해주세요.\n"
        "예)\n"
        "1. 벤치마크 대상 모델 확대\n"
        "2. 평가 결과 분석\n\n"
        "_입력 후 메시지를 전송하면 최종 확인 단계로 넘어갑니다._"
    ),
}

# {user_id: state_dict}
_store: dict[str, dict] = {}


def start(user_id: str, channel_id: str, is_late: bool) -> None:
    _store[user_id] = {
        "step": "done",
        "data": {},
        "channel_id": channel_id,
        "is_late": is_late,
    }


def get(user_id: str) -> dict | None:
    return _store.get(user_id)


def save_step(user_id: str, text: str) -> str | None:
    """Save current step answer and advance. Returns next step or None if done."""
    state = _store.get(user_id)
    if not state:
        return None

    current = state["step"]
    if current in STEP_LABELS:
        state["data"][STEP_LABELS[current]] = text

    idx = STEPS.index(current)
    if idx + 1 < len(STEPS):
        state["step"] = STEPS[idx + 1]
        return state["step"]
    return None


def clear(user_id: str) -> None:
    _store.pop(user_id, None)


def is_active(user_id: str) -> bool:
    return user_id in _store
