from __future__ import annotations

import os
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    APP_NAME: str = "VIGIL Phase 1 Backend"
    APP_VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/vigil"
    SECRET_KEY: str = "change-me-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    UPLOAD_DIR: str = "backend/uploads"
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024
    ALLOWED_AUDIO_EXTENSIONS: List[str] = [
        ".wav",
        ".flac",
        ".mp3",
        ".m4a",
        ".ogg",
        ".aiff",
        ".aif",
    ]

    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @classmethod
    def _build_cors_origins(cls) -> list[str]:
        env_value = os.getenv("CORS_ORIGINS")
        if env_value:
            return _split_csv(env_value)
        return [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def __init__(self, **values):
        super().__init__(**values)
        self.CORS_ORIGINS = self._build_cors_origins()


settings = Settings()
