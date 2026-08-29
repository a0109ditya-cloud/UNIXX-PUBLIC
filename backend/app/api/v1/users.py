from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
from backend.app.db.models import User
from backend.app.schemas.user import UserRead, UserUpdate
from backend.app.services.audit_service import record_event
from backend.app.services.user_service import update_user_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)):
    return UserRead.model_validate(current_user)


@router.patch("/me", response_model=UserRead)
async def update_current_user(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await update_user_profile(
        db,
        user=current_user,
        name=payload.name,
        email=payload.email,
        status=payload.status,
    )
    await record_event(
        db,
        event_type="user_profile_updated",
        user_id=user.id,
        resource_type="users",
        resource_id=user.id,
        metadata={"changes": payload.model_dump(exclude_none=True)},
    )
    return UserRead.model_validate(user)


@router.get("/{user_id}", response_model=UserRead, status_code=status.HTTP_200_OK)
async def read_user_by_id(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.id != user_id:
        return UserRead.model_validate(current_user)
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("User not found")
    return UserRead.model_validate(user)
