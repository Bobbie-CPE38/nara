# Round 5 H2 — LINE Handover delivery and check-in

H2 follows H1, N1 and L5. No new deployment service or credential is needed. The existing `LINE_MODE`, Channel secret and access token apply. N2 remains responsible for NO_SHOW detection and late-arrival recovery; H2 delegates check-in to N1's shared service, so later N2 behaviour applies to LINE too.

## Durable Handover messages

`handover_service.ensure()` prepares an intent only for a newly inserted snapshot in configured real mode. Snapshot, roster, audit, recipient, payload and retry key commit together. Simulation and pre-H2 snapshots stay unsent; upgrading or binding a LINE account later does not backfill messages.

`line_delivery_service.dispatch_pending()` handles up to 20 offers and 20 Handovers per sweep. Existing approval/orchestration and the manual assignment path dispatch after commit; HTTP requests enqueue the existing background worker with its own session. The job also recovers pending intents, including future N2 restoration intents whose callers miss immediate dispatch. Callers must finish their transaction before dispatching.

Handover claims and results lock SHIFT → ROSTER_ASSIGNMENT → STRUCTURED_HANDOVER. They check ASSIGNED and Clock < effective end, including partial-shift ends. A future assignment is active already. Case status is deliberately ignored: RESOLVED cases need delivery too. Locks and transactions end before LINE HTTP. The normal cancellation/network race remains possible after releasing locks; finish rechecks activity and never overwrites roster or case state.

The recipient, message and retry UUID stay immutable. Each retry checks the current active binding; unlink/rebind stops the intent as NO_CONTACT instead of redirecting it. Missing bindings at creation get NO_CONTACT with no payload, retry key or attempt. Inactive assignments become CANCELLED. No automatic retry is scheduled for terminal states.

The retry policy is shared with offers: 60-second leases; 30-second retry delay; at most three counted attempts; 2xx/409 accepted; 400-class permanent failures stop; 429/401/403 defer without consuming attempts, with 401/403 stopping the entire sweep. Transport timeouts and other retryable failures stop after three attempts. As with offers, a crash after the third accepted HTTP call but before recording its result can leave a terminal FAILED after recovery; Handover failure never fails the case, cancels the roster, removes the snapshot or writes OFFER_DELIVERY_FAILED. The web snapshot remains available.

Messages contain the snapshot's ward, effective cover interval, reason, patient count, requirements and coworkers, followed by a check-in button. The button instructions include the exact inclusive opening and exclusive closing times with dates, seconds and Thailand timezone, computed by the shared attendance rules (including replacement creation times and partial-shift ends). Already prepared/sent payloads remain immutable; the wording applies to new intents. Text is capped at 4,900 characters; the complete snapshot remains available from the nurse/case APIs. No LLM is called.

## Check-in

Send `CHECKIN <shift_id>` (case-insensitive, whitespace accepted) from the nurse's bound personal LINE account, or use the Handover button (`action=CHECK_IN&shift_id=<id>`). No staff identifier is accepted in the command. Button actions must have exactly those two keys once each; shift IDs must be positive signed-bigint values. Group/room senders and inactive/unbound accounts cannot check in.

The adapter calls `attendance_service.check_in(source=SELF)` with identity/actor from the active binding. Its optional `after_lock` callback joins webhook-event dedup to the service's existing Shift/Roster locking transaction. Both new and repeated check-ins remember the event before commit. Retrying the same event or using another event for the same shift creates one Attendance and one attendance audit. A new event for an existing check-in returns its original time/result, including after the shift ends.

N1 rules remain unchanged: earliest arrival minus 60 minutes inclusive, effective end exclusive, on-time through arrival plus 15 minutes inclusive. Replacement arrival is max(effective start, creation time). Expected refusals are acknowledged and deduplicated with a safe reply; unexpected failures roll back event/Attendance/audit together and return 503 for retry. The first LINE reply confirms success with the stored Thailand time and on-time/late result. Later distinct events say the nurse already checked in and show that original time/result; they never reset it. Redelivery of the identical webhook event remains a no-op without another reply. `CheckInResult.already_checked_in` is internal reply metadata and does not change the web response shape. Reply failure does not undo a successful check-in. Signed webhook verification, LINK and offer actions retain their existing handling.

## Approval visibility after accepting an offer

A signed LINE acceptance uses the same `record_response()` / Safety / request creation path as the web simulator. A candidate needed for the remaining gap who passes Safety gets a pending request; `GET /approvals?pending=true` includes it for the Head Nurse page (which polls every two seconds). H2 includes an integration test from a signed acceptance by 201 to that API read as 900. Acceptance acknowledgements alone do not promise a pending approval: reserves wait for promotion, Safety failures produce no request, and expired/closed/decided requests leave the pending list. This does not add Head Nurse LINE notifications.

## Migration and verification

Migration `f6b2d8a4c0e1` follows H1 `e8c4b2a6f0d9`, adds delivery fields/checks/due index, and needs no data cleanup or backfill. H1's earlier head test now checks its position in the chain. If N2 or another migration merges first, rebase this migration onto staging's current head and update the head tests.

Tests use isolated PostgreSQL and fake LINE adapters: transaction rollback, repeated ensure, retry/permanent/rate/config failures, lease recovery, immutable payload, unlink/rebind, inactive/ended roster, simulation history, check-in bounds/identity/refusals/dedup/rollback and concurrent workers/check-ins. Migration tests preserve existing snapshots/attendance and exercise checks and offline SQL. Existing HTTP/background regression tests verify request transactions close before blocked LINE I/O.

Real LINE end-to-end validation is still required separately after upgrading/restarting the local demo deliberately. No development demo database was reset or migrated for these tests. For a manual test: configure real LINE, bind a nurse, complete an approval/manual assignment, wait for the Handover, advance the demo clock into its check-in window, then press the button. Verify the attendance audit is SELF and repeated presses keep one row. The Quick Tunnel still targets only the reviewed loopback webhook proxy; no new public route is needed.

Verification on this branch: full backend 2,746 passed, 14 timing tests skipped; Ruff, Ruff format and mypy (174 source files) passed. The container inherits LINE_MODE=real; L5 fixtures isolate simulation tests and replace all real-mode LINE calls. No frontend files changed.

Follow-up check-in wording verification: 142 targeted attendance, LINE and approval tests passed, including dates across midnight, replacement creation after shift start and partial-shift endings; Ruff and mypy passed.
