# Round 4 PR A — Auto-approval

Base: `staging` after T1 (#78), branch `feat/auto-approval`. No migration or new configuration.
Authoritative behavior: workflow.md 6.11, 6.22 and 9.6.

## Behavior

The due-work job runs auto-approval after offer and approval expiry, before recovery
and merge-window closure. Acceptance still goes through Safety and creates a normal
MANUAL request; it does not approve synchronously.

For each destination ward, the job locks Ward and reads an actionable pending snapshot.
Capacity is `min(ratio × active Head Nurses in the ward, incoming_count)`. Supervisor
staff do not count. No active Head Nurse means zero capacity. Fractional ratios are
compared exactly, without rounding. Equality does not trigger automation.

If the snapshot count exceeds capacity, all eligible requests in that snapshot are
decided oldest first (`requested_at`, then ID), even after the remaining queue falls
below capacity. There is no mode retained between ticks. New requests after the
snapshot wait for another tick.

Cross-Ward, Float Pool and requests with `source_assignment_id` count toward the
queue but are never automatically approved. Expired requests, stopped cases and
requests whose specific accepted offer no longer exists do not count.

Automatic decisions use `approval_service.decide_automatic()` with an explicit
transaction-bound batch context and post-commit notification list. It shares `_decide()`
with the human `decide()` entry point; no authorization or notification hooks are hidden
in `Session.info`, and no placeholder actor ID is passed.
It sets `approval_mode=AUTO`, `approver_id=NULL` and actor `system`; the approval audit
also records `pending_count`, `approver_count` and `cap`. No ward-decision row is written.
Assignment, conflicting-offer cancellation, reserve promotion and D11 use the existing
manual decision path. A D11 execution failure preserves the approval and fails the case;
being approved is not proof that an assignment succeeded.

## Transactions and concurrency

Manual decisions now lock Ward before the existing decision locks.
SQLAlchemy `with_for_update(key_share=True)` without `read=True` renders PostgreSQL
`FOR NO KEY UPDATE`, which conflicts with another `NO KEY UPDATE` on that Ward.
It is not `FOR KEY SHARE`; the Ward lock provides mutual exclusion for decisions. The timeout job
keeps its existing lock order without Ward.

The auto job prelocks the union of every eligible request's resources before deciding:
Ward → sorted Shifts → sorted Requests → sorted Offers → sorted Cases → sorted Staff.
This prevents taking a second request's Shift after retaining the first request's Staff.
A child Session uses savepoints so existing commits in the shared decision path do not release the
outer ward transaction's locks. The outer transaction commits the entire ward snapshot.

If the offer set grows during lock acquisition, restart the whole ward batch up to five
times. An unexpected batch error rolls back the whole ward, records the failed ward and
leaves it for a later tick; other wards continue. Failure logging is bounded per ward and
exception type. The process-local counter is protected by a thread lock because job
and demo requests can run concurrently. It retains at most 1,024 keys to bound memory
and logs the first failure and every 120th recurrence (about hourly at 30-second ticks).
This counter only throttles logs; it does not coordinate database decisions. The caller must have no uncommitted writes.

Foreign-case recomputes and LINE delivery are deferred until the outer commit releases
all batch locks. HTTP delivery still uses the existing response background scheduler.
Foreign-case recomputation is **best-effort**: a failed call is logged, with no dedicated
retry queue. A stale foreign case may need another event or manual recomputation.
LINE offer delivery already has durable intents; the normal job calls `dispatch_pending()`
on later ticks. This does not guarantee delivery success or add a new notification outbox.

## API and remaining integration

`GET /approvals/auto` requires an active demo identity. Head Nurses see their own ward;
Supervisors see all wards. Other roles receive 403. It returns the same fields as a
pending approval plus `decided_at`, newest decision first (ID breaks ties), at most 50.
It includes approved requests whose execution failed; consumers must inspect case/audit
results before presenting an assignment as successful.

The auto-history UI remains PR U. PR S must retain the Ward-first decision lock and
explicit batch-context validation in `decide_automatic()` when adding Supervisor/two-ward decisions. T2 is independent;
this branch includes T1's source-assignment exclusion but no T2 migration or roster work.
Both due-work HTTP responses now include sorted `auto_approved_request_ids` and
`failed_auto_approval_ward_ids`; `DueWork` also preserves the failed wards. Rendering
these fields on demo/control remains PR U.

No live LINE calls or demo reset are required to exercise PR A.

## Validation

`tests/integration/test_auto_approval.py` covers threshold equality, draining the entire
snapshot, fractional/ceiling capacity, zero approvers, manual-only source exclusions,
expiry/stale requests, oldest-first ordering, authorization, D11, atomic batch rollback,
scoped/limited history, real two-connection Job/Job and Job/human races, post-auto approval-timeout regression, HTTP result reporting, and a second
connection proving foreign notifications run only after the outer Ward lock is released.

Validation on this branch: backend **2,336 passed, 14 skipped** (the opt-in solver
timing harness); all **25** auto-approval tests passed. `ruff check .`,
`ruff format --check .` and `mypy app` passed. Frontend changes are limited to the clock-response TypeScript fields; typecheck and
all **313** frontend tests passed. Alembic
retains the single T1 head `a9c3e7f1b5d2`; `git diff --check` passed.
