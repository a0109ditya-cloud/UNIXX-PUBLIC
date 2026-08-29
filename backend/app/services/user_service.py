from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import User


async def update_user_profile(db: AsyncSession, *, user: User, name: str | None = None, email: str | None = None, status: str | None = None) -> User:
    if name is not None:
        user.name = name
    if email is not None:
        existing = await db.scalar(select(User).where(User.email == email.lower()))
        if existing is not None and existing.id != user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        user.email = email.lower()
    if status is not None:
        user.status = status
    await db.commit()
    await db.refresh(user)
    return user
