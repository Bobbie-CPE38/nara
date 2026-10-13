"""Which ward a head nurse may act on (docs/workflow.md section 6.12, R2-Q21).

One definition for approval decisions and the manual exits of MANUAL_HANDOFF.
The caller checks the role; this checks the ward.
"""


def manages_ward(*, home_ward_id: int, ward_id: int) -> bool:
    """A head nurse acts only on shifts of their own ward."""
    return home_ward_id == ward_id
