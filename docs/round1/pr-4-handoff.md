# PR 4: Per-candidate approval and execution

Base: `feat/round1-case-flow` at `61bb6d0`, including PR 2b and PR 3.

## Implemented

- Pending reads exclude stopped cases while preserving undecided request rows as history. They never fabricate a rejection or decision to clean up a stopped case.
- Decide one request at a time. Keep 404 → 403 → 409 ordering; a stopped case returns 409. Rejection requires a nonblank reason; all decision reasons are limited to 500 characters (422 otherwise), preserves the candidate response time, cancels that candidate's offer and promotes reserves in acceptance order through real Safety.
- Approval creates that candidate's replacement roster row immediately. Other approvals may remain pending, and a partially staffed case may continue outreach or go to MANUAL_HANDOFF without removing assignments already committed.
- No execution recheck of the approved candidate (Q38). After assignment, shared scheduling Hard Rules check the candidate's other offers for overlap, rest, daily/weekly hours and consecutive shifts; cancel only unsafe offers.
- The EXECUTING handler only verifies assigned coverage, cancels unused SENT/reserve offers, records all assignment IDs and cancellation IDs, and resolves the case. Approved candidates retain their ACCEPTED history.
- Offer reads include `is_assigned`, so LINE simulator can confirm an individual's shift even while the multi-person case is still waiting for another approval.
- `head_nurse_reject` overlays the Golden Case. HTTP tests reject 201 with a reason, accept 202 and approve 202.

## Transactions and locks

The decision/audit is flushed before `recompute(..., prepare=...)`. Assignment, foreign cancellations, reserve promotion and completion run inside D11's savepoint. A system failure keeps the decision, rolls back these workflow writes, and fails the case; a later failure cannot remove an assignment committed by an earlier approval.

Shift → selected approval request → all own-case offers plus this candidate's live foreign offers in one query ordered by ID → case → whole-plan Staff ordered by ID. Refresh ORM state after waits. If new offers appeared before the Staff lock was acquired, release and restart the whole order before writing the decision; after five attempts return 409. Never add Offer locks after holding case/Staff.

Foreign notifications happen after commit, each foreign case in its own transaction. Include cases whose offers were cancelled (not merely those still SENT), and staff released when reserves are cancelled or fail promotion. PR O still owns recovery after notification failure and offer expiry.

## Integration checks

Tests use real HTTP handlers and PostgreSQL connections. Cover two-person approval, reserve promotion/failure, partial assignment with exhaustion, unsafe and safe foreign offers, duplicate/stopped requests, D11 rollback, simultaneous per-person approvals, acceptance racing the last approval (both orders and simultaneous), and a foreign wave committing while approval waits for Staff.

No migration. PR 5 still owns the approvals UI's rejection reason input; PR O owns deadlines/timeouts. Before merging the integration branch into staging, update it from staging and run the full backend/E2E and frontend checks.

## Validation

Full backend suite: 1,367 passed, including E2E. Frontend: 186 passed. Ruff, format check, mypy, TypeScript typecheck and production build passed. No developer database reset was used.
