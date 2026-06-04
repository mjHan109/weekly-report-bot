#!/usr/bin/env python3
"""PreToolUse hook: block dangerous shell commands and secret file writes."""
from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath

DENY_JSON = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
    }
}


def deny(reason: str) -> None:
    payload = dict(DENY_JSON)
    payload["hookSpecificOutput"]["permissionDecisionReason"] = reason
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def check_bash(command: str) -> None:
    cmd = command.strip()
    lower = cmd.lower()

    if re.search(r"\brm\s+-rf\b", lower) or re.search(r"\brm\s+-[^\s]*r", lower):
        deny("Destructive rm command blocked by security hook.")

    if re.search(r"git\s+push\b[^;\n]*--force", lower) or " push -f " in f" {lower} ":
        if re.search(r"\b(main|master)\b", lower):
            deny("Force push to main/master blocked by security hook.")

    secret_git_patterns = [
        r"git\s+add\b[^;\n]*\.env\b",
        r"git\s+add\b[^;\n]*credentials",
        r"git\s+add\b[^;\n]*secret",
        r"git\s+commit\b[^;\n]*\.env\b",
    ]
    for pattern in secret_git_patterns:
        if re.search(pattern, lower):
            deny("Staging/committing likely secret files blocked by security hook.")

    if re.search(r"git\s+commit\b[^;\n]*(-a|--all)", lower) and re.search(
        r"\.env|credentials|secret", lower
    ):
        deny("Commit that may include secret files blocked by security hook.")


def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def check_write(path: str) -> None:
    p = normalize_path(path)
    name = PurePosixPath(p).name.lower()
    parts = [part.lower() for part in PurePosixPath(p).parts]

    if name == ".env" or (name.endswith(".env") and not name.endswith(".env.example")):
        deny("Writing .env files blocked. Use .env.example for templates.")

    if name in {"credentials.json", "client_secret.json", "secrets.json"}:
        deny(f"Writing secret file '{name}' blocked by security hook.")

    if "secret" in name and not name.endswith(".example") and name not in {
        ".gitkeep",
        "security_guard.py",
    }:
        deny(f"Writing file with 'secret' in name blocked: {name}")

    if ".claude/settings.local.json" in p:
        deny("Writing .claude/settings.local.json blocked by security hook.")


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = event.get("tool_name") or event.get("toolName") or ""
    tool_input = event.get("tool_input") or event.get("toolInput") or {}

    if tool_name == "Bash":
        command = tool_input.get("command") or ""
        if command:
            check_bash(command)
    elif tool_name in {"Write", "Edit", "MultiEdit"}:
        file_path = tool_input.get("file_path") or tool_input.get("filePath") or ""
        if file_path:
            check_write(file_path)
        if tool_name == "MultiEdit":
            for edit in tool_input.get("edits") or []:
                fp = edit.get("file_path") or edit.get("filePath") or ""
                if fp:
                    check_write(fp)

    sys.exit(0)


if __name__ == "__main__":
    main()
