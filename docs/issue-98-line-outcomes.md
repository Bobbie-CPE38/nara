# Issue #98 — final offer outcomes on LINE

This follow-up branches from staging after round 5. It covers accepted nurses and
unanswered offers; no acceptance criteria are deferred to another implementation PR.
The user reported the tested live LINE flows working on 2026-10-17 and authorized
opening the implementation PR. Review and merge remain required before closure.

## Behaviour

- Approval rejection, approval expiry and unanswered-offer expiry are distinct.
- Either ward rejecting is final. One ward approving while the other is pending
  sends no failure notification.
- Surplus offers/reserves, conflicting assignments, stopped automation, failed
  Safety and refused transfers receive their recorded cancellation outcome.
- D11 execution failure says assignment could not be confirmed, never that a
  human rejected it. Earlier successful assignments keep their Handover message.
- Every message names the offer, ward, proposed cover dates/times (Thailand time,
  including partial shifts and overnight dates). It says the nurse was not
  assigned **from this offer**, rather than cancelling another roster assignment.
- Unknown `CANCELLED` uses neutral wording without inventing a cause. Free-text
  approver notes and internal errors are not sent.
- A nurse's own rejection keeps its existing reply without a redundant push.
- The timeout job automatically pushes the expiry after committing it. Clicking
  the old Accept button also replies immediately, before or after the job:
  “ข้อเสนอนี้หมดเวลาตอบรับแล้ว จึงไม่สามารถรับข้อเสนอได้”.

## Transaction and delivery

The audit writer projects selected authoritative audit actions through
`offer_outcome_service.prepare_audit()`. This writes an immutable outcome/UI
snapshot and, in real mode with an active binding, a delivery intent in the same
transaction. This boundary is intentional: manual decisions, workflow handlers,
NO_SHOW surplus cancellation and jobs share it. It makes no network calls,
commits or new workflow-lock acquisitions. Non-outcome audits do nothing.

`(outreach_id, kind)` is unique in `offer_outcome_notification`; a second contact attempt
has a new offer ID and therefore a separate outcome. Repeated audits do not
replace the first final reason, message, recipient or retry UUID. No job scans old
audits to create messages. Simulation still records the outcome for the UI but
has NULL delivery status, with no backfill when real mode is enabled later.

The existing dispatcher handles up to 20 final notifications per sweep after
commit, in addition to its offer and Handover quotas. HTTP callers use the
existing background worker's fresh session; the regular job recovers lost work.
Locks are the existing Offer → Case → Staff helper, followed by the notification
row. Transactions end before LINE HTTP. Claims/results recheck eligibility;
leases, immutable retry keys and credential/rate-limit handling share the
existing sender's policy. Missing bindings become NO_CONTACT without attempts or
payload. Unlink/rebind never redirects an old message.

An overlapping successful Handover for the same case/person/shift suppresses a
stale failure before sending/retrying and cancels retries if detected after the
send. Unrelated cases do not suppress this outcome. As with the existing sender,
a success committed after the final pre-send check may race an HTTP call already
in flight; no database locks are held over network I/O. Similarly, recovery after
the third HTTP success but before result commit inherits the existing sender's
terminal-failure limitation.

Notification failures change only this outbox. They never change the offer,
roster, approval or case, and do not log OFFER_DELIVERY_FAILED. No additional
public endpoint, service, credential or tunnel configuration is needed.

## API and migration

- `GET /me/offers` and `/demo/line-sim/offers` add nullable `final_outcome` and
  `final_message` and `final_delivery_status`. The shared OfferList displays the final message even without
  LINE, and hides it for a confirmed assignment. Failed LINE delivery is explicitly shown. The read stays batched with a
  unique-key outer join; it adds no per-offer query or additional round trip.
- `b4e7a9c2d6f0` follows `f6b2d8a4c0e1`. It creates an empty outbox with its
  uniqueness/check constraints and due index. Upgrade preserves existing data;
  no reset or message backfill is needed. Run `alembic upgrade head` before
  using the new application code.

## Live smoke scenarios

Use the existing Quick Tunnel gate and a bound personal test LINE account:

1. Accept an offer, reject its approval on the Head Nurse web page: one clear
   rejection push, no Handover.
2. Accept another offer and let its approval expire using Demo Clock: a distinct
   approval-timeout push; the existing retry/next-candidate rules still apply.
3. Let an unanswered offer expire: receive the automatic expiry push, then press
   its old Accept button and receive the explicit expired-button reply. Repeat
   this with a press after the deadline but before the job processes expiry.
4. Accept as a reserve, then approve another nurse so the gap closes: the
   selected nurse gets Handover, the reserve gets a cancellation explaining the
   coverage is complete. Confirm ward and overnight/partial cover times.
5. Check the nurse web page shows the same final result. Automated tests cover
   failure/retry/crash, missing bindings, D11 and PostgreSQL races separately.

## Verification (2026-10-17)

- Full backend: 2,884 passed, 14 skipped (the opt-in solver timing harness).
  LINE adapters were fake; PostgreSQL used the separate `staffing_issue98_test`
  database. This includes 54 new notification/migration cases.
- Ruff, Ruff format and mypy passed (180 application source files).
- Frontend: 351 passed; typecheck and production build passed.
- Additive migration applied to the local demo without resetting its data;
  `/health` and reading `/me/offers` returned 200 with the new outcome fields.
- The user reported successful live rejection, approval-timeout and surplus-reserve
  cancellation checks. An earlier automatic unanswered-offer push failed delivery
  as recorded below. After the follow-up changes and clarification of the Demo
  scenarios, the user reported everything tested working normally and authorized
  the PR (2026-10-17). This is user-reported validation; crash, retry, uniqueness
  and concurrency guarantees were checked with fake LINE and PostgreSQL tests.


## Reserve acknowledgement and promotion

The accepted-as-reserve flag is recorded from current assigned/pending coverage
under response locks. It does not use the Solver's PRIMARY/RESERVE target. The
LINE acceptance reply explicitly says the nurse is a reserve when that remains
true after commit. Duplicate webhook events remain silent.

When Safety later creates an approval request for that reserve, its audit writes
a durable `RESERVE_PROMOTED` notification in the same transaction. It says the
nurse was selected from the reserve list and is waiting for approval, with no
assignment promise. Its unique key is separate from the later `FINAL` message.
Retry is suppressed once the request expires, is decided or the case stops.
The final-offer API joins only FINAL rows, so promotion does not duplicate offers
or appear as a cancellation/failure in the nurse page.

Migration `c5f8b0d3e7a1` follows `b4e7a9c2d6f0`, preserving existing final messages
and retry keys. It marks currently waiting reserves using the existing no-Safety,
no-request rule; this sends nothing on upgrade. Downgrade retains final history
but removes promotion rows, which cannot fit the old one-row-per-offer schema.

## Automatic expiry and diagnosing missing LINE messages

Both the internal job HTTP route and Demo Clock HTTP route have integration tests
with the real BackgroundTasks/session path and a fake LINE adapter. They push
expiry without any nurse button/read request. A first transport TIMEOUT is retried
by a later job tick, again without a nurse button; the separate expired-button
reply remains available afterwards.

A local read-only check found the reported unanswered-offer notification had
already been recorded automatically but its delivery was FAILED after three
attempts, last result TIMEOUT; the approval-timeout push was ACCEPTED/200. This is
delivery failure, not a dependency on clicking Accept. New terminal failures are
logged with safe IDs/result codes and the nurse page warns that LINE delivery
failed while retaining the final outcome. No terminal old message was manually
re-sent or relabelled successful.

Demo Clock was frozen during that check. After reset, waiting wall time does not
advance offer deadlines or scheduled retry times. Advance the Demo Clock for this
test; normal real-clock mode checks due work at each job interval (default 30s).
Network delivery cannot be promised exactly at the deadline or during an outage.


The existing concurrent-approval regression once returned roster rows in the
opposite staff order (`202, 201`). Its assertion now compares sorted staff IDs:
there must still be exactly one assignment for each of 201 and 202, but concurrent
ID allocation has no promised staff order. This is the previously recorded round
5 flake; the case-resolution and single-audit assertions are unchanged.
