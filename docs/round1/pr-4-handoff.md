# PR 4: Per-candidate approval and execution

Base: `feat/round1-case-flow` at `61bb6d0`, including PR 2b and PR 3.

## Implemented

- Pending reads exclude stopped cases and requests without an ACCEPTED offer of the same case/item. The same predicate controls pending gap coverage. Cancellation preserves undecided requests as inactive history; deciding them returns 409 instead of creating a fake rejection or acquiring extra approval locks in foreign cases. Reports and other consumers counting pending requests must also use `case_facts_service.accepted_offer_for_request()` rather than counting `is_pending=True` alone.
- Decide one request at a time. Keep 404 → 403 → 409 ordering; a stopped case returns 409. Rejection requires a nonblank reason; reason length is checked in the service after 404 → 403 → 409: at most 500 stored characters (422 otherwise). Rejection text is trimmed before this check and before storage; approval text is preserved as supplied, preserves the candidate response time, cancels that candidate's offer and promotes reserves in acceptance order through real Safety.
- Approval creates that candidate's replacement roster row immediately. Other approvals may remain pending, and a partially staffed case may continue outreach or go to MANUAL_HANDOFF without removing assignments already committed.
- No execution recheck of the approved candidate (Q38). After assignment, shared scheduling Hard Rules check the candidate's other offers for overlap, rest, daily/weekly hours and consecutive shifts; cancel only unsafe offers.
- The EXECUTING handler only verifies assigned coverage, cancels unused SENT/reserve offers, records all assignment IDs and cancellation IDs, and resolves the case. Approved candidates retain their ACCEPTED history.
- Offer reads include `is_assigned`, so LINE simulator can confirm an individual's shift even while the multi-person case is still waiting for another approval.
- `head_nurse_reject` overlays the Golden Case. HTTP tests reject 201 with a reason, accept 202 and approve 202.

## Transactions and locks

The decision/audit is flushed before `recompute(..., prepare=...)`. Assignment, foreign cancellations, reserve promotion and completion run inside D11's savepoint. A system failure keeps the decision, rolls back these workflow writes, and fails the case; a later failure cannot remove an assignment committed by an earlier approval.

Shift → selected approval request → all own-case offers plus this candidate's live foreign offers in one query ordered by ID → case → whole-plan Staff ordered by ID. Refresh ORM state after waits. If new offers appeared before the Staff lock was acquired, release and restart the whole order before writing the decision; after five attempts raise the distinct retryable `ApprovalLockRetryError` (HTTP 409). A missing/ambiguous accepted offer raises `ApprovalOfferConflictError` (HTTP 409). Never add Offer locks after holding case/Staff.

Foreign notifications happen after commit, each foreign case in its own transaction. Include cases whose offers were cancelled (not merely those still SENT), and staff released when reserves are cancelled or fail promotion. PR O still owns recovery after notification failure and offer expiry.

## Integration checks

Tests use real HTTP handlers and PostgreSQL connections. Cover two-person approval, reserve promotion/failure, partial assignment with exhaustion, unsafe and safe foreign offers, duplicate/stopped requests, D11 rollback, simultaneous per-person approvals, acceptance racing the last approval (both orders and simultaneous), and a foreign wave committing while approval waits for Staff.

Tests also cover cancellation of a foreign ACCEPTED offer with an existing pending request, resumption of that running case to another wave, stale approval/rejection returning 409, and completion cancelling an unassigned pending candidate. The foreign-ACCEPTED fixture simulates legacy/external data: the normal response path already prevents two concurrent unresolved acceptances by one staff member.

No migration. PR 5 still owns the approvals UI's rejection reason input; PR O owns deadlines/timeouts. Before merging the integration branch into staging, update it from staging and run the full backend/E2E and frontend checks.

## Validation

Full backend suite: 1,386 passed, including E2E. Frontend: 186 passed. Ruff, format check, mypy, TypeScript typecheck and production build passed. No developer database reset was used.
