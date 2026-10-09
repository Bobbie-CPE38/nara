from fastapi import APIRouter

from app.seed.reset import reset_demo

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset() -> dict[str, str]:
    """Drop the database, migrate, load the Golden Case and freeze the clock at D 21:00."""
    demo_time = reset_demo()
    return {"status": "ok", "clock": demo_time.isoformat()}
