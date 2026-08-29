# VIGIL Phase 1 Backend API

## Overview

The repository now includes a FastAPI backend that wraps the existing VIGIL AI pipeline without modifying AASIST, preprocessing, or risk thresholds.

Key design goals:
- keep the AI inference contract untouched
- persist only the required Phase 1 tables
- enforce user ownership on all voice resources
- log security-relevant events to `audit_events`
- support PostgreSQL via `DATABASE_URL` and Alembic migrations

## Base URL

- local: http://localhost:8000
- API prefix: /api/v1

## Endpoints

### Auth
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET /api/v1/auth/me
- POST /api/v1/auth/logout

### Users
- GET /api/v1/users/me
- PATCH /api/v1/users/me

### Voice
- POST /api/v1/voice/upload
- GET /api/v1/voice/files
- GET /api/v1/voice/files/{voice_file_id}
- POST /api/v1/voice/files/{voice_file_id}/analyze
- GET /api/v1/voice/files/{voice_file_id}/analyses
- GET /api/v1/voice/analyses/{analysis_id}

### Health
- GET /api/v1/health/live
- GET /api/v1/health/ready

## Database model mapping

- `users` -> `User`
- `password_credentials` -> `PasswordCredential`
- `voice_files` -> `VoiceFile`
- `voice_analysis` -> `VoiceAnalysis`
- `audit_events` -> `AuditEvent`

## PostgreSQL setup

Set `DATABASE_URL` before running the app, for example:

```bash
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/vigil"
```

The project includes an Alembic migration at:

- `backend/app/db/migrations/versions/20260829_phase1_schema.py`

## Startup

```bash
uvicorn backend.app.main:app --reload
```

## Swagger

- http://localhost:8000/docs
- http://localhost:8000/redoc
