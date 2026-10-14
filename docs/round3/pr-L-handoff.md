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

After the workflow commits, HTTP paths queue background work and send the
HTTP response before LINE network calls. Replies run first; delivery uses a
fresh Session, never the request Session. The `get_db` dependency has function
scope: its Session closes before the response and background work, so even
post-commit read transactions cannot retain locks while LINE is blocked.
The internal job and demo-clock HTTP routes also queue delivery through get_db. Direct service calls without a
background scheduler dispatch synchronously after commit.
The job also dispatches after expiry, recovery and window work, so a crash
before the first call is recoverable. A sweep attempts at most 20 offers,
reloading due rows after each result so
new waves created by failed delivery can be sent in the same sweep. Remaining
work is picked up on the next job tick.

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
- No active unambiguous LINE binding sets delivery status `NO_CONTACT`. The
  offer stays `SENT`, with no payload, HTTP attempts, failure audit or recompute.
  The nurse can answer from the simulator or nurse page; unanswered offers
  expire under the existing rule. PR L
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
and return 503 for LINE redelivery. Each event owns one transaction, so a
failed first event does not prevent later events from committing. All events
are processed before returning 503 if any failed; only failed events retry.

Replies run after the HTTP response, best effort and never retried. Rejections
are acknowledged as rejections, without acceptance wording. Expired offers get an
expiry explanation. Unsupported event types are acknowledged; PR K extends
the dispatcher for LINK messages using the same dedup table.

## Verification and remaining scope

Integration tests cover signed/unsigned requests, accept/reject replay,
ownership, expiry, rollback, immutable push content/key, claims and restarts,
delivery error classes, and late-result protection. Real PostgreSQL tests
force an actual offer-set lock restart, send duplicate events concurrently,
race two senders, accept while a network send is blocked, and verify that the
HTTP response is sent before blocked LINE reply/push calls finish. Migration tests
check a single head, history backfill and ORM/schema agreement.

All HTTP traffic is replaced by deterministic doubles in CI, including tests
of real-mode paths. No test credentials are production credentials.

Real LINE delivery, HTTP latency and account settings still need validation
with the team's channel via the development-only Quick Tunnel and local
HTTP filter below, or PR D's AWS environment in round 6. No live LINE
test, developer-database migration, PR K command or AWS deployment is claimed
by this implementation.

## Local LINE testing before round 6

Person 3 uses Cloudflare Quick Tunnel: no Cloudflare account, purchased domain
or tunnel token is required. Its temporary `trycloudflare.com` hostname changes
when the tunnel restarts; update and Verify the LINE webhook URL each time.

Route LINE → Quick Tunnel → a loopback-only local HTTP filter → Backend.
The filter forwards only the exact `/line/webhook` path, preserving the raw
request body and `x-line-signature`. All other paths return 404, including
`/line/webhook/`, `/line/webhook/anything`, `/demo/reset` and `/internal/...`.
The public webhook path has no `/api` prefix. Backend signature checks remain
required. Do not point Quick Tunnel directly at the backend port; the filter,
not cloudflared ingress, enforces the path restriction.

Before opening the tunnel, verify the signed webhook and denied paths locally;
repeat the checks through the public URL. Person 3 owns this setup and shares
secret-free reproduction instructions with people 1 and 2. Local tunnel/filter
configuration and LINE secrets stay outside the repo. No cloudflared process,
container or configuration belongs in the main Compose file or AWS deployment.

If the organisers do not permit the tunnel, or the tunnel/filter is not ready,
use the fake LINE API and simulator and record that live integration remains
untested. In round 6, switch LINE to the AWS HTTPS endpoint and stop the tunnel.

References: [Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
