from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.exception_handlers import register_exception_handlers
from app.api.routes import approvals, cases, demo, events, line_sim, roster
from app.core.config import settings
from app.db.session import engine

app = FastAPI(title="Staffing API")

# Every router of walking-skeleton step 4 is registered here once, so a route
# PR adds routes to its own file and never edits this one
for module in (demo, events, cases, approvals, roster, line_sim):
    app.include_router(module.router)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],  # includes X-Demo-User later
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
