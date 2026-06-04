# Phase 2 Output — LLM Integration Layer

Date: 2026-06-04
Owner: @prompt-engineer
Model: claude-sonnet-4-6

---

## 1. Overview

Implements the LLM integration layer for the Teams Weekly Report Automation project.
Three async generation capabilities are exposed as a clean Python API:
individual report formatting, team aggregate report generation, and email body composition.

---

## 2. Files Created

| File Path | Role |
|---|---|
| `src/services/llm/__init__.py` | Package entry point, public symbol exports |
| `src/services/llm/client.py` | `LLMClient` — anthropic SDK wrapper with up to 2 retries |
| `src/services/llm/generation_service.py` | Three high-level async generation functions |
| `src/services/llm/prompts/__init__.py` | Prompts sub-package entry point |
| `src/services/llm/prompts/personal_report.py` | Personal report prompt template |
| `src/services/llm/prompts/team_aggregate.py` | Team aggregate prompt template |
| `src/services/llm/prompts/mail_body.py` | Email body prompt template |

---

## 3. Module Design

### 3-1. LLMClient (`client.py`)

- Wraps `anthropic.Anthropic` synchronous client.
- `complete(system, user, max_tokens, temperature)` — synchronous call with retry.
- `complete_async(...)` — async exposure via `asyncio.get_running_loop().run_in_executor`.
- Retried exceptions: `RateLimitError`, `APIStatusError`, `APIConnectionError`.
- Max attempts: 3 (1 initial + 2 retries), linear back-off of 2 s between attempts.
- Module-level singleton `get_default_client()` reads `ANTHROPIC_API_KEY` from the environment.

### 3-2. Generation Service (`generation_service.py`)

#### Domain Models (temporary dataclasses)

```
PersonalReport
  name: str          # Submitter display name
  week_period: str   # "YYYY-MM-DD ~ YYYY-MM-DD"
  this_week: str     # Work done this week
  next_week: str     # Work planned for next week
  issues: str        # Issues / blockers (default "")
  notes: str         # Special notes (default "")
  is_late: bool      # Submitted after Thursday 13:00 deadline

ChannelConfig
  team_name: str
  week_period: str
  to_recipients: list[str]
  cc_recipients: list[str]
```

#### Public async functions

| Function | Input | Output | Token limit |
|---|---|---|---|
| `generate_personal_summary(report, client?)` | `PersonalReport` | Section-formatted Korean report | 512 |
| `generate_team_aggregate(reports, channel_config, client?)` | `list[PersonalReport]`, `ChannelConfig` | 4-section team report (~1500 chars) | 2048 |
| `generate_mail_body(aggregate_content, channel_config, client?)` | `str`, `ChannelConfig` | Complete Korean email body | 1024 |

`generate_team_aggregate` internally uses `asyncio.gather` to generate personal summaries
in parallel before passing them to the team aggregate prompt.

---

## 4. Prompt Design

### 4-1. Personal Report (`personal_report.py`)

- **System:** Professional business report formatter, 100–200 chars per section, email-friendly format.
- **User template:** Submitter name, reporting week, 4 input fields. Late badge `[지각 제출]` auto-inserted when `is_late=True`.
- **Output:** 4 sections — `**이번 주 한 일**`, `**다음 주 할 일**`, `**이슈 / 블로커**`, `**특이사항**`.

### 4-2. Team Aggregate (`team_aggregate.py`)

- **System:** Formal Korean for management, total output within 1500 chars.
- **User template:** Team name, week period, member/late counts, individual formatted report blocks.
- **Output — 4 required sections:**
  1. Team overall summary (key achievements this week)
  2. Next week team plan
  3. Common issues / blockers
  4. Per-member summary (bulleted list, late submitters tagged `[지각]`)

### 4-3. Email Body (`mail_body.py`)

- **System:** Formal Korean (합쇼체), plain text without markdown.
- **User template:** To/CC recipients, team name, week period, aggregated report content.
- **Output:** Complete email body — greeting → 4-section report → sign-off.

---

## 5. Common Parameters

| Parameter | Value |
|---|---|
| Model | `claude-sonnet-4-6` |
| Temperature | `0.3` (consistent formatting) |
| Language | Korean (all prompts) |
| Templating | Python `str.format()` (no Jinja) |

---

## 6. Integration with Thursday 13:00 Aggregation Logic

- `PersonalReport.is_late = True` inserts a `[지각 제출]` badge in the personal report.
- The `[지각]` tag is preserved in the per-member section of the team aggregate report.
- When all members submit on time (before 13:00), `is_late=False` produces badge-free output.

---

## 7. Next Integration Points

- `src/services/reports/` — `ReportService` loads `PersonalReport` objects from the DB
  and calls `generate_team_aggregate`.
- `src/services/mail/` — `generate_mail_body` output is used as the Graph API mail body.
- `src/models/` — Once the shared models package is finalized in Phase 2, replace the
  temporary dataclasses in `generation_service.py`.
