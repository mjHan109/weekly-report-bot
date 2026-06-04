# Requirements Specification for Teams Weekly Report Automation

> **Documentation sync:** `docs/ko/01_requirements_spec.md`

## 1. Objective
Teams Bot weekly reports. **Targets designated by team lead.** Wait for **self-submission** from missing members — **no team lead proxy.** Team lead gets **Adaptive Cards** for wait state and mail preview path.

## 2. Core Commands
| Command | Who | Purpose |
|---|---|---|
| `보고 대상 지정` | Team lead | Designate targets |
| `이번 주 보고 작성` | Targets | Task Module (on-time; **late self-submit if missed 13:00**) |
| `팀 주간 보고 취합` | Team lead | Manual aggregate when late/miss at 13:00 |
| `팀장 등록` | Admin / team lead self | Register team lead |

## 3. Scenarios
### 3.1 Personal Report
On-time before 13:00; **late: non-submitters submit themselves** — no proxy.

### 3.1.1 Thu 10:00 / 3.1.2 Thu 13:00
- Missing at 13:00: channel asks **self-submit**; **team lead Adaptive Card** — pending list, mail blocked
- All on-time at 13:00: **auto-aggregate** + team lead card with **mail actions**

### 3.1.3 All submitted (incl. late)
- **Team lead Adaptive Card:** all submitted, **`팀 주간 보고 취합`** → then preview + **`메일 작성`**

## 4. Functional Requirements
FR-013–FR-020 as in ko doc; **FR-021** team lead status cards (pending / ready to aggregate / mail preview path).

## 5–8
See `05_project_decisions.md`, `CLAUDE.md`
