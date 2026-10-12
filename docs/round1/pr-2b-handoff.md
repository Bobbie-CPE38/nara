# PR 2b: Wave and response handoff

Base: `feat/round1-case-flow`. This branch is reviewed separately and enters the integration branch before PR 3 and PR 4. The integration branch goes into `staging` only after all three changes pass together.

## Implemented in 2b

- First Wave keeps the Solver's target holders, rechecks Hard Rules and the offer cap, and replaces only vacant targets. `fill_targets(..., already_selected=...)` subtracts kept people from the already rounded targets.
- Later Waves use the same plan and rank, exclude every staff member the case already contacted, and persist target credits before delivery.
- Each Wave writes one SENT offer per person using one clock read; its handler writes OFFER_SENT in rank order. The first audit row contains skipped candidates, with the first failed Hard Rule in the shared rule order (then OFFER_LIMIT_REACHED).
- Responses select the authenticated staff member's exact outreach_id. Multiple unanswered offers are allowed. Paused offers cannot be accepted, but may be rejected. Stopped cases and repeated/stale answers return 409 without writes.
- Accepted reserves have no Safety or approval row until promoted. Promotion uses response_at then id, and stops when assigned plus pending cover the case gap.
- Responses lock all case offers, the case, then all plan Staff in ID order. Foreign-case recomputes happen after the answer commits, in separate transactions. PR O adds the recovery sweep.
- The LINE simulator shows ward, shift times, per-offer Accept/Reject eligibility, reserve information and cancellation reasons. Expiry/deadline remains PR O.

## Shared interfaces

- `outreach_service.cancel_offer(db, outreach)` only changes SENT/ACCEPTED to CANCELLED, preserving response_at. Safety, Approval and completion own their audit and transaction.
- `outreach_service.promote_reserves(db, case)` processes unvalidated ACCEPTED offers oldest first. The caller already holds the case/offer/Staff locks.
- `orchestrator.recompute(db, case_id, prepare=...)` runs an optional preparation callback inside D11's savepoint before computing the status. The response and its audit remain outside that savepoint; system failures preserve the answer and return FAILED. PR 4 may pass promote_reserves after a rejection.
- `case_facts_service.get_case_fillers(db, case_id, include_reserves=True)` supplies the shared coverage semantics to Wave selection.

## PR 3 (person 2)

The temporary Safety bridge adds `outreach_id` to `safety_service.validate_accepted_candidate()` and `validate_safety.handle()`. It still uses the existing three Skeleton availability rules and existing approval-request creation. PR 3 replaces this implementation with the shared Hard Rules, records failed validations, calls cancel_offer, moves approval creation/audit to approval_service, and removes the SAFETY_VALIDATION case handler/edges and stub fixture entry as planned.

Reserve promotion currently calls `validate_safety.handle(db, case, outreach_id=...)` directly, without changing case status. If PR 3 moves this individual entry point into safety_service, it must update the promotion call in that same PR. A processed reserve must have a validation, an approval request or a cancelled offer; leaving it unchanged is treated as a system error instead of looping forever.

## PR 4 (person 3)

Approval/Execution are still the Skeleton implementation. PR 4 supplies per-person roster creation, approval rejection, promotion after rejection, conflicting-offer cancellation in other cases and cancellation of unneeded offers at completion. The current E2E verifies one approved replacement; it does not certify multi-person approval or completion before PR 4.

The acceptance-versus-last-approval two-connection test requires those real PR 4 paths. PR 2b tests same-offer concurrent acceptance, same-person acceptance across cases and concurrent next Waves from two cases sharing the pool. Do not merge this intermediate branch directly into staging.

## Migration

No new migration. Offer timeout fields and their migration stay in PR O.
