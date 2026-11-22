-- 001_duckdb_schema.sql
-- Core schema, views, and app_config defaults for DuckDB

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR PRIMARY KEY,
    anon_id VARCHAR UNIQUE NOT NULL,
    role_name VARCHAR NOT NULL,
    department VARCHAR NOT NULL,
    seniority VARCHAR NOT NULL DEFAULT 'mid',
    arm VARCHAR NOT NULL CHECK (arm IN ('control', 'treatment')),
    app_role VARCHAR NOT NULL DEFAULT 'employee' CHECK (app_role IN ('employee', 'security_admin', 'hr_viewer')),
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    auth_user_id VARCHAR UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_accounts (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS red_flags (
    id VARCHAR PRIMARY KEY,
    code VARCHAR UNIQUE NOT NULL,
    description VARCHAR NOT NULL,
    difficulty_tier INTEGER NOT NULL CHECK (difficulty_tier BETWEEN 1 AND 3)
);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    body VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaigns (
    id VARCHAR PRIMARY KEY,
    created_by VARCHAR,
    brief_json JSON NOT NULL,
    target_filter JSON NOT NULL,
    wave_no INTEGER NOT NULL DEFAULT 1,
    status VARCHAR NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'live', 'closed')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS templates (
    id VARCHAR PRIMARY KEY,
    campaign_id VARCHAR NOT NULL,
    email_json JSON NOT NULL,
    planted_flags JSON NOT NULL,
    difficulty INTEGER NOT NULL DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 3),
    source VARCHAR NOT NULL DEFAULT 'llm' CHECK (source IN ('llm', 'fallback', 'admin_edit')),
    status VARCHAR NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS simulations (
    id VARCHAR PRIMARY KEY,
    campaign_id VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,
    template_id VARCHAR NOT NULL,
    delivered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (campaign_id, user_id)
);

CREATE TABLE IF NOT EXISTS events (
    id VARCHAR PRIMARY KEY,
    simulation_id VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,
    type VARCHAR NOT NULL CHECK (type IN ('opened', 'clicked', 'replied', 'submitted', 'reported', 'ignored')),
    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (simulation_id, type)
);

CREATE TABLE IF NOT EXISTS coaching_sessions (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    simulation_id VARCHAR,
    kind VARCHAR NOT NULL CHECK (kind IN ('feedback', 'chat')),
    turns INTEGER NOT NULL DEFAULT 0,
    outcome VARCHAR,
    messages_json JSON NOT NULL DEFAULT '[]',
    source VARCHAR NOT NULL DEFAULT 'llm' CHECK (source IN ('llm', 'fallback', 'static_control')),
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_scores (
    user_id VARCHAR PRIMARY KEY,
    score DOUBLE NOT NULL DEFAULT 0,
    band VARCHAR NOT NULL DEFAULT 'Low' CHECK (band IN ('Low', 'Medium', 'High')),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS remediation_queue (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    reason VARCHAR NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'launched', 'dismissed')),
    campaign_id VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_config (
    key VARCHAR PRIMARY KEY,
    value_json JSON NOT NULL,
    updated_by VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id VARCHAR PRIMARY KEY,
    actor VARCHAR NOT NULL,
    action VARCHAR NOT NULL,
    entity VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    meta JSON NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id VARCHAR PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model VARCHAR NOT NULL,
    purpose VARCHAR NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    status VARCHAR NOT NULL DEFAULT 'ok'
);

CREATE OR REPLACE VIEW v_hr_department_aggregates AS
WITH cfg AS (
    SELECT COALESCE(CAST(json_extract_string(value_json, '$.min_cohort_size') AS INTEGER), 5) AS min_cohort
    FROM app_config WHERE key = 'min_cohort_size'
    UNION ALL SELECT 5 LIMIT 1
),
dept_stats AS (
    SELECT
        u.department,
        u.is_synthetic,
        COUNT(DISTINCT u.id) AS user_count,
        COUNT(DISTINCT s.id) AS delivered_count,
        COUNT(DISTINCT CASE WHEN e.type = 'clicked' THEN e.simulation_id END) AS clicked_count,
        COUNT(DISTINCT CASE WHEN e.type = 'submitted' THEN e.simulation_id END) AS submitted_count,
        COUNT(DISTINCT CASE WHEN e.type = 'reported' THEN e.simulation_id END) AS reported_count,
        COALESCE(AVG(r.score), 0) AS avg_risk_score
    FROM users u
    LEFT JOIN simulations s ON s.user_id = u.id
    LEFT JOIN events e ON e.simulation_id = s.id
    LEFT JOIN risk_scores r ON r.user_id = u.id
    GROUP BY u.department, u.is_synthetic
)
SELECT
    d.department,
    d.is_synthetic,
    d.user_count,
    d.delivered_count,
    d.clicked_count,
    d.submitted_count,
    d.reported_count,
    d.avg_risk_score
FROM dept_stats d, cfg
WHERE d.user_count >= cfg.min_cohort;

CREATE OR REPLACE VIEW v_admin_department_metrics AS
SELECT
    u.department,
    u.role_name,
    u.is_synthetic,
    COUNT(DISTINCT u.id) AS user_count,
    COUNT(DISTINCT s.id) AS delivered_count,
    COUNT(DISTINCT CASE WHEN e.type = 'opened' THEN e.simulation_id END) AS opened_count,
    COUNT(DISTINCT CASE WHEN e.type = 'clicked' THEN e.simulation_id END) AS clicked_count,
    COUNT(DISTINCT CASE WHEN e.type = 'submitted' THEN e.simulation_id END) AS submitted_count,
    COUNT(DISTINCT CASE WHEN e.type = 'reported' THEN e.simulation_id END) AS reported_count,
    COALESCE(AVG(r.score), 0) AS avg_risk_score
FROM users u
LEFT JOIN simulations s ON s.user_id = u.id
LEFT JOIN events e ON e.simulation_id = s.id
LEFT JOIN risk_scores r ON r.user_id = u.id
GROUP BY u.department, u.role_name, u.is_synthetic;

INSERT INTO app_config (key, value_json, updated_by) VALUES
('risk_weights', '{"opened": 2.0, "clicked": 15.0, "replied": 20.0, "submitted": 30.0, "ignored": 5.0, "reported": -15.0}', 'system'),
('decay_half_life_days', '{"days": 30.0}', 'system'),
('role_multipliers', '{"finance": 1.3, "executive": 1.4, "hr": 1.2, "it": 1.1, "engineering": 1.0, "sales": 1.15, "operations": 1.05, "default": 1.0}', 'system'),
('band_thresholds', '{"medium": 35.0, "high": 65.0}', 'system'),
('difficulty_map', '{"Low": 1, "Medium": 2, "High": 3}', 'system'),
('chat_turn_cap', '{"max_turns": 6}', 'system'),
('min_cohort_size', '{"min_cohort_size": 5}', 'system'),
('rate_limits', '{"events_per_min": 60, "chat_per_min": 20, "coach_per_min": 20}', 'system'),
('llm_token_budget', '{"coach_max_input_tokens": 1200, "coach_max_output_tokens": 350, "chat_max_output_tokens": 250, "generate_max_output_tokens": 800}', 'system'),
('control_static_feedback', '{"reported": "Thank you for reporting this simulated phishing email. Always verify unexpected requests through a trusted channel.", "clicked": "This was a simulated phishing exercise. Before clicking links, inspect the sender address and hover over URLs to verify the destination.", "submitted": "This was a simulated phishing exercise. Never enter credentials or sensitive data on unverified pages. Report suspicious messages to security.", "ignored": "This was a simulated phishing exercise. When you spot a suspicious email, use the Report Phishing button so the security team can investigate."}', 'system')
ON CONFLICT (key) DO NOTHING;
