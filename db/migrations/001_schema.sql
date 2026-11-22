-- 001_schema.sql
-- Core schema for PhishCoach AI (Supabase Postgres)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users (anonymized; no raw PII stored here)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    anon_id TEXT UNIQUE NOT NULL,
    role_name TEXT NOT NULL,
    department TEXT NOT NULL,
    seniority TEXT NOT NULL DEFAULT 'mid',
    arm TEXT NOT NULL CHECK (arm IN ('control', 'treatment')),
    app_role TEXT NOT NULL DEFAULT 'employee' CHECK (app_role IN ('employee', 'security_admin', 'hr_viewer')),
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    auth_user_id UUID UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Red-flag taxonomy (populated by ingest_kb.py)
CREATE TABLE IF NOT EXISTS red_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    difficulty_tier INTEGER NOT NULL CHECK (difficulty_tier BETWEEN 1 AND 3)
);

-- Knowledge base chunks with Postgres full-text search (populated by ingest_kb.py)
CREATE TABLE IF NOT EXISTS kb_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tsv TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_chunks_tsv ON kb_chunks USING GIN (tsv);

-- Campaigns
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by UUID REFERENCES users(id),
    brief_json JSONB NOT NULL,
    target_filter JSONB NOT NULL DEFAULT '{}'::jsonb,
    wave_no INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'live', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Templates generated for campaigns
CREATE TABLE IF NOT EXISTS templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    email_json JSONB NOT NULL,
    planted_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    difficulty INTEGER NOT NULL DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 3),
    source TEXT NOT NULL DEFAULT 'llm' CHECK (source IN ('llm', 'fallback', 'admin_edit')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Delivered simulations
CREATE TABLE IF NOT EXISTS simulations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_id UUID NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, user_id)
);

-- User interaction events (idempotent per simulation + type)
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('opened', 'clicked', 'replied', 'submitted', 'reported', 'ignored')),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (simulation_id, type)
);

CREATE INDEX IF NOT EXISTS idx_events_user_ts ON events(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_sim ON events(simulation_id);

-- Coaching & practice chat sessions
CREATE TABLE IF NOT EXISTS coaching_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    simulation_id UUID REFERENCES simulations(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('feedback', 'chat')),
    turns INTEGER NOT NULL DEFAULT 0,
    outcome TEXT,
    messages_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL DEFAULT 'llm' CHECK (source IN ('llm', 'fallback', 'static_control')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ
);

-- Risk scores per user
CREATE TABLE IF NOT EXISTS risk_scores (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    score NUMERIC(5,2) NOT NULL DEFAULT 0,
    band TEXT NOT NULL DEFAULT 'Low' CHECK (band IN ('Low', 'Medium', 'High')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Remediation queue (high-risk or repeat-failure users appear once while pending)
CREATE TABLE IF NOT EXISTS remediation_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'launched', 'dismissed')),
    campaign_id UUID REFERENCES campaigns(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_remediation_unique_pending
    ON remediation_queue(user_id) WHERE status = 'pending';

-- Config table (admin-editable)
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL,
    updated_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- LLM call telemetry for budget monitoring
CREATE TABLE IF NOT EXISTS llm_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    model TEXT NOT NULL,
    purpose TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ok'
);
