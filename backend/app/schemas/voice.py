from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VoiceFileCreate(BaseModel):
    original_filename: str
    file_size_bytes: int | None = None
    content_type: str | None = None


class VoiceFileRead(BaseModel):
    id: str
    user_id: str
    original_filename: str
    file_format: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    duration_ms: int | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    storage_reference: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class VoiceUploadResponse(BaseModel):
    message: str
    voice_file: VoiceFileRead
