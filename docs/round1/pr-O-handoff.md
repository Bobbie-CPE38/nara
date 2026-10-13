# PR O: Offer timeout and recovery sweep

Base: `staging` at `53459ce`, after the integration of #40, #41 and #42.

## Behaviour

- Seed `OUTREACH_POLICY.offer_timeout_seconds = 300`, integer > 0. Sending reads that policy once and stores each wave's immutable `expires_at = sent_at + duration` from one backend-clock reading.
- Answerable interval: `clock.now() < expires_at`. Both ACCEPT and REJECT at or after the deadline return 409 without changing the offer or audit. Only the job writes TIMEOUT.
- Reads, open/paused-offer facts and offer-cap checks exclude overdue SENT offers even before the job tick. Accepted candidates, reserves and approvals do not time out.
- LINE simulator explains both overdue SENT and TIMEOUT offers and displays the stored deadline and trusts backend action flags. It does not compare browser real time with the frozen demo clock.
- `job_service.run_due_work()` expires SENT offers first, runs the recovery sweep, then closes due merge windows. A case ending through timeout can release its queued window in the same tick. Existing demo/internal route response shapes stay unchanged.
- Each expired offer gets one OFFER_TIMEOUT audit (`outreach_id`, `staff_id`, Outreach Agent). Timeout does not fill response_at. Case completion cancels only unexpired SENT offers and unused ACCEPTED reserves. Overdue SENT offers remain for the job to write TIMEOUT and its audit, including after RESOLVED or MANUAL_HANDOFF. Whole-wave expiry occurs before recomputing; next waves never resend already contacted staff.

## Recovery and transactions

Recovery first reads facts without row locks as a hint. Healthy waits take no workflow locks. Only apparently stranded cases acquire Offer → Case → whole-plan Staff locks and recheck the same predicate before writing. Each case is processed in its own transaction. State and deadlines are rechecked after waits. If a concurrent wave appeared before Staff locks were acquired, release and restart the complete lock order rather than locking new offers late.

Timeout updates/audits are outside D11's workflow savepoint. Workflow failure keeps TIMEOUT and fails the case; timeout/audit failure rolls back that case, excludes it from recovery during the same tick, and retries next tick. Other cases continue. Repeated failures log a stack trace on the first and every 120th consecutive failure per operation/case/exception type; the process-local counter is bounded to 1,024 entries and cleared on success. Retries still run each tick.

For a legacy/inconsistent case outside waiting or stopped statuses, expiry commits TIMEOUT and its audits without calling recompute or changing case status, and logs that manual repair is required. Such an offer does not retry forever, but the case remains stuck: recovery scans only WAITING_RESPONSE and WAITING_APPROVAL. An operator must repair or close the case; expiry is not case recovery.

The sweep recovers WAITING_RESPONSE cases with no SENT offers, or only paused offers plus an uncontacted candidate. Legitimate paused-only waits remain until another case produces an outcome or the offer expires. It also repairs stale WAITING_APPROVAL after cancellation leaves no actionable request; healthy pending approvals remain untouched. Reserve promotion uses the real Safety path.

Lock retries may roll back the transaction: callers must have no uncommitted writes. Exhausting the five lock-set attempts raises a separate OutreachLockRetryError; LINE responses return 503 with Retry-After: 1, while stale/expired offers remain 409.

## Migration and deployment

Migration `a4b8c2d6e9f1` follows `f3a7c1d9e5b2` and leaves one Alembic head. Existing policy rows adopt 300 seconds; the temporary database default is removed. Offers with sent_at are backfilled with sent_at + 300 seconds, including historical offers. NULL remains allowed for unsent/historical rows; SENT requires an expiry.

A legacy SENT row with no sent_at aborts upgrade before changing schema. Repair its actual timestamp or explicitly close it before retrying; no invented timestamp and no automatic reset. Previously overdue SENT rows expire on the first due-work run. As for the integration deploy, no case should remain in the removed SAFETY_VALIDATION case phase.

Before using the local stack, apply the migration (`docker compose exec -T backend alembic upgrade head`). Demo reset is optional for a fresh demonstration and remains destructive; it is not required by this migration.

## Remaining scope

Approval deadlines are intentionally absent. Real LINE delivery still requires an outbox. Policy administration/version selection remains outside round 1; expiry is immutable when the policy changes.

## Validation

Backend: 1,428 tests passed, including E2E, existing case-flow regressions, upgrade/backfill/refusal tests, two-connection races, lock-set retries/exhaustion, unlocked healthy waits and locked rechecks. Frontend: 188 tests passed. Ruff, formatting, mypy, TypeScript typecheck, production build and Prettier checks for the changed frontend files passed. No frontend lint script/configuration is currently provided by the project. The migration was exercised only on the guarded test database; the developer database was not reset or migrated.
