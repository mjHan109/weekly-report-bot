# Claude Code Hooks

Project hooks registered in `.claude/settings.json`.

| Script | Event | Role |
|---|---|---|
| `security_guard.py` | PreToolUse (Bash, Write/Edit) | Block dangerous commands and secret file writes |
| `reinject_context.py` | SessionStart (`compact`) | Re-inject CLAUDE.md / `05` rules after compaction |
| `doc_sync_warn.py` | PostToolUse (Write/Edit) | Warn if `docs/ko/` edited without paired `docs/en/` file |

**Apply changes:** restart Claude Code session or run `/hooks` to reload.

Tests (from project root):

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' | python .claude/hooks/security_guard.py
echo '{"tool_name":"Write","tool_input":{"file_path":".env"}}' | python .claude/hooks/security_guard.py
```
