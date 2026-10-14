"""Public LINE callback: signature authentication, not demo-header authentication."""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.api.dependencies import DbSession
from app.core.config import settings
from app.services import line_background_service, line_webhook_service

router = APIRouter(prefix="/line", tags=["line"])
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def webhook(request: Request, db: DbSession, tasks: BackgroundTasks) -> JSONResponse:
    if not settings.real_line_enabled:
        raise HTTPException(503, "Real LINE is not configured")
    body = await request.body()
    if not line_webhook_service.valid_signature(body, request.headers.get("x-line-signature")):
        raise HTTPException(401, "Invalid LINE signature")
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise ValueError("Invalid webhook body")
        for event in payload["events"]:
            if (
                not isinstance(event, dict)
                or not isinstance(event.get("webhookEventId"), str)
                or not 1 <= len(event["webhookEventId"]) <= 256
            ):
                raise ValueError("Invalid webhook event")
    except ValueError as error:
        db.rollback()
        raise HTTPException(400, "Invalid webhook payload") from error
    line_background_service.configure(db, tasks)
    failed = False
    for event in payload["events"]:
        try:
            await run_in_threadpool(line_webhook_service.process_event, db, event)
        except Exception as error:
            db.rollback()
            failed = True
            logger.error("LINE webhook event deferred (%s)", type(error).__name__)
    # Preserve post-commit work for successful events even when another event
    # failed. Raising HTTPException would discard the response's background tasks.
    return JSONResponse({"ok": not failed}, status_code=503 if failed else 200, background=tasks)
