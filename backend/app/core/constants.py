"""Constants shared across layers."""

# The largest PostgreSQL bigint. Every table ID is a bigint (docs/workflow.md, D7),
# so an ID above this must be rejected by validation before it reaches the database
MAX_BIGINT = 2**63 - 1
