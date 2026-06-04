#!/usr/bin/env python3
"""PostToolUse hook: warn when only docs/ko or docs/en was edited."""
from __future__ import annotations

import json
import sys
from pathlib import PurePosixPath


def normalize(path: str) -> str:
    return path.replace("\\", "/").lower()


def is_ko_doc(path: str) -> bool:
    p = normalize(path)
    return p.startswith("docs/ko/") and p.endswith(".md")


def is_en_doc(path: str) -> bool:
    p = normalize(path)
    return p.startswith("docs/en/") and p.endswith(".md")


def paired_path(path: str) -> str | None:
    p = normalize(path)
    if is_ko_doc(p):
        return p.replace("docs/ko/", "docs/en/", 1)
    if is_en_doc(p):
        return p.replace("docs/en/", "docs/ko/", 1)
    return None


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = event.get("tool_input") or event.get("toolInput") or {}
    paths: list[str] = []

    file_path = tool_input.get("file_path") or tool_input.get("filePath")
    if file_path:
        paths.append(file_path)

    for edit in tool_input.get("edits") or []:
        fp = edit.get("file_path") or edit.get("filePath")
        if fp:
            paths.append(fp)

    warnings: list[str] = []
    for path in paths:
        pair = paired_path(path)
        if not pair:
            continue
        # Compare relative to cwd; hook runs from project root
        from pathlib import Path

        if not Path(pair).exists():
            warnings.append(
                f"Edited {normalize(path)} but paired file missing: {pair}. "
                f"Update docs/ko and docs/en together."
            )

    if warnings:
        msg = "DOC SYNC WARNING:\n" + "\n".join(warnings)
        print(msg, file=sys.stderr)
        # Non-blocking: exit 0 so edit proceeds, stderr surfaces to Claude
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
