import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.exception_handlers import register_exception_handlers
from app.api.origin_guard import AuthHttpGuard
from app.api.routes import (
    admin_staff,
    approvals,
    auth,
    cases,
    clock,
    dashboard,
    demo,
    events,
    gap,
    internal,
    line_sim,
    line_webhook,
    me,
    roster,
    unavailability,
)
from app.core.config import settings
from app.db.session import engine

logger = logging.getLogger(__name__)


def warn_if_demo_on_aws() -> None:
    """docs/workflow.md 6.33.1: a warning, not a refusal to start (AUTH-Q11 ก). No setting
    value is logged. AU4's acceptance check fails on this combination."""
    if settings.app_env == "aws" and settings.auth_mode == "demo":
        logger.warning(
            "APP_ENV=aws with AUTH_MODE=demo: X-Demo-User lets anyone act as anyone. "
            "Set AUTH_MODE=session on AWS."
        )


warn_if_demo_on_aws()

app = FastAPI(title="Staffing API")

# Register each router once; route implementations live in their own modules.
for module in (
    admin_staff,
    auth,
    demo,
    clock,
    events,
    cases,
    approvals,
    roster,
    line_sim,
    me,
    internal,
    line_webhook,
    unavailability,
    dashboard,
    gap,
):
    app.include_router(module.router)

register_exception_handlers(app)

# Added first, so CORS wraps it and a 403 from the guard still carries CORS headers
app.add_middleware(AuthHttpGuard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],  # includes X-Demo-User
    # The session cookie (round 6 PR AU1). The origins are an explicit list, never "*"
    allow_credentials=True,
)


@app.get("/health")
def health() -> JSONResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok", "database": "ok"})
    except SQLAlchemyError as exc:
        return JSONResponse(
            {"status": "error", "database": "unreachable", "detail": type(exc).__name__},
            status_code=503,
        )
