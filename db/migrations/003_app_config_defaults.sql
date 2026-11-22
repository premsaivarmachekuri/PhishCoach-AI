-- 003_app_config_defaults.sql
-- Default configuration values (config is data, editable by admin)

INSERT INTO app_config (key, value_json, updated_by) VALUES
('risk_weights', '{"opened": 2.0, "clicked": 15.0, "replied": 20.0, "submitted": 30.0, "ignored": 5.0, "reported": -15.0}'::jsonb, 'system'),
('decay_half_life_days', '{"days": 30.0}'::jsonb, 'system'),
('role_multipliers', '{"finance": 1.3, "executive": 1.4, "hr": 1.2, "it": 1.1, "engineering": 1.0, "sales": 1.15, "operations": 1.05, "default": 1.0}'::jsonb, 'system'),
('band_thresholds', '{"medium": 35.0, "high": 65.0}'::jsonb, 'system'),
('difficulty_map', '{"Low": 1, "Medium": 2, "High": 3}'::jsonb, 'system'),
('chat_turn_cap', '{"max_turns": 6}'::jsonb, 'system'),
('min_cohort_size', '{"min_cohort_size": 5}'::jsonb, 'system'),
('rate_limits', '{"events_per_min": 60, "chat_per_min": 20, "coach_per_min": 20}'::jsonb, 'system'),
('llm_token_budget', '{"coach_max_input_tokens": 1200, "coach_max_output_tokens": 350, "chat_max_output_tokens": 250, "generate_max_output_tokens": 800}'::jsonb, 'system'),
('control_static_feedback', '{"reported": "Thank you for reporting this simulated phishing email. Always verify unexpected requests through a trusted channel.", "clicked": "This was a simulated phishing exercise. Before clicking links, inspect the sender address and hover over URLs to verify the destination.", "submitted": "This was a simulated phishing exercise. Never enter credentials or sensitive data on unverified pages. Report suspicious messages to security.", "ignored": "This was a simulated phishing exercise. When you spot a suspicious email, use the Report Phishing button so the security team can investigate."}'::jsonb, 'system')
ON CONFLICT (key) DO NOTHING;
