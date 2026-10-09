"""
HTTP answers for errors that any route can meet (docs/workflow.md, section 9).

Registered once in main.py, so a route does not catch these itself. The route
must not commit after either error: get_db closes the session, and that rolls
back whatever the request had flushed.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.workflow.transitions import InvalidTransitionError
from app.workflow.orchestrator import CaseNotFoundError


def _conflict(request: Request, error: Exception) -> JSONResponse:
    # A repeated request: the case already moved on (a second ACCEPT, a double click)
    return JSONResponse({"detail": str(error)}, status_code=status.HTTP_409_CONFLICT)


def _not_found(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=status.HTTP_404_NOT_FOUND)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(InvalidTransitionError, _conflict)
    app.add_exception_handler(CaseNotFoundError, _not_found)
