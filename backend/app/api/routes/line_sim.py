"""LINE simulator for the demo: a candidate's offers and answers.

Kept apart from demo.py, which only resets the demo. Routes arrive in
walking-skeleton step 4.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/demo/line-sim", tags=["line-sim"])
