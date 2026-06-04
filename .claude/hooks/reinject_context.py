#!/usr/bin/env python3
"""SessionStart (compact) hook: re-inject project rules after context compaction."""
from __future__ import annotations

import json
import sys

CONTEXT = """\
[Hook: context compacted — project rules reminder]

Teams weekly report automation (메일 연동):
- Read CLAUDE.md and docs/ko/05_project_decisions.md before changing behavior.
- docs/ko/ and docs/en/ must stay in sync (same structure and meaning).
- No team-lead proxy submit; late submitters use 이번 주 보고 작성 themselves.
- Thu 13:00 deadline; auto-aggregate only if all designated targets submit on-time.
- Team lead Adaptive Cards for pending submitters / ready to aggregate / mail flow.
- Never commit .env, credentials.json, or Graph/LLM secrets.
- Agent defs: .claude/agents/ | Phase prompts: .claude/prompts/
"""


def main() -> None:
    _ = sys.stdin.read()  # SessionStart payload (optional)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": CONTEXT,
                }
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
