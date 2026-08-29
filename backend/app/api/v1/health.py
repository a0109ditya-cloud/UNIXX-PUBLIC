from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from backend.app.api.deps import get_db
from backend.app.core.config import settings
from backend.app.db.session import async_session_maker

router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live():
    return {"status": "ok", "service": settings.APP_NAME}


@router.get("/health/ready")
async def health_ready():
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok", "service": settings.APP_NAME}
    except Exception as exc:  # pragma: no cover - defensive health check
        return {"status": "not_ready", "database": "error", "detail": str(exc)}
