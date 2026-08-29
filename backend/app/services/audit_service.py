from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AuditEvent


async def record_event(
    db: AsyncSession,
    *,
    event_type: str,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        event_metadata=metadata or {},
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_user_events(db: AsyncSession, user_id: str) -> list[AuditEvent]:
    result = await db.execute(select(AuditEvent).where(AuditEvent.user_id == user_id).order_by(AuditEvent.created_at.desc()))
    return list(result.scalars().all())
