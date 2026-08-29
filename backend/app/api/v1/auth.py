from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
from backend.app.db.models import User
from backend.app.schemas.auth import AuthLogin, AuthRegister, Token
from backend.app.schemas.user import UserRead, UserWithToken
from backend.app.services.audit_service import record_event
from backend.app.services.auth_service import authenticate_user, issue_token_for_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserWithToken, status_code=status.HTTP_201_CREATED)
async def register(
    payload: AuthRegister,
    db: AsyncSession = Depends(get_db),
):
    user = await register_user(db, email=payload.email, password=payload.password, name=payload.name)
    token = issue_token_for_user(user)
    await record_event(
        db,
        event_type="user_registered",
        user_id=user.id,
        resource_type="users",
        resource_id=user.id,
        metadata={"email": user.email},
    )
    result = UserRead.model_validate(user)
    return {**result.model_dump(), "access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=UserWithToken)
async def login(payload: AuthLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, email=payload.email, password=payload.password)
    token = issue_token_for_user(user)
    await record_event(
        db,
        event_type="user_login",
        user_id=user.id,
        resource_type="users",
        resource_id=user.id,
        metadata={"email": user.email, "login_time": datetime.now(timezone.utc).isoformat()},
    )
    result = UserRead.model_validate(user)
    return {**result.model_dump(), "access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserRead.model_validate(current_user)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    return {"message": "Token has been discarded by the client. Logout successful.", "user_id": current_user.id}
