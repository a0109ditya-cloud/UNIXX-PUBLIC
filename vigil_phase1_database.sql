-- ============================================================
-- VIGIL - PostgreSQL Database | Phase 1
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;


-- ============================================================
-- 1. USERS
-- ============================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name VARCHAR(150),

    email CITEXT NOT NULL UNIQUE,

    status VARCHAR(30) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'suspended')),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    last_login_at TIMESTAMPTZ
);


-- ============================================================
-- 2. AUTHENTICATION
-- ============================================================

CREATE TABLE password_credentials (
    user_id UUID PRIMARY KEY,

    password_hash TEXT NOT NULL,

    hashing_algorithm VARCHAR(30) NOT NULL DEFAULT 'argon2id',

    password_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    failed_login_count INTEGER NOT NULL DEFAULT 0
        CHECK (failed_login_count >= 0),

    locked_until TIMESTAMPTZ,

    CONSTRAINT fk_password_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 3. VOICE FILES
-- ============================================================

CREATE TABLE voice_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL,

    original_filename TEXT NOT NULL,

    file_format VARCHAR(20),

    content_type VARCHAR(100),

    file_size_bytes BIGINT
        CHECK (file_size_bytes >= 0),

    duration_ms BIGINT
        CHECK (duration_ms >= 0),

    sample_rate_hz INTEGER
        CHECK (sample_rate_hz > 0),

    channels INTEGER
        CHECK (channels > 0),

    -- Reference to protected file/object storage.
    -- Actual audio is not stored directly in PostgreSQL.
    storage_reference TEXT NOT NULL UNIQUE,

    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_voice_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 4. VOICE ANALYSIS
-- ============================================================

CREATE TABLE voice_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID NOT NULL,

    voice_file_id UUID NOT NULL,

    model_name VARCHAR(100) NOT NULL,

    model_version VARCHAR(50),

    status VARCHAR(30) NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'processing',
                'completed',
                'failed'
            )
        ),

    prediction VARCHAR(50)
        CHECK (
            prediction IN ('spoof', 'bonafide')
        ),

    risk_score NUMERIC(5,2)
        CHECK (
            risk_score >= 0
            AND risk_score <= 100
        ),

    risk_level VARCHAR(30)
        CHECK (
            risk_level IN (
                'LOW',
                'MEDIUM',
                'HIGH',
                'CRITICAL',
                'UNKNOWN'
            )
        ),

    result JSONB,

    error_message TEXT,

    processed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_analysis_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_analysis_voice_file
        FOREIGN KEY (voice_file_id)
        REFERENCES voice_files(id)
        ON DELETE RESTRICT
);


-- ============================================================
-- 5. AUDIT EVENTS
-- ============================================================

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID,

    event_type VARCHAR(100) NOT NULL,

    resource_type VARCHAR(100),

    resource_id UUID,

    -- Store only non-sensitive metadata here.
    metadata JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_audit_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE RESTRICT
);


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_voice_files_user
    ON voice_files(user_id, uploaded_at DESC);

CREATE INDEX idx_voice_analysis_user
    ON voice_analysis(user_id, created_at DESC);

CREATE INDEX idx_voice_analysis_voice_file
    ON voice_analysis(voice_file_id, created_at DESC);

CREATE INDEX idx_audit_events_user
    ON audit_events(user_id, created_at DESC);

CREATE INDEX idx_audit_events_type
    ON audit_events(event_type, created_at DESC);


-- ============================================================
-- AUTOMATIC updated_at FOR USERS
-- ============================================================

CREATE OR REPLACE FUNCTION update_users_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER users_updated_at_trigger
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_users_updated_at();