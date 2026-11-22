-- 002_rls_and_views.sql
-- Row Level Security policies and aggregate views

-- Helper functions to resolve current auth user's app_role and internal user_id
CREATE OR REPLACE FUNCTION current_app_user_id() RETURNS UUID AS $$
    SELECT id FROM users WHERE auth_user_id = auth.uid() LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

CREATE OR REPLACE FUNCTION current_app_role() RETURNS TEXT AS $$
    SELECT app_role FROM users WHERE auth_user_id = auth.uid() LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulations ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE coaching_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE risk_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE remediation_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_calls ENABLE ROW LEVEL SECURITY;

-- Users: employees see own row; security_admin sees all
CREATE POLICY users_self_select ON users
    FOR SELECT USING (auth_user_id = auth.uid() OR current_app_role() = 'security_admin');

-- Simulations: employees see own simulations; security_admin sees all
CREATE POLICY simulations_select ON simulations
    FOR SELECT USING (user_id = current_app_user_id() OR current_app_role() = 'security_admin');

-- Events: employees read/insert own events; security_admin reads all
CREATE POLICY events_select ON events
    FOR SELECT USING (user_id = current_app_user_id() OR current_app_role() = 'security_admin');

CREATE POLICY events_insert_own ON events
    FOR INSERT WITH CHECK (user_id = current_app_user_id());

-- Coaching sessions: employees read/write own; security_admin reads all
CREATE POLICY coaching_select ON coaching_sessions
    FOR SELECT USING (user_id = current_app_user_id() OR current_app_role() = 'security_admin');

CREATE POLICY coaching_insert_own ON coaching_sessions
    FOR INSERT WITH CHECK (user_id = current_app_user_id());

CREATE POLICY coaching_update_own ON coaching_sessions
    FOR UPDATE USING (user_id = current_app_user_id());

-- Risk scores: employees read own; security_admin reads all
CREATE POLICY risk_scores_select ON risk_scores
    FOR SELECT USING (user_id = current_app_user_id() OR current_app_role() = 'security_admin');

-- Admin-only tables
CREATE POLICY campaigns_admin_all ON campaigns
    FOR ALL USING (current_app_role() = 'security_admin');

CREATE POLICY templates_admin_all ON templates
    FOR ALL USING (current_app_role() = 'security_admin');

CREATE POLICY remediation_admin_all ON remediation_queue
    FOR ALL USING (current_app_role() = 'security_admin');

CREATE POLICY app_config_admin_all ON app_config
    FOR ALL USING (current_app_role() = 'security_admin');

CREATE POLICY audit_log_admin_select ON audit_log
    FOR SELECT USING (current_app_role() = 'security_admin');

CREATE POLICY llm_calls_admin_select ON llm_calls
    FOR SELECT USING (current_app_role() = 'security_admin');

-- HR aggregate view enforcing minimum cohort size from app_config
CREATE OR REPLACE VIEW v_hr_department_aggregates AS
WITH cfg AS (
    SELECT COALESCE((value_json->>'min_cohort_size')::int, 5) AS min_cohort
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
        COALESCE(AVG(r.score), 0)::NUMERIC(5,2) AS avg_risk_score
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

-- Admin live metrics view
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
    COALESCE(AVG(r.score), 0)::NUMERIC(5,2) AS avg_risk_score
FROM users u
LEFT JOIN simulations s ON s.user_id = u.id
LEFT JOIN events e ON e.simulation_id = s.id
LEFT JOIN risk_scores r ON r.user_id = u.id
GROUP BY u.department, u.role_name, u.is_synthetic;

-- Enable Supabase Realtime for live dashboard tables (ignore if publication does not exist in local PG)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE events;
        ALTER PUBLICATION supabase_realtime ADD TABLE risk_scores;
        ALTER PUBLICATION supabase_realtime ADD TABLE remediation_queue;
    END IF;
END $$;
