"""Pending approvals and decisions. Routes arrive in walking-skeleton step 4."""

from fastapi import APIRouter

router = APIRouter(prefix="/approvals", tags=["approvals"])
