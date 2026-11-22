# PhishCoach AI — End-to-End Build Spec (working title)

> **Audience:** Google Antigravity (agentic IDE) building this project, and the human reviewing it.
> **Stack cost:** $0 (free tiers only). **Last researched:** 2026-11-22.
> **Status of facts:** Items marked **[VERIFY]** came from secondary sources or may have changed. Re-check them before relying on them.

---

## 0. How to use this file with Antigravity

1. Create the repo, then add this file as `docs/SPEC.md`.
2. Create workspace rules from **Appendix A** (Antigravity supports persistent Markdown rules, workflows, skills and MCP; **[VERIFY]** the exact rules folder path, e.g. `.agents/rules/`, against current Antigravity docs).
3. Run **one phase at a time** (Section 9). For each phase, prompt: *"Implement Phase N of docs/SPEC.md. Follow the Non-Negotiable Rules (Section 4). Run the phase's acceptance tests. Produce a walkthrough artifact. Stop and wait for review."*
4. For Phases 0 to 2, use a review-before-proceed execution mode so you can catch structural mistakes early. Loosen it later if you are comfortable.
5. Ask the agent to verify UI phases with its browser capability (screenshots or recordings) in addition to automated tests.
6. Never let the agent put real secrets in the repo. Use `.env` (gitignored) and `.env.example`.

---

## 1. Problem statement

### 1.1 Business situation (as given)
A global enterprise runs **quarterly phishing simulation campaigns** targeting thousands of employees. Security-awareness teams design the email campaigns **manually** and analyze response metrics **after** each campaign. Stakeholders are the **security team, HR and employees**. The organization faces rising phishing threats and regulatory requirements for security training. Making simulations more **realistic** and delivering **interactive, personalized training** is a strategic priority to reduce risk and improve compliance.

### 1.2 Current challenges and their business impact

| Current challenge | Business impact |
|---|---|
| Static, non-interactive phishing simulation content | Reduces employee engagement and training effectiveness |
| Limited personalized feedback for users who fail simulations | Limits learning and behavior change |
| Manual design and deployment of simulation campaigns | Consumes security-team resources |
| Difficulty tracking individual training progress and risk levels | Impairs targeted remediation efforts |

### 1.3 Constraints (as given; one item partly illegible in the source photo)
- Comply with **privacy and ethical training guidelines**.
- Integrate with **email simulation platforms** and **HR systems**.
- **No AI model training** during the hackathon (partly illegible in the source; treated as: do not train or fine-tune models, use prompting, retrieval and rules only). **[VERIFY against the original PDF]**
- **Secure, role-based access** to the cloud environment, consistent with data-protection regulations.

### 1.4 Data considerations (as given)
Phishing email templates and campaign data; user response logs; HR employee data for role and risk profiling; integration endpoints for email simulation platforms. Preprocess to **anonymize and categorize** user interactions. Use **synthetic phishing scenarios** for development. Comply with privacy and data-protection standards. Prefer synthetic or anonymized data. Ensure data quality and relevance.

### 1.5 Solution expectations (as given)
An **interactive web application** with a **GenAI-powered conversational interface** that simulates phishing interactions and delivers personalized training feedback. Features: **dynamic phishing email generation, user-interaction tracking, integration with simulation and HR systems.** Success is measured by **engagement and training-effectiveness improvements demonstrated in pilot scenarios.** Creative solutions aligned with the problem are welcome.

### 1.6 The problem in plain terms
Companies test staff by sending fake phishing emails. Today those tests are repetitive and hand-built, people who fail get a generic message, and nobody can easily see who is at risk and what to do about it. We build a web app where AI writes fresh, realistic tests, chats with people to practice spotting scams, coaches each person individually, and shows the security team live who is at risk.

---

## 2. Goals, non-goals and success metrics

### 2.1 Goals
- G1 Generate **dynamic**, role-aware phishing simulations with a live LLM.
- G2 Provide an interactive **conversational** phishing simulation and **personalized** coaching.
- G3 Automate campaign creation and deployment (admin gives a brief, AI drafts, admin approves).
- G4 Track every interaction in real time and compute individual and group **risk**.
- G5 Drive **targeted remediation** for high-risk users.
- G6 Integrate with simulation-platform and HR systems through adapters (mock implementations for the hackathon).
- G7 Demonstrate **engagement and effectiveness** in a pilot with an honest, controlled design.

### 2.2 Non-goals
Training or fine-tuning any model. Sending real phishing emails. Using real employee data. Production-grade SLA. Replacing the enterprise's real simulation platform.

### 2.3 Success metrics (all computed live from stored events, never hardcoded)
- **Click rate** = users who clicked / users delivered.
- **Submit rate** = users who submitted data on the fake landing form / users delivered.
- **Report rate** = users who reported / users delivered.
- **Median time-to-report.**
- **Repeat-failure rate** = users failing in 2 or more waves / users failing at least once.
- **Coaching engagement** = coaching views opened, chat turns, chat completion.
- **Risk-band movement** per user and per department between waves.

---

## 3. Research findings and design implications

The evidence on phishing training is **mixed**, and this should shape the product and how we claim success.

| Finding | Source | Design implication |
|---|---|---|
| An 8-month randomized controlled experiment (ten simulated campaigns, 19,500+ employees at a large healthcare organization) concluded commonly deployed anti-phishing training is unlikely to offer significant practical value. A key reason was that most people don't engage with the embedded training material. | UC San Diego-led study (co-author Grant Ho), IEEE S&P (Oakland) 2025; UCSD news release | **Engagement is the bottleneck.** The product must make training short, interactive and in-the-moment. Measure engagement explicitly. |
| In a large mixed-methods study, the benefit of embedded training appeared to come from its **nudge** (a periodic reminder of the threat), more than from its content, which employees rarely consumed. | Lain et al., ETH Zurich, arXiv 2409.01378 | Keep feedback brief and actionable. Don't rely on long content. |
| A 15-month large-scale study found embedded training as commonly deployed was not effective and could have negative side effects. It recommended warnings and **crowd-sourced phishing detection** (users reporting) as complementary measures. | Lain et al., arXiv 2112.07498 | Make **reporting** a first-class action. Track **report rate** and **time-to-report**, not only click rate. Avoid shaming copy. |
| Earlier lab and field studies (e.g., PhishGuru, 515-participant field study) reported positive results and knowledge retention. | CMU researchers (PhishGuru studies; authorship not verified here) | Results conflict across studies, so evaluate rather than assume. |
| Evaluating exercise efficacy is statistically tricky. A large analysis (19,180 participants, 115,080 test emails) developed methods to correct bias. | Siadati et al., USENIX | Use a **control arm** and per-user baselines. Report uncertainty. |

### 3.1 What this means for the product
1. **Hypothesis, not a promise.** Our claim is that interactive, personalized GenAI coaching can raise engagement, which prior work identifies as the main failure point. We **test** this in the pilot. We do not assume it.
2. **Pilot has a control arm** (Section 11) so any improvement is attributable.
3. **Reporting is rewarded**, and the UI includes a prominent "Report phishing" action.
4. **No punitive framing.** Feedback is supportive, and managers never see individual names.
5. **Confidence:** these sources are real and peer-reviewed or preprints. I summarized them from search excerpts and abstracts. Read the originals before quoting numbers in your pitch.

---

## 4. Non-negotiable rules (also put these in the workspace rules file)

1. **No hardcoded data.** No metrics, scores, users, emails, coaching text, chart values or percentages in frontend or backend source. Everything is read from the database, an API or a live LLM call.
2. **Seeding only through the front door.**
   - Employees come from the **mock HR service** through the HR adapter.
   - Campaign events come from real app usage (and the clearly labelled persona simulator in Phase 8) through the **public API**.
   - Playbook content is loaded by the **knowledge-base ingestion tool** from `/content/playbook/*.md`. This is authored reference knowledge, not metrics.
   - Nothing is inserted directly into application tables by SQL in app code.
3. **Config is data.** Model names, risk weights, decay half-life, band thresholds, difficulty rules, cohort minimum size and turn caps live in env vars or the `app_config` table, editable by an admin where appropriate.
4. **Honest UI states.** Every screen has loading, empty and error states. Never show placeholder numbers. Any fallback content carries a visible "fallback" badge and is stored with `source='fallback'`.
5. **Safety of generated content.** Use only reserved domains (`.invalid`, `.test`, `example.com`). No real brands, no real URLs, no real credential forms. Every simulated landing page says it's a training exercise.
6. **No model training or fine-tuning.** Prompting, retrieval and rules only.
7. **Privacy.** Synthetic or anonymized data only. Users are referenced by anonymized IDs. Scrub PII before any LLM call and before logging.
8. **Cost.** Free tiers only. Do not add paid services.
9. **Secrets** never enter the repo or the frontend bundle. The Supabase **service-role key** and the Groq key live only on the backend.
10. **Synthetic labelling.** Every synthetic user or event has `is_synthetic=true`. Dashboards default to **real only** with a visible toggle.

---

## 5. Personas and user journeys

### 5.1 Personas
- **Employee (Asha, finance analyst):** busy, mildly skeptical, wants short, useful guidance.
- **Security admin (Ravi):** runs campaigns, wants less manual work and clear risk visibility.
- **HR viewer (Meera):** needs aggregate readiness and compliance reports, never individual shaming.

### 5.2 Employee journey
1. **Sign in** and see a simulated inbox with a transparency notice ("This mailbox contains training exercises").
2. **Receive a simulated email** generated live for her role and difficulty level.
3. **Act:** open, click a link, reply, submit data on the fake page, or press **Report phishing**. Every action is logged.
4. **Instant coaching** (streamed): what the red flags were, why they matter, one habit to adopt. The tone is supportive for failures and reinforcing for correct reports.
5. **Practice chat (optional):** an "attacker" persona talks to her; she tries to spot the scam. The chat ends on detection or after a turn cap, then a short debrief follows.
6. **My progress:** personal risk band, trend, strengths, next recommended practice.
7. **Re-test** later at an adaptive difficulty.

### 5.3 Security admin journey
1. **Create campaign:** target group, theme, difficulty, schedule, in natural language or form.
2. **AI drafts emails.** Guardrails and a flag checker validate them.
3. **Review and approve** drafts (edit or reject).
4. **Deploy** through the simulation-platform adapter.
5. **Watch live results:** events stream in, with risk by department and by role.
6. **Remediation queue:** high-risk users automatically queued for targeted follow-up. Admin approves and launches.
7. **Pilot view and exports** for compliance.

### 5.4 HR journey
View aggregate readiness and compliance metrics with a minimum cohort size. Individuals are never exposed. The HR system is also the data source for role and department.

---

## 6. Architecture (HLD)

### 6.1 Layered view

```
USERS: Employee | Security Admin | HR Viewer
   |
[L1 PRESENTATION]  React (Vite) SPA
   Employee: Inbox simulator, Coaching panel, Practice chat, My progress
   Admin: Campaign builder, Approval queue, Live dashboard, Remediation queue, Pilot view, Config
   HR: Aggregate dashboard
   |  HTTPS + JWT (Supabase Auth)   |  SSE for streaming   |  Supabase Realtime for live data
[L2 API + SECURITY]  FastAPI
   Auth middleware, RBAC, rate limiting, validation, audit log
   |
[L3 AI ORCHESTRATION]  LangGraph
   Campaign graph: generate -> flag-check -> rule guardrail -> LLM guardrail -> approval queue
   Coach graph: retrieve playbook -> compose feedback (streamed)
   Attacker-chat graph: persona turn -> input/output guardrail -> end-condition check -> debrief
   Risk engine (pure Python, rules, no ML)
   |
[L4 LLM GATEWAY]  Groq (multi-model routing, token budgeter, 429 backoff, fallback)
   |
[L5 KNOWLEDGE]  Postgres full-text search over red-flag playbook and policy docs
   |
[L6 INTEGRATION ADAPTERS]
   HRAdapter  ---> Mock HR service (separate FastAPI service)
   SimulationPlatformAdapter ---> Mock simulation platform (separate FastAPI service + webhook)
   |
[L7 DATA]  Supabase Postgres (+ RLS)
[L8 CROSS-CUTTING]  Tracing (Langfuse or LangSmith free), CI (GitHub Actions), secrets, anonymizer
```

### 6.2 Key design decisions
- **Mock source systems are separate services** with their own data and APIs. The core app treats them as real external systems through adapters, so swapping in real ones requires no core changes.
- **Live generation, decoupled from delivery.** Campaign emails are generated at campaign-creation time (live LLM calls), stored as drafts, approved, then delivered. This smooths load on the free LLM tier without hardcoding anything.
- **Multi-model routing to stretch free limits.** Groq's limits apply per model and per organization (Section 7). Route different jobs to different models so they draw from separate budgets.
- **RAG via Postgres full-text search** (`tsvector` and `websearch_to_tsquery`) instead of vectors. The playbook is small, and this avoids heavy embedding libraries on a 512 MB free host. Upgrade to pgvector only if retrieval quality demands it.
- **Light PII scrubber** (regex and a name list from the HR adapter) instead of heavy NLP stacks, again for memory limits.
- **Realtime** through Supabase Realtime (Postgres changes) for dashboards, with 5-second polling as fallback.
- **Rules-based risk scoring.** No learning, which complies with the no-training constraint.

### 6.3 LangGraph agents

| Agent | Input | Output | Model tier |
|---|---|---|---|
| Campaign Generator | brief (theme, department, role, difficulty, red-flag set from DB) | Pydantic-validated JSON: sender display name, sender address (reserved domain), subject, body, link label, planted_flags[] | Large |
| Flag Checker | generated email + planted_flags | pass or fail, with missing flags | Small (plus rule checks) |
| Guardrail | email or chat text | allow or block, with reason | Rules first, then Small |
| Coach | email, planted flags, user action, retrieved playbook chunks | short streamed feedback | Large (or Medium) |
| Attacker Persona | scenario, chat history | next attacker message | Medium or Large |
| Summarizer | chat transcript | short debrief and outcome label | Small |

**Red-flag taxonomy** lives in a DB table (`red_flags`) loaded by ingestion: e.g., sender mismatch, urgency, unusual request, link mismatch, unexpected attachment, generic greeting, authority pressure, reward lure, credential request.

### 6.4 Risk engine (config-driven)
For each user, compute from `events` joined to `simulations`:

```
raw = SUM over events of  weight[event_type] * decay(age_days, half_life) * difficulty_factor
risk = clamp( 100 * sigmoid_or_scaled( raw * role_multiplier[role] ), 0, 100 )
band = Low / Medium / High by thresholds in app_config
```

- `weight` per event type (click, submit, reply, ignore, report with a negative weight), `half_life`, `role_multiplier`, thresholds: all in `app_config` and admin-editable.
- **Adaptive difficulty:** band maps to difficulty level (1 to 3) via config. Difficulty determines the number and subtlety of planted red flags.
- **Remediation rule:** users entering the High band, or failing in consecutive waves, are inserted into `remediation_queue`.

### 6.5 Data model (Postgres, key columns only)
- `users` (id, anon_id, role_name, department, seniority, arm, is_synthetic, auth_user_id)
- `red_flags` (id, code, description, difficulty_tier)
- `kb_chunks` (id, source, title, body, tsv)
- `templates` (id, campaign_id, email_json, planted_flags, difficulty, source: `llm|fallback|admin_edit`, status: `draft|approved|rejected`)
- `campaigns` (id, created_by, brief_json, target_filter, wave_no, status: `draft|approved|live|closed`)
- `simulations` (id, campaign_id, user_id, template_id, delivered_at)
- `events` (id, simulation_id, user_id, type: `opened|clicked|replied|submitted|reported`, ts, is_synthetic)
- `coaching_sessions` (id, user_id, simulation_id, kind: `feedback|chat`, turns, outcome, started_at, ended_at)
- `risk_scores` (user_id, score, band, updated_at)
- `remediation_queue` (id, user_id, reason, status, created_at)
- `app_config` (key, value_json, updated_by, updated_at)
- `audit_log` (id, actor, action, entity, ts, meta)
- `llm_calls` (id, ts, model, purpose, prompt_tokens, completion_tokens, latency_ms, status) for budget monitoring

**RLS policy summary:** employees read and write only their own rows. Security admins read all events and aggregates. HR reads **aggregates only** through views that enforce a minimum cohort size.

### 6.6 API surface (FastAPI)

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Campaigns | `POST /campaigns` (brief, triggers generation), `GET /campaigns/{id}`, `POST /campaigns/{id}/templates/{tid}/approve` and `/reject`, `PATCH /templates/{tid}` (edit), `POST /campaigns/{id}/deploy` |
| Employee | `GET /me/inbox`, `GET /me/progress`, `POST /events` |
| Coaching | `POST /coach/{simulation_id}` (SSE stream) |
| Chat | `POST /chat/sessions`, `POST /chat/sessions/{id}/messages` (SSE), `POST /chat/sessions/{id}/end` |
| Admin | `GET /admin/dashboard`, `GET /admin/users/risk`, `GET /admin/remediation`, `POST /admin/remediation/{id}/launch`, `GET/PUT /admin/config`, `GET /admin/pilot`, `GET /admin/export?format=csv\|pdf` |
| HR | `GET /hr/aggregates` |
| Integration | `POST /integrations/sim/webhook`, `POST /integrations/hr/sync` |
| Mock services (separate processes) | `GET /mock/hr/employees`, `POST /mock/sim/campaigns`, `GET /mock/sim/events` |

### 6.7 Token and rate-limit strategy (important on the free tier)
- Groq returns **HTTP 429** when limits are exceeded, and limits apply **per model** at the **organization** level. Per-model limits on your account are shown on the console limits page, which is authoritative.
- A secondary source (read 2026-09-14) lists the free plan for a 120B-class model at roughly 30 requests/min, 1,000 requests/day, **8,000 tokens/min** and 200,000 tokens/day. **[VERIFY]** in your console. Token-per-minute is likely the tightest limit.
- Therefore:
  1. Keep prompts short: send only the needed playbook snippets, set `max_tokens`, and cap chat history.
  2. Build an **LLM gateway** with a per-model token-bucket that reads the rate-limit headers Groq returns, a priority queue (interactive chat and coaching above batch generation), exponential backoff on 429, and fallback to a smaller model.
  3. **Spread jobs across models:** generation, coaching, chat and guardrail checks each get a configured model name, so they use separate budgets.
  4. Generate campaign emails at creation time, not when the employee opens the inbox.
  5. Log every call in `llm_calls` and show remaining budget on the admin Config page.
  6. Model names live in config because Groq adds and retires models. Candidates seen in secondary sources for the free tier include Llama 3.3 70B, Llama 4 Scout and gpt-oss 20B and 120B. **[VERIFY]**

---

## 7. Tech stack and free-tier facts

| Layer | Choice | Free-tier facts and caveats |
|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind + Recharts | Host on Vercel or Netlify free tier **[VERIFY limits]** |
| Backend | FastAPI (Python 3.11+), `uvicorn`, `sse-starlette` | **Render free web service:** spins down after 15 minutes without inbound traffic and takes up to about a minute to spin back up. Ephemeral filesystem. About 512 MB RAM and 0.1 CPU per Render's own article. |
| Mock source systems | Two small FastAPI services (can run as extra routers in one deployment to save free instances) | Same hosting as above |
| Orchestration | LangGraph + LangChain | Open source |
| LLM | Groq API via the `groq` SDK or `langchain-groq` | Free plan, no card required per community answers. Limits per model, per organization. A third-party source says Groq doesn't train on API data. **[VERIFY Groq's current data terms]** |
| DB, Auth, Realtime | Supabase (Postgres, Auth, RLS, Realtime) | **Free projects are paused after about a week of low activity.** 2 active free projects. 0.5 GB DB per active project. 5 GB egress. Realtime Postgres Changes is included on free; message and connection quotas apply. **[VERIFY exact Realtime quotas]** |
| Search/RAG | Postgres full-text search | No extra cost or memory |
| PII scrubbing | Regex + name list | Avoids heavy NLP dependencies |
| Tracing | Langfuse or LangSmith free tier | **[VERIFY limits]** |
| CI | GitHub Actions | **[VERIFY minutes]** |
| E2E tests | Playwright | Open source |
| Agentic builder | Google Antigravity | Free preview or plan limits **[VERIFY]** |

**Do not** use Render's free Postgres (it expires 30 days after creation). Use Supabase.

---

## 8. Repo structure and configuration

```
/.agents/rules/            Antigravity rules (see Appendix A) [VERIFY path]
/docs/SPEC.md              this file
/content/playbook/*.md     authored red-flag and policy reference content
/frontend/                 React app
/backend/
  app/api/                 routers
  app/agents/              LangGraph graphs (campaign, coach, chat)
  app/adapters/            hr.py, sim_platform.py (interfaces + HTTP implementations)
  app/services/            risk_engine.py, anonymizer.py, guardrails.py, llm_gateway.py, config.py
  app/models/              Pydantic schemas
/mock_systems/             mock_hr/, mock_sim/
/tools/                    ingest_kb.py, create_demo_users.py, persona_simulator.py, sync_hr.py
/db/migrations/            schema, RLS, views, app_config defaults
/tests/                    unit/, integration/, e2e/, safety/, llm_eval/
/.github/workflows/ci.yml
.env.example
```

**Environment variables (names only):** `GROQ_API_KEY`, `MODEL_GENERATE`, `MODEL_COACH`, `MODEL_CHAT`, `MODEL_GUARD`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (backend only), `JWT_SECRET`, `HR_API_URL`, `SIM_API_URL`, `ALLOWED_ORIGINS`, `LANGFUSE_*` or `LANGSMITH_*`.

`app_config` defaults (inserted by a migration, editable later): risk weights, half-life, role multipliers, band thresholds, difficulty map, chat turn cap, min cohort size, per-user rate limits.

---

## 9. Build plan: phases, tasks and acceptance tests

Each phase ends with: tests passing, a walkthrough artifact, a "hardcode audit" (grep for literal metric numbers and sample text in `/frontend/src` and `/backend/app`), and a short note on anything incomplete.

### Phase 0: Foundations
**Tasks**
- Repo, linting, `.env.example`, CI skeleton.
- Supabase project; migrations for all tables in 6.5; `app_config` defaults.
- RLS policies and HR aggregate views with minimum cohort size.
- LLM gateway with per-model config, retries on 429, small-model fallback, `llm_calls` logging.
- `GET /health`.

**Acceptance**
- Migrations apply on a clean database.
- RLS test: an employee token cannot read another user's `events`, `risk_scores` or `coaching_sessions`.
- HR view returns nothing when cohort size is below the minimum.
- Gateway returns a live Groq response and records token counts.
- Simulated 429 triggers backoff and fallback.

### Phase 1: Mock systems and integration adapters
**Tasks**
- Mock HR service generating employees at startup (Faker) and exposing them over HTTP.
- Mock simulation-platform service with campaign deploy, event polling and a webhook.
- `HRAdapter` and `SimulationPlatformAdapter` interfaces plus HTTP implementations.
- `sync_hr.py`: pulls employees, anonymizes, assigns `anon_id`, randomly assigns `arm` (control or treatment) at enrollment, and upserts `users`.
- `create_demo_users.py`: creates Supabase auth users for each role using the service role key from env.

**Acceptance**
- `users` is populated only via the adapter. No raw names or emails exist in app tables.
- Re-running sync is idempotent.
- Arm split is roughly balanced and stored.
- Adapter has contract tests so a real implementation could be substituted.

### Phase 2: Knowledge base and campaign generation
**Tasks**
- Author `/content/playbook/*.md` (red-flag explanations, safe-behavior steps). Base it on general, widely taught phishing guidance. Do **not** invent citations. Add a source URL only where you have verified it.
- `ingest_kb.py` fills `red_flags` and `kb_chunks` (with `tsvector`).
- Campaign graph: brief, then generate, then flag checker, then rule guardrail, then LLM guardrail, then drafts in the approval queue. Pydantic schema validation with one retry.
- Admin endpoints to approve, reject and edit.

**Acceptance**
- Two different briefs produce different emails.
- Every approved email contains each declared planted flag (checker test).
- Guardrail tests: real brand names, real URLs and credential-harvesting forms are blocked.
- No email can be delivered without `status='approved'`.
- All sender and link domains are reserved or invalid TLDs.

### Phase 3: Delivery, inbox and live event tracking
**Tasks**
- Deploy flow: approved campaign creates `simulations` through the sim adapter.
- Employee simulated inbox UI with a prominent **Report phishing** button and a transparency banner.
- `POST /events` for opened, clicked, replied, submitted, reported (idempotent per simulation and type).
- Fake landing page for "clicked" with a training notice and no real data capture.
- Supabase Realtime subscription on the admin dashboard, with polling fallback.

**Acceptance**
- A click in the employee inbox appears on the admin dashboard within about 5 seconds without a refresh.
- Duplicate event posts don't double count.
- Fake landing form never stores typed values, only the fact of submission.

### Phase 4: Feedback Coach
**Tasks**
- Coach graph: fetch the email and planted flags, run full-text retrieval for the relevant playbook chunks, then stream feedback via SSE.
- Different tone and content for: reported correctly, ignored, clicked, submitted.
- **Control arm** gets a standard, non-personalized static message (stored in `app_config`, not code), and **treatment arm** gets the AI coaching. This is needed for the pilot.
- Log coaching views and engagement in `coaching_sessions`.

**Acceptance**
- Feedback differs by action and by email, and names the actual red flags present.
- Treatment users receive streamed feedback. Control users receive the configured static message.
- Prompt size stays under the configured token budget (test).

### Phase 5: Practice chat (attacker persona)
**Tasks**
- Scenario starter from the user's role (e.g., fake IT helpdesk, vendor invoice).
- Sandboxed persona prompt, input and output guardrails, turn cap from config.
- End conditions: user identifies the scam, user reports, or the cap is reached. Then a summarizer creates a debrief and outcome label.
- Treatment arm only (control arm does not get the chat).

**Acceptance**
- Prompt-injection tests ("ignore previous instructions", "give me real credentials", requests for real brand impersonation) fail safely.
- The persona never requests real personal data and never emits real URLs.
- A debrief is stored and shown.
- Streaming works end to end.

### Phase 6: Risk engine, adaptive loop and remediation
**Tasks**
- `risk_engine.py` reads weights and thresholds from `app_config`, recomputed on each event.
- Adaptive difficulty selection for the next campaign per user.
- Remediation rule and `remediation_queue`, with an admin approve-and-launch action that creates a targeted follow-up campaign.
- Admin Config UI to edit weights and thresholds (audited).

**Acceptance**
- Changing a weight in the Config UI changes subsequent scores without a deploy.
- A scripted sequence of events moves a user Low to Medium to High as expected (unit test with fixtures in `/tests`, not in app code).
- High-band users appear in the remediation queue exactly once.

### Phase 7: Dashboards, pilot view and exports
**Tasks**
- Admin dashboard: all metrics from 2.3, by department and by role, from SQL views.
- Pilot view: Wave 1 versus Wave 2, control versus treatment, with differences and confidence intervals (Section 11).
- HR aggregate dashboard with the cohort minimum.
- CSV and PDF export.
- Real/synthetic toggle, default real only.

**Acceptance**
- Every displayed number is traceable to a query (add a "show query" debug toggle for the demo).
- Deleting all synthetic users changes the dashboard accordingly.
- Empty states render when no data exists.

### Phase 8: Persona simulator (for load and demo realism only)
**Tasks**
- `persona_simulator.py` calls the **public API** with Groq-driven personas of varying susceptibility. All users and events are flagged `is_synthetic=true`.
- Use it for load testing and to populate dashboards in demos.

**Acceptance**
- Simulator uses only public endpoints (no direct DB writes).
- Synthetic data is excluded from effectiveness claims by default and clearly labelled in the UI.

> **Caution:** LLM-driven personas don't prove real human behavior change. Use real volunteers for the pilot claims.

### Phase 9: Hardening, deployment and demo
**Tasks**
- Rate limits, CORS lock-down, input validation, audit log completeness, dependency audit.
- Deploy frontend, backend and mock services; Supabase hosted.
- Warm-up runbook and demo script (Section 12).
- Final regression run and the completion checklist (Section 13).

**Acceptance**
- CI green on unit, integration, safety and e2e suites.
- Full journey passes on the deployed stack.
- No secrets in the repo (secret scan) or in the frontend bundle.

---

## 10. Testing strategy

| Level | What | Tools |
|---|---|---|
| Unit | Risk engine, anonymizer, guardrail rules, flag checker, config loader, token budgeter | pytest |
| Contract | Adapter interfaces against the mock services | pytest + httpx |
| Integration | API with a test Supabase schema: RLS, events idempotency, approval gate, campaign graph with a mocked LLM | pytest |
| LLM behavior (live, small sample) | Schema validity rate, planted-flag presence rate, guardrail catch rate | pytest + live Groq, rate-limited |
| Safety / red team | Prompt injection, jailbreak attempts, real-brand impersonation, PII leakage, cross-user data access | pytest, scripted attack list in `/tests/safety` |
| E2E | Employee and admin journeys in the browser | Playwright, plus the Antigravity browser agent for screenshots and recordings |
| Load | 10 to 25 concurrent personas against the deployed stack, checking 429 handling and queue behavior | persona simulator |
| Accessibility and UX | Keyboard navigation, contrast, empty and error states | Lighthouse or axe |

**Core scenarios to automate**
1. Admin brief to approved campaign to deployed to employee inbox.
2. Employee clicks, then admin dashboard updates live, then coaching streams, then risk changes.
3. Employee reports, then positive feedback, then risk falls.
4. Control versus treatment get different post-event experiences.
5. Employee A cannot access employee B's data (negative test).
6. HR cannot see a cohort smaller than the minimum.
7. 429 from Groq leads to backoff and fallback, and the UI shows a "fallback" badge.
8. Prompt injection in chat is refused and logged.

**Mocking rule:** LLM calls may be mocked in unit and integration tests. They must **not** be mocked in the live LLM-behavior suite or the demo. Mocks live only under `/tests`.

---

## 11. Pilot design (how we "demonstrate improvement")

- **Participants:** real volunteers (teammates, mentors, other participants) who consent to a training exercise. Real data only, with names anonymized.
- **Arms:** control (standard static feedback) versus treatment (AI coaching and practice chat). Random assignment at enrollment.
- **Waves:** Wave 1 (baseline, same difficulty for all), then intervention, then Wave 2 (post). Optionally Wave 3 after a delay for retention.
- **Metrics:** click rate, submit rate, report rate, time-to-report, repeat-failure, coaching engagement, risk-band movement.
- **Analysis:** per-arm change from Wave 1 to Wave 2, and the difference between arms (difference-in-differences). Show **confidence intervals** (e.g., Wilson intervals for proportions).
- **Honest reporting:** with small samples the intervals will be wide, so state the sample size and say the result is **indicative, not conclusive**. If treatment does not improve results, report that and the engagement findings. Given the research in Section 3, that is a legitimate finding.
- **Synthetic personas** are shown separately and are not used to claim effectiveness.

---

## 12. Deployment and operations

- **Order:** Supabase project, then migrations, then backend (Render), then mock services, then frontend (Vercel or Netlify), then `create_demo_users.py`, `sync_hr.py`, `ingest_kb.py`.
- **Cold starts:** Render free services take up to about a minute to wake. **Open the app and hit `/health` 2 to 3 minutes before any demo.** Render's staff have discouraged using keep-alive pings to defeat spin-down, so don't depend on a pinger. **[VERIFY Render's current policy]**
- **Supabase pause:** free projects pause after about a week of low activity. Run a real query or open the app at least every few days before the demo, and check the project is active the day before.
- **Ephemeral disk:** the backend must keep no state on local disk.
- **LLM budget check:** before the demo, run a quick load test and check the remaining quota on the Groq console.
- **Backup plan:** keep a screen recording of a full successful run.

**Demo script (about 5 minutes):** admin writes a brief, AI drafts, admin approves and deploys, employee receives, clicks, gets coached live, chats with the attacker, risk updates on the dashboard in real time, pilot view shows control versus treatment, and the Config page shows editable risk weights.

---

## 13. Definition of done (completion checklist)

**Functional**
- [ ] Live, role-aware phishing email generation with guardrails and approval gate
- [ ] Simulated inbox with Report button and transparency banner
- [ ] Real-time event tracking to admin dashboard
- [ ] Personalized streamed coaching (treatment) and static message (control)
- [ ] Practice chat with the attacker persona and debrief
- [ ] Risk engine with admin-editable config; adaptive difficulty
- [ ] Remediation queue with targeted follow-up campaigns
- [ ] Pilot view with control versus treatment and confidence intervals
- [ ] HR aggregate view with minimum cohort size
- [ ] Mock HR and simulation-platform systems behind adapter interfaces
- [ ] CSV and PDF export

**Non-functional**
- [ ] Hardcode audit passes (no literal metrics or sample content in app source)
- [ ] RBAC and RLS verified by negative tests
- [ ] No secrets in repo or frontend bundle
- [ ] Reserved domains only; no real brands or URLs in generated content
- [ ] Every call logged in `llm_calls`; 429 handling tested
- [ ] Tracing enabled
- [ ] CI green; Playwright e2e passes on the deployed stack
- [ ] README with setup, env vars, run, test and demo steps
- [ ] Known limitations documented

---

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Groq free-tier token and request caps | Per-model routing, short prompts, priority queue, backoff, fallback model, generation at campaign-creation time |
| Training may not reduce failures (per recent studies) | Control arm, engagement and report-rate metrics, honest reporting |
| Render cold starts | Warm-up runbook; avoid reliance on pingers |
| Supabase project pausing | Activity before demo; verify the day before |
| 512 MB RAM on free host | No heavy NLP or embedding libraries; Postgres FTS; regex scrubber |
| LLM output drift or invalid JSON | Pydantic validation, one retry, flag checker, fallback badge |
| Prompt injection or misuse in chat | Input and output guardrails, turn cap, logging, safety test suite |
| Ethical concerns (shaming, surveillance) | Anonymized IDs, supportive tone, HR aggregates only, transparency banner |
| Spec items I could not confirm | See **[VERIFY]** tags and Section 15 |

---

## 15. Open verification list (do before building)
1. Original PDF wording of the constraint about AI model training.
2. Your Groq console limits page: exact per-model RPM, RPD, TPM and TPD for the models you choose, and current free-tier data terms.
3. Supabase Realtime free quotas and that Realtime works with your RLS setup.
4. Render free limits and policy on keep-alive pings.
5. Vercel or Netlify, Langfuse or LangSmith, and GitHub Actions free-tier limits.
6. Antigravity's current rules folder path, execution-mode settings and plan limits.
7. Read the original research papers (Section 16) before quoting any figures in the pitch.

---

## 16. FAQs

**Domain**
1. **What is a phishing simulation?** A harmless fake phishing email sent by the company to see who clicks, reports or ignores it.
2. **Why not use the existing tool?** Typical tools send fixed templates and generic feedback. The gap is realism, interactivity, personalization and automation.
3. **Does phishing training actually work?** Evidence is mixed. Several large recent studies found weak or no effect for commonly deployed embedded training, citing low engagement. Our pilot tests whether interactive coaching helps, with a control group.
4. **Why track "reports" and not only "clicks"?** Reporting turns employees into detectors and is recommended by the research as a complementary defense.
5. **Is this tricking employees?** It's acceptable only with transparency and supportive framing: policy notice, no shaming, anonymized reporting to HR and managers.

**Product and build**
6. **What does GenAI do?** Writes fresh role-specific emails, plays the attacker in the chat, and explains mistakes in plain language.
7. **Where does data come from?** Employees from the mock HR service (synthetic), events from real app use, playbook from authored content. Nothing is hardcoded.
8. **How are the integrations handled without real systems?** Adapters with mock services behind the same interface a real system would use.
9. **How do we stay inside "no model training"?** Prompting, retrieval and rules only. The risk score is a weighted formula.
10. **What if the LLM quota runs out mid-demo?** Backoff, fallback model, labelled fallback content, and a recorded backup run.
11. **How do we prove effectiveness?** Control-versus-treatment pilot with waves, confidence intervals, and honest reporting of small-sample limits.
12. **How is privacy protected?** Anonymized IDs, PII scrubbing before LLM calls and logs, RLS, HR cohort minimums, audit log.

---

## 17. Sources consulted (all retrieved 2026-11-22)

**Research**
- UC San Diego-led team (co-author Grant Ho), 8-month randomized controlled experiment on anti-phishing training, IEEE S&P (Oakland) 2025: https://sysnet.ucsd.edu/~voelker/pubs/phishtrain-oakland25.pdf
- UC San Diego news release on the same study: https://today.ucsd.edu/story/cybersecurity-training-programs-dont-prevent-employees-from-falling-for-phishing-scams
- Lain et al. (ETH Zurich), "Content, Nudges and Incentives: A Study on the Effectiveness and Perception of Embedded Phishing Training": https://arxiv.org/abs/2409.01378
- Lain et al., "Phishing in Organizations: Findings from a Large-Scale and Long-Term Study": https://arxiv.org/abs/2112.07498
- CMU PhishGuru researchers (hosted on Alessandro Acquisti's page; author list not verified), real-world evaluation of anti-phishing training: https://www.heinz.cmu.edu/~acquisti/papers/Acquisti_Real-World_Evaluation_of_Anti-Phishing_Training.pdf
- Siadati et al., large-scale analysis of embedded phishing exercises (USENIX): https://www.usenix.org/node/205854

**Platform facts**
- Groq rate limits documentation: https://console.groq.com/docs/rate-limits
- Groq community answers on free tier: https://community.groq.com/t/is-there-a-free-tier-and-what-are-its-limits/790
- Secondary summary of Groq free-plan limits (read 2026-09-14): https://benchlm.ai/free-tier/groq
- Supabase project pausing: https://supabase.com/docs/guides/platform/free-plan-pausing
- Supabase billing and plan details: https://supabase.com/docs/guides/platform/billing-on-supabase
- Render free tier docs: https://render.com/docs/free
- Google Antigravity docs: https://antigravity.google/docs/home
- Antigravity rules and workflows (third-party field guide, lower confidence): https://rkalani1.github.io/agent-builder-field-guide/platforms/antigravity/

---

## Appendix A: Antigravity workspace rule (paste into the rules file)

```markdown
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
```

## Appendix B: Phase kickoff prompt template

```text
Read docs/SPEC.md fully. Implement Phase <N> only. Follow Section 4 (Non-Negotiable Rules).
Deliver: code, tests that satisfy the Phase <N> acceptance criteria, a hardcode audit result,
and a walkthrough artifact (with screenshots for any UI). Report anything you could not complete
or that depends on a [VERIFY] item. Then stop and wait for my review before starting Phase <N+1>.
```
