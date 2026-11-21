"""Constants shared across layers."""

# The largest PostgreSQL bigint. Every table ID is a bigint (docs/workflow.md, D7),
# so an ID above this must be rejected by validation before it reaches the database
MAX_BIGINT = 2**63 - 1

# ROLE.name of the head nurse. No RoleName enum exists; the seed names role 2
# this way (docs/workflow.md 10.2). The role that approves a replacement and
# that reports an event about someone or something else
HEAD_NURSE_ROLE = "HEAD_NURSE"

# ROLE.name of the supervisor (round 4 PR S, docs/workflow.md 6.21). It may decide
# a request of any ward after APPROVAL_POLICY.supervisor_after_seconds, and act on
# MANUAL_HANDOFF of any ward. No seed row and no code use it yet
SUPERVISOR_ROLE = "SUPERVISOR"

# Longest reason a head nurse can give for cancelling an assignment. The text
# is copied into the event payload and the audit payload
MAX_EVENT_REASON_LENGTH = 500

# Bound approval free text stored in requests/audit and shown to candidates.
MAX_APPROVAL_REASON_LENGTH = 500

# Round 5 (docs/workflow.md 6.24). A check-in is on time up to the row's required
# arrival plus this grace period; the NO_SHOW job acts only after it
NO_SHOW_GRACE_SECONDS = 15 * 60

# Round 5 (6.24). The earliest check-in accepted, before the row's required arrival
CHECK_IN_EARLIEST_SECONDS = 60 * 60

# Round 5 (6.25). Version of STRUCTURED_HANDOVER.content
HANDOVER_CONTENT_VERSION = 1

# Round 6 (docs/workflow.md 6.27, 6.28). Defaults of the LLM allowance. Code reads
# the matching settings.llm_* value (env LLM_DAILY_CALL_CAP and so on), so they can be
# changed without a release. The cap counts every attempt the gateway sends, retries
# included, per calendar day in LLM_QUOTA_TIMEZONE
LLM_DAILY_CALL_CAP = 100
LLM_QUOTA_TIMEZONE = "Asia/Bangkok"

# Monthly spend limit of every LLM work type together, in USD. A budget alert warns;
# it does not stop calls (the daily cap does)
LLM_MONTHLY_BUDGET_USD = 20

# Largest prompt allowed per request, in tokens. A payload above it is not sent
LLM_MAX_INPUT_TOKENS = 5_000

# Most attempts one explanation or summary row may ever use across all requests of
# the user. Asking again never resets it
LLM_MAX_ATTEMPTS_PER_ROW = 4

# Model trial (6.28): cases x models x attempts. The cap is for the whole run, not per
# day (LLM_TRIAL_USAGE keeps it by run id), and the trial is counted in the monthly
# budget above
LLM_TRIAL_CASES = 30
LLM_TRIAL_MODELS = 3
LLM_TRIAL_MAX_ATTEMPTS = 2
LLM_TRIAL_CALL_CAP = LLM_TRIAL_CASES * LLM_TRIAL_MODELS * LLM_TRIAL_MAX_ATTEMPTS

# Round 6 PR F1 (docs/workflow.md 6.31, 9.8). GET /dashboard measures the gap only of
# shifts in progress or starting within this many hours of the Backend Clock, so its
# cost does not grow with every shift in the system
DASHBOARD_SHORTAGE_WINDOW_HOURS = 24
# Most shifts it lists as short, earliest first, and most recent NO_SHOW events
DASHBOARD_MAX_SHORTAGES = 20
DASHBOARD_MAX_NO_SHOWS = 10
