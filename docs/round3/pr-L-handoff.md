# PR L — Real LINE delivery and webhook responses

Branch: `feat/line-messaging`, based on staging after PR 0. This PR does not
implement LINK-code issuance, unlinking or the nurse page (PR K and PR N).

## Configuration

Default: `LINE_MODE=simulation`. Tests and existing simulator flows need no secrets.
To enable real delivery set `LINE_MODE=real`, `LINE_CHANNEL_SECRET` and
`LINE_CHANNEL_ACCESS_TOKEN` in the backend environment. Missing/empty secrets
keep simulation; the webhook responds 503 until real mode is configured.
Secrets are Pydantic SecretStr values and never returned or logged.

On AWS PR D loads secrets from Parameter Store. Do not commit a populated env
file. The public endpoint is `POST /line/webhook`, exempt only this exact path
from PR D's Basic Auth gate. Enable Use webhook and Webhook redelivery in LINE
Developers, then Verify the HTTPS URL. The signed verification body with
`events: []` returns 200.

## Delivery and migration

Migration `c6e9a2b4d8f1` follows `b7d3e5a1c9f2`. Existing offers get no intent;
upgrading never sends historical messages. Real-mode waves write a pending
intent, fixed recipient/body and UUID on each offer in their own transaction.
`sent_at` and `expires_at` retain the existing meaning: deadline starts when
the workflow offers the shift, not when LINE accepts the push.

After the workflow commits, dispatch tries the new case's pending intents.
The job also dispatches after expiry, recovery and window work, so a crash
before the first call is recoverable. A sweep attempts at most 20 offers.

Sender lock order is the shared Offer → Case → whole-plan Staff order. It
commits a unique lease/claim before HTTP, then reacquires locks to persist the
result. HTTP timeout is 5 seconds; the claim lease is 60 seconds, using backend
clock time. A crashed attempt consumes an attempt; an expired lease retries
with the same retry key. No network call holds workflow locks.

- Delivery status `ACCEPTED` means **LINE accepted the API request**, not that
  the candidate accepted or read it. Offer status remains `SENT`.
- HTTP 2xx and confirmed retry-key 409 finish delivery.
- Timeout/5xx consume attempts, max three. Next attempt is due after 30 seconds.
- 429 does not consume an attempt; retries stop at the offer deadline.
- 401/403 do not consume an attempt, stop this sweep and log a configuration
  error. Another tick can resume after configuration is repaired.
- Other 4xx or three failed attempts set the live offer to `FAILED`, write one
  `OFFER_DELIVERY_FAILED` and recompute through the orchestrator. D11 protects
  that outcome if subsequent workflow work fails.
- Accepted, cancelled, expired or stopped-case offers are not retried or
  overwritten. Overdue SENT rows are left for the existing timeout audit.
- No active unambiguous LINE binding is a permanent delivery failure. PR L
  tests use Contact fixtures; real end-to-end account linking needs PR K.

## Webhook

Signature is constant-time Base64 HMAC-SHA256 over the raw body. It is checked
before JSON parsing or database writes. Sender identity comes from an active,
unambiguous Contact plus active Staff and its existing audit Actor. Postback
data contains only `outreach_id` and `response=ACCEPT|REJECT`; ownership is
checked by `record_response()`. No demo header is trusted by the webhook.

The optional `after_lock` callback inserts the event ID after the shared lock
helper finishes any transaction restarts. Its flush is outside D11, alongside
the answer, and both commit together. Duplicate event IDs are acknowledged
without repeating audit, Safety, Approval or chat replies. Expected business
refusals get a terminal event row and HTTP 200; unexpected failures roll back
and return 503 for LINE redelivery. Each event owns one transaction, so an
earlier event in a multi-event request remains processed if a later one fails.

Replies are post-commit, best effort and never retried. Expired offers get an
expiry explanation. Unsupported event types are acknowledged; PR K extends
the dispatcher for LINK messages using the same dedup table.

## Verification and remaining scope

Integration tests cover signed/unsigned requests, accept/reject replay,
ownership, expiry, rollback, immutable push content/key, claims and restarts,
delivery error classes, and late-result protection. Real PostgreSQL tests
force an actual offer-set lock restart, send duplicate events concurrently,
race two senders, and accept while a network send is blocked. Migration tests
check a single head, history backfill and ORM/schema agreement.

All HTTP traffic is replaced by deterministic doubles in CI, including tests
of real-mode paths. No test credentials are production credentials.

Real LINE delivery, HTTP latency and account settings still need validation
with the team's channel via Tunnel or PR D's AWS environment. No live LINE
test, developer-database migration, PR K command or AWS deployment is claimed
by this implementation.
