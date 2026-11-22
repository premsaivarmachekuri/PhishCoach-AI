# PhishCoach AI - Architecture

**One line:** an AI red-team that writes safe phishing simulations, plays the attacker live, coaches the employee the moment they slip, and shows risk dropping in real time.

## Stack
React + Vite + Tailwind (UI) · FastAPI (API, SSE) · LangGraph agents · Groq LLMs · DuckDB (live data). No login screens: a **role switcher** in the header sets the active persona.

```
 React role switcher ──X-Role / X-User-Id──▶ FastAPI ──▶ role guards (require_admin / require_hr_or_admin / own-data)
        ▲  SSE "change" events                  │
        │                                       ├─ Campaign Agent   (LangGraph: generate → rule check → LLM guard → retry/fail)
        │                                       ├─ Attacker Agent   (streamed chat simulation + per-turn judge)
        │                                       ├─ Coach Agent      (streamed, personalised feedback from the user's real event)
        │                                       ├─ Risk Engine      (config-driven scoring, no LLM)
        │                                       └─ LLM Gateway ──▶ Groq model A → fallback B → fallback C
        └──────────── DuckDB (users, campaigns, events, risk) ◀── HR adapter / Sim-platform adapter (webhooks)
```

## Roles and permissions (enforced server-side on every request)
| Role | Sees | Blocked |
|---|---|---|
| Security Admin | campaigns, deploy, risk dashboard, remediation, pilot metrics, config | - |
| HR Viewer | anonymised department aggregates only | campaigns, individuals (403) |
| Employee | own inbox, live coaching chat, own progress | admin + HR data (403) |

The switcher is a UX shortcut, not UI-only hiding: the API resolves the persona to a **real enrolled user row** and returns 403 outside the role's scope. Switching role remounts the view, so access changes instantly.

## Agents
1. **Campaign Agent** (`agents/campaign_graph.py`) - theme + department + difficulty → email JSON. Nodes: `generate → check → llm_guard → (retry | fail)`. Deterministic `check` rejects real brands, non-reserved sender domains and malformed JSON; `llm_guard` is a second-model safety review. Human admin approves before deploy.
2. **Attacker Agent** (`agents/chat_graph.py`) - streams a conversational phishing attempt; a judge scores each turn (detected / fell for it / turn cap). Output is guardrail-filtered token by token.
3. **Coach Agent** (`agents/coach_graph.py`) - turns the employee's actual action (clicked / submitted / reported) plus the planted red flags into short, personalised feedback.
4. **Risk Engine** (`services/risk_engine.py`) - pure code, thresholds in `app_config`; drives remediation queue.

## Unbreakability
- **LLM-only fallback chain** (`llm_gateway.py`): bounded retry with backoff + Retry-After → next model in `MODEL_FALLBACKS` (default `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`). Streaming fails over only before the first token. If every model fails: **coaching** degrades to a rules coach (`agents/coach_graph.rules_coaching`) assembled from the employee's real event, the email's planted flags and the playbook rows in the DB, tagged `fallback` (amber badge, "AI offline"); campaign generation and attacker chat return a clean `503 AI service unavailable` (no fabricated email content).
- Strict schema validation + brand/domain guardrails on all generated content; reserved `.invalid`-style sender domains only.
- Rate limits per user, per-model budget tracking, telemetry of every LLM call.
- Typed error states in the UI (loading / error / empty); SSE client auto-reconnects with backoff.
- Privacy: anonymised ids (`emp_xxxx`) everywhere in UI; HR sees aggregates only.
- No mock data: every screen reads live from the DB; integrations go through adapters (`HRAdapter`, `SimulationPlatformAdapter`).

## Real-time
Writes publish a topic to `services/realtime.py`; `/realtime/stream` (SSE) pushes "something changed" and the UI refetches. Dashboards update during the demo without refresh.

## Run
```
uvicorn mock_systems.mock_hr.app:app --port 8001
uvicorn mock_systems.mock_sim.app:app --port 8002
uvicorn app.main:app --app-dir backend --port 8000
cd frontend && npm run dev
```
Set `GROQ_API_KEY` in `.env`. Tests: `pytest tests/unit tests/integration tests/safety`.

## Failure modes and system response
| Failure | Response |
|---|---|
| Primary LLM rate-limited / 5xx / empty | retry with backoff, then next model in chain; header badge turns amber (FALLBACK) |
| All LLMs down | Coach: rules coach from real event + playbook, badge "rules coach (AI offline)". Campaign/chat: HTTP 503 + UI retry; no fabricated content |
| LLM emits unsafe/malformed email | deterministic check + guard model reject, bounded regeneration, then explicit fail |
| Employee requests admin/HR data | 403 from server-side guard |
| HR/sim integration down | adapter error surfaced as typed error state; DB data untouched |
| SSE drops | client reconnects with exponential backoff |

## Notes
- **Control arm** feedback is intentionally standardised text stored in `app_config` (experiment design), not an LLM fallback.
- **Demo-only:** `/demo/personas` and the `X-Role` header are unauthenticated by request (no login screens). In production, replace `get_current_user` with SSO/JWT; every endpoint already depends on that single function.
