"""
HTTP answers for errors that any route can meet (docs/workflow.md, section 9).

Registered once in main.py, so a route does not catch these itself. The route
must not commit after either error: get_db closes the session, and that rolls
back whatever the request had flushed.
"""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import CaseNotFoundError
from app.domain.workflow.transitions import InvalidTransitionError


def _conflict(request: Request, error: Exception) -> JSONResponse:
    # Two requests for one case at once: both passed the route's own lookup
    # before either committed, and orchestrator.resume() rejected the second.
    # A repeat that arrives later is the route's job (seams 3 and 7), not this
    return JSONResponse({"detail": str(error)}, status_code=status.HTTP_409_CONFLICT)


def _not_found(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=status.HTTP_404_NOT_FOUND)


# Only these keys of a validation error leave an /auth response. FastAPI's default also
# returns `input` (the submitted value, a password included) and `ctx`, which can repeat
# it (docs/workflow.md 6.33.2: a password is never returned)
_SAFE_ERROR_KEYS = ("type", "loc", "msg")


def _is_auth_path(path: str) -> bool:
    return path == "/auth" or path.startswith("/auth/")


async def _validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    if not _is_auth_path(request.url.path):
        return await request_validation_exception_handler(request, error)
    detail = [
        {key: item[key] for key in _SAFE_ERROR_KEYS if key in item} for item in error.errors()
    ]
    return JSONResponse(
        {"detail": jsonable_encoder(detail)},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(InvalidTransitionError, _conflict)
    app.add_exception_handler(CaseNotFoundError, _not_found)
