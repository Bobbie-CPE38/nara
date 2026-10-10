"""Demo seed loaders. Run on a freshly migrated database in a caller-owned transaction.

Freeze app.core.clock at D 21:00 +07:00 before calling load(db), or base_data.seed(db)
then scenarios.golden_case.seed(db). The caller commits and owns rollback/reset.
app.seed.reset.reset_demo() does all of this for POST /demo/reset.
"""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.base import Base


def load(db: Session) -> None:
    """Populate empty application tables without deleting data or committing."""
    # Imported here: the loaders import sync_sequences from this module
    from app.seed import base_data
    from app.seed.scenarios import golden_case

    for table in Base.metadata.sorted_tables:
        if db.execute(select(table).limit(1)).first() is not None:
            raise ValueError(
                f"Cannot seed: {table.name} already contains data. "
                "Use a fresh demo database; no existing data has been deleted."
            )
    base_data.seed(db)
    golden_case.seed(db)


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
