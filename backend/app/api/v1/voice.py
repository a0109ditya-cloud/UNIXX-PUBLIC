from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_user, get_db
from backend.app.db.models import User, VoiceAnalysis, VoiceFile
from backend.app.schemas.analysis import VoiceAnalysisRead
from backend.app.schemas.voice import VoiceFileRead, VoiceUploadResponse
from backend.app.services.audit_service import record_event
from backend.app.services.voice_service import create_analysis_for_voice, create_voice_upload, get_analysis_for_user, get_voice_file_for_user, list_analyses_for_voice, list_voice_files

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/upload", response_model=VoiceUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_voice(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    voice_file = await create_voice_upload(db, user_id=current_user.id, uploaded_file=file)
    await record_event(
        db,
        event_type="voice_uploaded",
        user_id=current_user.id,
        resource_type="voice_files",
        resource_id=voice_file.id,
        metadata={"filename": voice_file.original_filename},
    )
    return {"message": "Voice file uploaded successfully", "voice_file": VoiceFileRead.model_validate(voice_file)}


@router.get("/files", response_model=list[VoiceFileRead])
async def list_user_voice_files(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    voice_files = await list_voice_files(db, user_id=current_user.id)
    return [VoiceFileRead.model_validate(item) for item in voice_files]


@router.get("/files/{voice_file_id}", response_model=VoiceFileRead)
async def get_voice_file(
    voice_file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    voice_file = await get_voice_file_for_user(db, user_id=current_user.id, voice_file_id=voice_file_id)
    return VoiceFileRead.model_validate(voice_file)


@router.post("/files/{voice_file_id}/analyze", response_model=VoiceAnalysisRead)
async def analyze_voice_file_route(
    voice_file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analysis = await create_analysis_for_voice(db, user_id=current_user.id, voice_file_id=voice_file_id)
    await record_event(
        db,
        event_type="voice_analysis_completed",
        user_id=current_user.id,
        resource_type="voice_analysis",
        resource_id=analysis.id,
        metadata={"voice_file_id": voice_file_id, "status": analysis.status},
    )
    return VoiceAnalysisRead.model_validate(analysis)


@router.get("/files/{voice_file_id}/analyses", response_model=list[VoiceAnalysisRead])
async def list_analyses_for_file(
    voice_file_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analyses = await list_analyses_for_voice(db, user_id=current_user.id, voice_file_id=voice_file_id)
    return [VoiceAnalysisRead.model_validate(item) for item in analyses]


@router.get("/analyses/{analysis_id}", response_model=VoiceAnalysisRead)
async def get_analysis_by_id(
    analysis_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    analysis = await get_analysis_for_user(db, user_id=current_user.id, analysis_id=analysis_id)
    return VoiceAnalysisRead.model_validate(analysis)
