"""Request-scoped queues of primitive data, run only after the HTTP response.

Deliveries use a fresh Session, never a request's Session or ORM objects.
Reply tokens are short-lived, so replies run before the offer delivery sweep.
The durable offer-row outbox survives a lost/crashed background task.
"""

from dataclasses import dataclass, field

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


@dataclass
class Work:
    case_ids: set[int | None] = field(default_factory=set)
    replies: list[tuple[str, str]] = field(default_factory=list)


def _run(work: Work) -> None:
    from app.services import line_delivery_service, line_webhook_service

    for token, message in work.replies:
        line_webhook_service.send_reply(token, message)
    if not work.case_ids:
        return
    case_ids = (
        [None]
        if None in work.case_ids
        else sorted(case_id for case_id in work.case_ids if case_id is not None)
    )
    for case_id in case_ids:
        with SessionLocal() as db:
            line_delivery_service.dispatch_pending(db, case_id=case_id)


def configure(db: Session, tasks: BackgroundTasks) -> None:
    """Install once, before processing; registering in dependency teardown is too late."""
    if db.info.get("line_background_tasks") is tasks:
        return
    work = Work()
    db.info["line_background_tasks"] = tasks
    db.info["line_delivery_scheduler"] = work.case_ids.add
    db.info["line_reply_scheduler"] = lambda token, message: work.replies.append((token, message))
    tasks.add_task(_run, work)
