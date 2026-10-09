"""Register ORM tables on Base.metadata for Alembic autogeneration.

Timestamp values must be supplied using app.core.clock.now(), not database defaults.
The remaining model modules will register their referenced tables when merged.
"""

from app.db.models.approval_request import ApprovalRequest
from app.db.models.attendance import Attendance
from app.db.models.audit_log import AuditLog
from app.db.models.candidate_outreach import CandidateOutreach
from app.db.models.contact import Contact
from app.db.models.structured_handover import StructuredHandover

__all__ = [
    "ApprovalRequest",
    "Attendance",
    "AuditLog",
    "CandidateOutreach",
    "Contact",
    "StructuredHandover",
]
