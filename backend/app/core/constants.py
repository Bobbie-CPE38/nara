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
