# Phase 3 Security Review Report

**Date:** 2026-06-04
**Author:** @security-reviewer
**Review Target:** Phase 2 implementation (commit 5654, 2026-06-04)
**Review Standard:** ADR-SEC-001 through ADR-SEC-007

---

## 1. ADR-SEC Compliance Matrix

| ADR | Title | Status | Notes |
|---|---|---|---|
| ADR-SEC-001 | Delegated OAuth only — no application permissions | **PARTIAL** | Graph scope over-declaration (Issue #1) |
| ADR-SEC-002 | Team lead registration dual-gate: INITIAL_ADMIN or self | **PARTIAL** | Env variable name mismatch + missing audit log (Issues #2, #3) |
| ADR-SEC-003 | Triple-gate mail send (gate_check) | **COMPLIANT** | All three conditions re-verified server-side from DB |
| ADR-SEC-004 | Refresh token atomic write | **COMPLIANT** | refresh -> access -> metadata write order confirmed |
| ADR-SEC-005 | Channel isolation: channel_id from activity only, mismatch = reject + log | **NON-COMPLIANT** | ActivityValidator middleware not implemented (Issue #4) |
| ADR-SEC-006 | No proxy submission: actor == owner hardcoded | **COMPLIANT** | `actor_aad_id != target_aad_id` raises immediately |
| ADR-SEC-007 | Bot JWT verification: mandatory pre-route middleware | **PARTIAL** | BotFrameworkHttpAdapter used correctly but empty APP_ID is silently accepted (Issue #5) |

**Summary:** Of 7 ADRs, 3 are fully compliant, 3 are partially compliant, and 1 is non-compliant.

---

## 2. Security Issues Found

### Issue #1 — [CONFIRMED] Graph scope over-declaration (ADR-SEC-001 violation)

**File:** `src/services/mail/token_manager.py` lines 186–190
**File:** `src/api/routes/auth.py` lines 92–94

Both `token_manager.py`'s `refresh_token()` method and `auth.py`'s `_SCOPES` constant request:

```
openid profile email offline_access User.Read Mail.ReadWrite Mail.Send
```

ADR-SEC-001 requires delegated OAuth only with least-privilege scopes. The Graph endpoints actually used by `graph_client.py` are: draft create/update/delete (Mail.ReadWrite), send (Mail.Send), and channel member list (ChannelMember.Read.All). `ChannelMember.Read.All` is absent from the scope list. `User.Read` is only used for the `/me` fallback in `auth.py` (lines 240–246) during OID extraction and is not needed beyond that point.

**Severity:** Low (scopes in use are functionally required, but `User.Read` retention violates least-privilege)

---

### Issue #2 — [CONFIRMED] Env variable name mismatch breaks dual-gate (ADR-SEC-002 violation)

**File A:** `src/adapters/teams/handlers/register_team_lead.py` line 112
**File B:** `src/infra/config.py` lines 53–54

`register_team_lead.py`'s `_is_initial_admin()` function reads `os.environ.get("INITIAL_ADMIN_AAD_IDS", "")` directly.

`config.py`'s Settings model declares the same concept with `alias="INITIAL_ADMIN_USER_IDS"`.

`team_lead_service.py` (line 47) reads `self._settings.initial_admin_user_ids` through the Settings object.

Result: the handler layer reads `INITIAL_ADMIN_AAD_IDS` while the service layer reads `INITIAL_ADMIN_USER_IDS`. If an operator sets only `INITIAL_ADMIN_USER_IDS`, Gate 1 in the handler always returns `False`. On a new channel, Gate 2a ("no team lead yet — allow self-registration") triggers, meaning **any user can register as team lead for a new channel.**

**Severity:** High — unauthorized user can register as team lead on any new channel

---

### Issue #3 — [CONFIRMED] No audit log on team lead registration failure (ADR-SEC-002 violation)

**File:** `src/adapters/teams/handlers/register_team_lead.py` lines 53–54
**File:** `src/services/acl/team_lead_service.py` lines 112–118

ADR-SEC-002's "감시 로그" (audit log) section requires recording the following actions on failure:

- `unauthorized_team_lead_registration`
- `unauthorized_team_lead_transfer`

When ACL check fails in `register_team_lead.py` (lines 53–54) a reply is sent to the user, but no audit log entry is created. The `TeamLeadRegistrationError` raise path in `team_lead_service.py` (lines 114–118) likewise has no audit logging.

**Severity:** Medium — reduces ability to detect and investigate unauthorized registration attempts

---

### Issue #4 — [CONFIRMED] ActivityValidator middleware not implemented (ADR-SEC-005 violation)

**File:** `src/services/reports/submission_service.py` (entire file)
**File:** `src/adapters/teams/handlers/register_team_lead.py` (entire file)
**File:** `src/api/dependencies.py` (entire file)

ADR-SEC-005 requires:

1. `channel_id` extracted exclusively from `Activity.channelData.teamsChannelId` (payload untrusted)
2. `activity_channel_id != request_channel_id` mismatch → reject immediately + write audit log

`submission_service.py` accepts `channel_id` as a caller-supplied parameter (line 47). `register_team_lead.py`'s `_get_channel_id()` (lines 152–157) correctly extracts from `activity.conversation.id`, but the service layer performs no cross-check to verify that the incoming `channel_id` matches the activity's channel.

`dependencies.py`'s `inject_channel_config` reads `channel_id` from a query parameter (line 26), which is a request-payload value with no activity-derived cross-check.

No `ActivityValidator` middleware implementing cross-channel mismatch detection exists in any file.

**Severity:** High — no layer detects or blocks cross-channel data access attempts

---

### Issue #5 — [CONFIRMED] Empty APP_ID allows Bot JWT bypass (ADR-SEC-007 partial violation)

**File:** `src/api/routes/bot.py` lines 44–51

```python
_APP_ID: str = os.environ.get("MICROSOFT_APP_ID", "")
_APP_PASSWORD: str = os.environ.get("MICROSOFT_APP_PASSWORD", "")
```

`os.environ.get(..., "")` falls back to an empty string when the env var is missing. The Bot Framework SDK treats an empty `app_id` as **emulator mode and skips JWT validation entirely**, accepting all incoming activities. If these variables are accidentally omitted in production, JWT verification is completely disabled.

ADR-SEC-007 requires Bot JWT verification as mandatory pre-route middleware with no conditional bypass.

**Severity:** High — missing env var in production silently disables authentication

---

### Issue #6 — [CONFIRMED] Scheduler HMAC missing timestamp freshness check

**File:** `src/api/dependencies.py` lines 83–112
**File:** `src/api/routes/scheduler.py` lines 57–65

`verify_hmac_signature()` uses `{timestamp}:{body}` as the HMAC message but does not validate the freshness of `timestamp`. An attacker who captures a valid HMAC-signed request can replay it at any future time and pass verification.

**Severity:** Medium — mitigated by internal network policy, but replay window is unlimited without this check

---

### Issue #7 — [SUSPECTED] In-process state store race condition in auth.py

**File:** `src/api/routes/auth.py` lines 47–52

`_pending_states` is a module-level global dict. In multi-worker deployments (Gunicorn, etc.) it is not shared across processes, causing CSRF state validation to fail. The code comment (lines 44–46) acknowledges this and recommends Redis for production, but no fix was applied in Phase 2.

**Severity:** Medium (harmless in single-worker deployment; breaks PKCE flow in multi-worker)

---

## 3. Fix Recommendations

### Fix #1 — Issue #2: Unify env variable name

`_is_initial_admin()` in `register_team_lead.py` (line 112) must not read `os.environ` directly. It should call `get_settings().initial_admin_user_ids` so both layers read from the same source of truth. See `phase-3-security-patches.md` Fix-A.

### Fix #2 — Issue #3: Add audit log on registration failure

Add audit log writes at the ACL rejection branch in `register_team_lead.py` and at the `TeamLeadRegistrationError` raise point in `team_lead_service.py`. See Fix-B.

### Fix #3 — Issue #4: Implement ActivityValidator middleware

Introduce a helper that extracts `channel_id` from `Activity.channelData.teamsChannelId` and asserts it matches any service-layer channel_id before processing. Reject on mismatch and write audit log. See Fix-C.

### Fix #4 — Issue #5: Fail startup on empty APP_ID

Add a startup guard in `bot.py` that raises `RuntimeError` if `MICROSOFT_APP_ID` or `MICROSOFT_APP_PASSWORD` is empty. See Fix-D.

### Fix #5 — Issue #6: Add HMAC timestamp freshness window

Extend `verify_hmac_signature()` to reject timestamps older than 300 seconds. See Fix-E.

### Fix #6 — Issue #7: Redis-backed state store (Phase 4 recommendation)

Replace `_pending_states` with Redis TTL keys before multi-worker deployment. Not an immediate blocker for single-worker Phase 3.

---

## 4. Phase 2 Security Checklist Results

| Item | Result |
|---|---|
| Delegated OAuth only (no app permissions) | PASS (graph_client.py delegated-only) |
| Least-privilege Graph scopes | FAIL (User.Read retained unnecessarily) |
| Team lead registration: identity from activity only | PASS (register_team_lead.py) |
| Team lead registration: INITIAL_ADMIN or self-register gate | FAIL (env var name mismatch) |
| Team lead registration failure audit log | FAIL (not implemented) |
| Triple-gate mail send (server-side DB re-verify) | PASS |
| No auto-send before approval | PASS |
| Refresh token atomic write | PASS |
| channel_id from activity only + mismatch rejection | FAIL (ActivityValidator missing) |
| No proxy submission (actor == owner) | PASS |
| Bot JWT verification mandatory | FAIL (empty APP_ID silently accepted) |
| Scheduler HMAC verification | PASS (HMAC implemented; freshness only missing) |
| Token values never logged | PASS |
| Token values never returned to client | PASS |

**Summary:** 9 passed, 5 failed out of 14 items.
