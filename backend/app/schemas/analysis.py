from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class VoiceAnalysisRead(BaseModel):
    id: str
    user_id: str
    voice_file_id: str
    model_name: str
    model_version: str | None = None
    status: str
    prediction: str | None = None
    risk_score: float | None = None
    risk_level: str | None = None
    result: dict | None = None
    error_message: str | None = None
    processed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class VoiceAnalysisRequest(BaseModel):
    force: bool = False
