"""Demo seed loaders. Run on a freshly migrated database in a caller-owned transaction.

Freeze app.core.clock at D 21:00 +07:00 before calling base_data.seed(db), then
scenarios.golden_case.seed(db). The caller commits and owns rollback/reset.
"""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.base import Base


def sync_sequences(db: Session, tables: list[str]) -> None:
    """Advance PostgreSQL serial sequences past explicitly seeded IDs.

    PostgreSQL sequences are not transactional. Call this only for demo/test data;
    the caller's rollback still removes rows but may leave gaps in generated IDs.
    """
    db.flush()
    for table_name in tables:
        table = Base.metadata.tables[table_name]
        sequence = db.scalar(
            text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
            {"table_name": table.name},
        )
        maximum = db.scalar(select(func.max(table.c.id)))
        if sequence is not None and maximum is not None:
            db.execute(
                text(
                    "SELECT setval(CAST(:sequence AS regclass), "
                    "GREATEST(:maximum, COALESCE("
                    "pg_sequence_last_value(CAST(:sequence AS regclass)), 1)), true)"
                ),
                {"sequence": sequence, "maximum": maximum},
            )
