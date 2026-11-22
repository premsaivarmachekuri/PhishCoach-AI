# Project rules: PhishCoach AI

- Source of truth is docs/SPEC.md. Implement one phase at a time and stop for review.
- NEVER hardcode metrics, scores, users, emails, coaching text, chart values or sample percentages in /frontend/src or /backend/app. Read from the DB, an API or a live LLM call.
- Seed data only through: the mock HR service + HR adapter, the KB ingestion tool, and the public API. No direct SQL inserts from app code.
- Config (model names, risk weights, thresholds, caps) lives in env vars or the app_config table.
- Every UI screen needs loading, empty and error states. Fallback content must be badged and stored with source='fallback'.
- Generated phishing content may use only reserved domains (.invalid, .test, example.com), no real brands, no real URLs, no credential capture.
- Do not train or fine-tune any model.
- Never commit secrets. The Supabase service-role key and Groq key are backend-only.
- Mocks are allowed only under /tests. Do not mock the LLM in live-behavior tests or the demo.
- At the end of each phase: run all tests for that phase, run the hardcode audit (grep), and produce a walkthrough artifact with screenshots for UI work.
- Do not add paid services or dependencies that need more than ~512 MB RAM at runtime.
