from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.db.models import VoiceAnalysis, VoiceFile
from backend.app.integrations.ai_adapter import analyze_voice_file


def _sanitize_filename(filename: str) -> str:
    safe = os.path.basename(filename)
    if not safe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return safe


async def create_voice_upload(db: AsyncSession, *, user_id: str, uploaded_file: UploadFile) -> VoiceFile:
    if uploaded_file.filename is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing filename")

    ext = Path(uploaded_file.filename).suffix.lower()
    if ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported audio extension: {ext}")

    if uploaded_file.size and uploaded_file.size > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large")

    user_dir = Path(settings.UPLOAD_DIR) / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_filename(uploaded_file.filename)
    storage_path = user_dir / safe_name
    with storage_path.open("wb") as target_file:
        shutil.copyfileobj(uploaded_file.file, target_file)

    voice_file = VoiceFile(
        user_id=user_id,
        original_filename=safe_name,
        file_format=ext.lstrip("."),
        content_type=uploaded_file.content_type,
        file_size_bytes=storage_path.stat().st_size,
        storage_reference=str(storage_path),
        uploaded_at=datetime.now(timezone.utc),
    )
    db.add(voice_file)
    await db.commit()
    await db.refresh(voice_file)
    return voice_file


async def get_voice_file_for_user(db: AsyncSession, *, user_id: str, voice_file_id: str) -> VoiceFile:
    voice_file = await db.get(VoiceFile, voice_file_id)
    if voice_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice file not found")
    if voice_file.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to access this voice file")
    return voice_file


async def create_analysis_for_voice(db: AsyncSession, *, user_id: str, voice_file_id: str) -> VoiceAnalysis:
    voice_file = await get_voice_file_for_user(db, user_id=user_id, voice_file_id=voice_file_id)
    audio_path = Path(voice_file.storage_reference)
    if not audio_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored audio file not found")

    result = analyze_voice_file(audio_path)
    prediction = result.get("prediction")
    analysis = VoiceAnalysis(
        user_id=user_id,
        voice_file_id=voice_file.id,
        model_name=result.get("model", "AASIST"),
        model_version=result.get("model_version", "1.0.0"),
        status="completed" if result.get("status") == "success" else "failed",
        prediction=prediction if prediction in {"spoof", "bonafide"} else None,
        risk_score=result.get("risk_score"),
        risk_level=result.get("risk_level"),
        result=result,
        error_message=result.get("error"),
        processed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


async def list_voice_files(db: AsyncSession, *, user_id: str) -> list[VoiceFile]:
    result = await db.execute(select(VoiceFile).where(VoiceFile.user_id == user_id).order_by(VoiceFile.uploaded_at.desc()))
    return list(result.scalars().all())


async def list_analyses_for_voice(db: AsyncSession, *, user_id: str, voice_file_id: str) -> list[VoiceAnalysis]:
    await get_voice_file_for_user(db, user_id=user_id, voice_file_id=voice_file_id)
    result = await db.execute(
        select(VoiceAnalysis).where(VoiceAnalysis.voice_file_id == voice_file_id, VoiceAnalysis.user_id == user_id).order_by(VoiceAnalysis.created_at.desc())
    )
    return list(result.scalars().all())


async def get_analysis_for_user(db: AsyncSession, *, user_id: str, analysis_id: str) -> VoiceAnalysis:
    analysis = await db.get(VoiceAnalysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    if analysis.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to access this analysis")
    return analysis
