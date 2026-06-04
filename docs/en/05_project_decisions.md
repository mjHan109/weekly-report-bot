# Project Decisions (Confirmed)

> **Documentation sync rule:** Sync with `docs/ko/05_project_decisions.md`.

## 1. Reporting Week
- **Confirmed:** previous Thu 13:00:01 through current Thu 13:00:00 (KST)
- **Formal deadline:** every Thursday 13:00 (KST) for on-time submission

### 1.1 Report Targets
- **Team lead designates** per-channel targets via `보고 대상 지정`
- All gates use **designated targets only**

### 1.2 Post-13:00 Submission (No Proxy)
- **No team lead proxy submit.**
- **Designated targets who missed 13:00** may still **`이번 주 보고 작성` themselves** (late self-submit)
- Log `submitted_after_deadline=true`

### 1.3 Thu 10:00 Reminder
- **Channel** message to **non-submitters among targets**

### 1.4 Thu 13:00 Processing
#### A. All targets on-time before 13:00
- **Auto-aggregate**; team lead **Adaptive Card** with preview + **`메일 작성`**

#### B. Non-submitters at 13:00
- **Channel** alert: ask non-submitters to self-submit
- **Team lead Adaptive Card:** missing list, **「N pending · waiting for submit · mail blocked」**
- **No auto-aggregate**; wait for **self-submission**

#### C. All submitted after late self-submits
- **Team lead Adaptive Card:** **「all submitted · ready to aggregate」** + **`팀 주간 보고 취합`**
- After manual aggregate → preview card → **`메일 작성`** flow
- **Manual aggregate only** if any miss at 13:00 or any late submit

### 1.5 Mail Preconditions
- All targets submitted + aggregation complete + team lead send approval

## 2. Input UI
- **Task Module** — designated targets write their own report (on-time / late self-submit same flow)
- **Adaptive Card** — personal/aggregate preview, **team lead status and follow-up action cards**

## 3. Team Aggregation
| Condition | Aggregation |
|---|---|
| All designated targets submitted on-time before 13:00 | **Auto** |
| Any miss at 13:00 or any late self-submit | **Manual** (`팀 주간 보고 취합`, team lead only) |

## 4. Team Lead Registration
- `팀장 등록` — **initial admin only** + **team lead self** only

## 5. Mail To/CC · Graph · Channel
- Delegated OAuth (confirmed), per-channel isolation, To/CC designated by team lead

## 6. DB Candidates
- `ChannelReportTarget`, `PersonalReport.submitted_after_deadline`, `TeamReport.aggregation_mode` (auto|manual)
- ~~`submitted_by_team_lead`~~ — not used

## 7. Completion Criteria
- All designated targets submitted + aggregation complete + team lead mail send approved

## 8. Commands (Korean MVP)
- `보고 대상 지정`, `이번 주 보고 작성`, `팀 주간 보고 취합`, `팀장 등록`
- Cards: `메일 작성`, `수정 사항 입력`, `취소`, `발송`, (team lead) aggregate via card button
