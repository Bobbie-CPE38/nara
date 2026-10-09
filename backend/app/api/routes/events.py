"""Event intake (docs/workflow.md, section 3). Routes arrive in walking-skeleton step 4."""

from fastapi import APIRouter

router = APIRouter(prefix="/events", tags=["events"])
