# Round 4 PR S — Per-ward approval and Supervisor

Base: `staging` at `14dfd95` (C1 and T3 merged). Branch: `feat/approval-two-wards`.
Contract: workflow.md 6.11, 6.21 and 9.6. LINE result notifications (#75) are excluded.

## Decisions

`APPROVAL_WARD_DECISION` records each human decision, unique by request and side.
Destination-only approval applies to free staff, including Cross-Ward and Float Pool.
An item with `source_assignment_id` also requires SOURCE, determined from that roster
row's Shift ward, independently of the nurse's home ward.

An initial approval stores one ward decision and `APPROVAL_WARD_APPROVED`. It does not
execute, finalize the request, extend its deadline or remove it from pending reads.
The last required approval finalizes the request and enters the existing assignment
path exactly once. Either side's rejection immediately finalizes the entire request
and uses the existing rejection, reserve-promotion and case-recompute path.

Head Nurses may omit side to use their own ward. An explicit opposite side gives 403.
Supervisor must name a side when two remain; when only one remains it can be inferred.
A single-ward request only accepts DESTINATION. Repeating a decided side gives 409.
Side values are semantically checked in the service after authorization and stale-state
checks, preserving 404 → 403 → 409 → 422. Rejection reasons retain the existing rules.
A corrupted `required_approver_role` cannot grant an RN authority: requests require the
HEAD_NURSE role, with Supervisor as the explicit delayed alternative.

## Supervisor and handoff

`can_decide()` is the shared authority check. Supervisor may decide any ward when
`now >= requested_at + supervisor_after_seconds`. The boundary is inclusive; expiry
remains exclusive. Early Supervisor decisions give 403 even for an already decided side.
Two decisions by one Supervisor produce two rows naming the same person and recording
`decided_as=SUPERVISOR`; they never imply two distinct human approvers.

Supervisor may list, assign and close MANUAL_HANDOFF cases in all wards immediately.
Handoff candidates still must belong to the destination ward and pass every Hard Rule;
`manages_ward()` retains its staff-membership semantics. Supervisor does not acquire
Head Nurse event-reporting or leave-editing permissions. Closure audit records the
actual role in `closed_by`.

S seeds the SUPERVISOR Role as ID 3, without adding a Supervisor staff member. W4 should
reuse that Role and add its multi-ward demo users. Existing databases receive no Role
insert from the migration; normal demo seeding/W4 data setup supplies this row.

## Locking, timeout and Auto-Approval

Human decisions retain destination Ward first, then lock destination and source Shifts
in one sorted query, Request, Offers, Case and sorted Staff. The shared helper restarts
on offer phantoms as before. One Request lock serializes both sides; the unique constraint
also prevents duplicate side rows. No source Ward lock is acquired after Shift.

Timeout takes the same sorted Shift union without Ward and bypasses human authority.
A partially approved request retains its original deadline. Timeout ends it and preserves
the first ward's history. Automatic decisions retain the explicit transaction-bound
batch context, reject transfer requests as before, and write no human ward-decision rows.
Post-commit foreign recomputation and LINE delivery retain PR A's documented behavior.

## API and UI compatibility

Pending requests add `home_ward_id`, `source_ward_id`, `wards` (side, ward, PENDING/APPROVED)
and `supervisor_from`. Reads enrich the list in batches, without per-request queries.
Supervisor time uses the current approval policy; request expiry remains its snapshot.
Auto-history reads have the same extra fields and show the approved destination side.

Decision responses add `outcome`, raw nullable `reason`, and `failed_rules`.
`is_approved` is nullable and always equals the aggregate request value:

| Outcome | is_approved |
|---|---|
| WAITING_OTHER_WARD | null |
| ASSIGNED | true |
| REJECTED | false |
| TRANSFER_CANCELLED | true |
| EXECUTION_FAILED | true |

C2 can report TRANSFER_CANCELLED through its TRANSFER_CHECK_FAILED audit, identified by
the request's exact outreach ID. Raw reason codes remain readable even after a code is
retired. D11 gives EXECUTION_FAILED while preserving the final approval.

The existing approvals page only receives compatible types and truthful messages for
WAITING_OTHER_WARD/TRANSFER_CANCELLED. Full ward-side controls, Supervisor UI, per-ward
history and richer outcome displays remain PR U. S adds no LINE result messages.

## Migration and C2 seam

`f2a7c9d4e6b8` follows T3 `c6e2b9f4a1d7`. It adds the decision table and the policy delay,
with `0 < supervisor_after_seconds < approval_timeout_seconds`. Seed delay is 600.
Existing policies receive `min(600, timeout - 1)`. Policies with timeout <= 1 abort
before DDL and need correction before upgrade. Existing requests and deadlines stay;
no historical human decisions are invented. Downgrade drops the new decision history.

The T3 transfer-writer guard remains. C1 creates no transfer candidates, so it is
unreachable in the current normal flow. Test-created transfer requests can receive
both approvals, but execution gives D11/EXECUTION_FAILED until C2 provides its writer.
Success tests use an explicit test stand-in for that future writer. C2 must replace the
guard, atomically modify/link the source and destination rows, run final transfer checks
and provide cancellation outcomes. S does not implement these transfer operations.

## Validation

Tests cover both approval orders, either-side rejection, side inference, duplicate and
wrong-side decisions, error precedence, Supervisor timing, real actor identity, timeout
after partial approval, D11, legacy transfer reasons, Auto-Approval and handoff access.
Two-connection tests cover different sides racing, the same side racing, and final
approval racing the timeout job. Migration tests cover valid backfill, impossible
policies, delay constraints, round trip and one migration head. The original
manages_ward tests remain; the legacy arbitrary-RN-role approval test now uses another
valid Head Nurse, with a separate test rejecting RN role-policy tampering.

Validation: backend **2,493 passed, 14 skipped** (opt-in solver timing harness);
frontend **316 passed**; TypeScript typecheck, isolated production build, Ruff,
Ruff format check, mypy and `git diff --check` passed. The single Alembic head is
`f2a7c9d4e6b8`. Tests used `LINE_MODE=simulation` and a dedicated test database.
The live demo database and LINE binding were not migrated or reset.
