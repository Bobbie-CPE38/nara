"""Round 6 PR E1 migration: rank_explanation.attempt_limit, NULL for rows nobody asked for."""

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text

from app.db.models import RankExplanation
from app.domain.enums import ExplanationStatus
from app.seed.reset import ALEMBIC_INI
from tests.integration.case_rows import short_case

REVISION = "e7c3a5d9b1f4"


def test_the_migration_follows_b1_on_a_single_head():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert len(script.get_heads()) == 1
    assert script.get_revision(REVISION).down_revision == "d2a6f9c1e4b7"


def test_downgrade_drops_only_untried_rows_nobody_asked_for(production_seeded):
    db = production_seeded
    case, items = short_case(db)
    plan_id = next(iter(items.values())).plan_id
    rows = {
        "unasked": RankExplanation(prompt_version="a", status=ExplanationStatus.PENDING),
        "unasked_tried": RankExplanation(
            prompt_version="b", status=ExplanationStatus.PENDING, attempts=1
        ),
        "asked": RankExplanation(
            prompt_version="c", status=ExplanationStatus.PENDING, attempt_limit=2
        ),
        "ready": RankExplanation(prompt_version="d", status=ExplanationStatus.READY, text="t"),
    }
    for row in rows.values():
        row.case_id = case.id
        row.plan_id = plan_id
    db.add_all(rows.values())
    db.flush()
    revision = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_revision(REVISION)

    with Operations.context(MigrationContext.configure(db.connection())):
        revision.module.downgrade()
        columns = {c["name"] for c in inspect(db.connection()).get_columns("rank_explanation")}
        assert "attempt_limit" not in columns
        left = db.execute(
            text("SELECT prompt_version FROM rank_explanation ORDER BY prompt_version")
        ).scalars()
        assert list(left) == ["b", "c", "d"]
        revision.module.upgrade()

    db.expire_all()
    limits = {
        version: limit
        for version, limit in db.execute(
            select(RankExplanation.prompt_version, RankExplanation.attempt_limit)
        ).all()
    }
    # The column comes back empty: no row counts as asked for after a round trip
    assert limits == {"b": None, "c": None, "d": None}
