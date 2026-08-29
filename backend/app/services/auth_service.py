from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.db.models import PasswordCredential, User


async def register_user(db: AsyncSession, *, email: str, password: str, name: str | None = None) -> User:
    normalized_email = email.strip().lower()
    existing = await db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = User(email=normalized_email, name=name)
    db.add(user)
    await db.flush()

    credential = PasswordCredential(
        user_id=user.id,
        password_hash=hash_password(password),
        hashing_algorithm="bcrypt",
        password_changed_at=datetime.now(timezone.utc),
    )
    db.add(credential)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, *, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    user = await db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    credential = await db.get(PasswordCredential, user.id)
    if credential is None or not verify_password(password, credential.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user


def issue_token_for_user(user: User) -> str:
    return create_access_token(subject=user.email)
