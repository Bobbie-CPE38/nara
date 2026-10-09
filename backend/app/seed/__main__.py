"""Load the demo with `python -m app.seed` after starting the backend container."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.seed import base_data
from app.seed.scenarios import golden_case


def load(db: Session) -> None:
    """Populate empty application tables without deleting data or committing."""
    for table in Base.metadata.sorted_tables:
        if db.execute(select(table).limit(1)).first() is not None:
            raise ValueError(
                f"Cannot seed: {table.name} already contains data. "
                "Use a fresh demo database; no existing data has been deleted."
            )
    base_data.seed(db)
    golden_case.seed(db)


def main() -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    if ScriptDirectory.from_config(config).get_heads():
        command.upgrade(config, "head")
    else:
        print("No migrations yet: creating the demo schema from current ORM models.")
        Base.metadata.create_all(engine)

    demo_time = clock.now().replace(hour=21, minute=0, second=0, microsecond=0)
    clock.set_time(demo_time)
    try:
        with SessionLocal.begin() as db:
            load(db)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    finally:
        clock.reset()
    print(f"Golden Case loaded for {demo_time.date()}: 9 staff, 2 shifts, 7 roster assignments.")
    print("The API process clock is unchanged; /demo/reset will configure it when implemented.")


if __name__ == "__main__":
    main()
