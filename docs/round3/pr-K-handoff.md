# PR K — LINE account linking

Branch: `feat/line-account-linking`, based on staging after PR #66. No frontend
or real LINE calls are added. PR X's migration must follow `d7f0b3c5e9a2`.

## Local administrator commands

Run inside the Backend container while its API is running:

```sh
docker compose exec backend python -m app.line_accounts issue-code --staff-id 201
docker compose exec backend python -m app.line_accounts unlink --staff-id 201
```

The CLI authenticates with `INTERNAL_JOB_SECRET` to fixed loopback endpoints:
`POST /internal/line-accounts/{staff_id}/issue-code` and `.../unlink`.
There is no frontend or unauthenticated issuance/unlink endpoint. This is an
administrator command for people already trusted with the Backend environment.
The endpoints are not exposed by the Quick Tunnel proxy, which only permits
POST `/line/webhook`. Keep the internal secret private.

Commands execute in the running Backend, so codes use its Clock, including the
frozen Demo Clock. Issuance returns `Cache-Control: no-store`; the CLI displays
`LINK <code>` only after the Backend commits. Deliver the command privately to
the staff member, who sends it in a one-to-one chat with the LINE OA. Do not paste
codes into a PR, screenshot, log or shared terminal transcript. The CLI does not
print remote response bodies or secrets on error.

## Rules and atomicity

- A code has 192 random bits, is case-sensitive, expires after 10 Backend-clock
  minutes, and stores only a SHA-256 hash. At `now >= expires_at` it is invalid.
  Demo Clock advances, rather than elapsed wall time, control expiry when frozen.
- `LINK <code>` is dispatched before the binding lookup. Sender identity comes
  only from a signed, one-to-one LINE message, never from a staff ID in the text.
- Staff must be active. A bound staff member or an already-owned LINE UID is
  refused; bindings are never automatically overwritten, including inactive
  Contact rows. Issue-code also requires an explicit unlink first if bound.
- Code consumption, Contact binding, `LINE_ACCOUNT_LINKED` audit and webhook
  dedup commit in one transaction. Any unexpected failure rolls everything
  back and returns 503. Expected refusals get their own terminal dedup row and
  reply with HTTP 200, following PR L. Event replay has no second effect/reply.
- Lock order is Staff → code → that staff's Contact rows. No Offer/Case locks
  are taken. The code update checks unused, unrevoked and not expired atomically.
  Concurrent claims of one UID by different staff are settled by the database's
  `uq_contacts_line_uid` constraint; the losing code remains unused.
- Unlink clears `line_uid`, preserving Contact ID, `line_id` and `is_active`, and
  revokes all unused codes of the staff member. It works for inactive staff too.
  Audit actor is `system` per workflow 7.1; there is one audit per cleared Contact.
  Repeating unlink adds no audit when nothing was bound. Revoked codes cannot
  rebind an old account; issue a fresh code after unlink.
- Audit payloads contain only `contact_id` and `staff_id`, with no case/event ID,
  raw code, hash or LINE UID. Linked audit actor is the target staff's user actor.

## Offers and binding changes

A newly linked account receives future real-mode offers. Existing `NO_CONTACT`
intents are terminal and are not retroactively resent. Offers remain `SENT` and
can be answered from the simulator/nurse page or expire under the existing rule.
Before each pending send/retry, the sender checks that the current active binding
still matches the immutable recipient. After unlink/rebind, a mismatched intent
becomes `NO_CONTACT`, without push, failure audit or case recompute. Payload/key
are never redirected to a new recipient. A network request already in flight
at unlink cannot be recalled; late answers are refused by the binding lookup.

## Migration and verification

Migration `d7f0b3c5e9a2` follows PR L's `c6e9a2b4d8f1` and adds
`LINE_ACCOUNT_LINK_CODE` and uniqueness for non-null `CONTACTS.line_uid`, including
inactive rows. Multiple NULL contacts remain allowed. Duplicate legacy UIDs
cause an explicit migration failure, with no UID in the error; an administrator
must resolve ownership first. No history is silently reassigned or deleted.

Tests use the isolated `_test` database and fake LINE adapter. They cover signed
LINK/replay, expiry boundaries, refusals, rollback at audit/dedup, administration
authentication and Clock, unlink/relink, old-recipient delivery, migration round
trip/duplicate preflight, CLI errors and real two-connection races for one code,
one event, shared UID and unlink vs link. Generic migration checks compare the
full schema to ORM metadata and require a single head.

Validation: Backend **2,119 passed, 14 skipped** (opt-in timing harness); Ruff
check, Ruff format check, mypy and `git diff --check` passed. Frontend unchanged.

Local developer DB migration, public Tunnel checks and actual LINE linking are
not performed by these tests. For real testing, apply the migration to the chosen
development DB, configure LINE real mode and the optional Quick Tunnel proxy,
Verify the URL, issue a code, send it privately in LINE, then create a fresh offer
for the linked staff member. Follow `dev/line-webhook-proxy/README.md` for gate
checks and record what has actually passed.
