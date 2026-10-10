"""Local LINE stand-in. Offers are read from CANDIDATE_OUTREACH by the simulator.

No network call or separate message store: the database transaction owns the
offer, so a failed workflow round leaves no delivered mock offer behind.
"""


def send_offer(*, staff_id: int, outreach_id: int) -> None:
    """Simulate successful delivery; the caller persists the SENT offer."""
