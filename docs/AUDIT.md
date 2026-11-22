# Audit against the 4 evaluation criteria

| Criterion | Status | Evidence | Remaining gap |
|---|---|---|---|
| **Real-world usefulness** | Strong | Pilot "Impact" tab leads with treatment vs control click rate and difference-in-differences; AI campaign generation with human approval; per-user coaching; remediation queue; HR sees anonymised aggregates only | Pilot sample is small (N=40) so results are indicative only; no email-platform sending outside the mock sim adapter |
| **Agent design + architecture doc** | Strong | 3 agents (campaign graph, attacker chat + judge, coach) + deterministic risk engine; `docs/ARCHITECTURE.md` has diagram, roles, failure modes | Agent traces are not surfaced in the UI |
| **Unbreakability** | Good | LLM-only model fallback chain (tested); retry/backoff; guardrails on generated email; 503 instead of fake content; rate limits; SSE auto-reconnect; React error boundary + Retry on every load | No automated end-to-end UI test; fallback chain tested with mocks, not a live outage |
| **Demo + clarity (10 s)** | Good | Monochrome UI; role switcher; every role shows a one-line goal and 3-step journey; header shows Live status and active model/fallback | Admin "Live Risk" tab is dense; Employee/HR screens were restyled by theme only |

## Real-time
Data views refetch on server-sent change events (`metrics`, `campaigns`, `remediation`). Header Live pill reflects the SSE connection. Persona list refreshes every 15 s, model badge every 10 s. No hardcoded or mock data: all screens read the live DuckDB through the API.

## Security note
`/demo/personas` and the `X-Role` header are unauthenticated by request (no login). Replace `get_current_user` with SSO/JWT for production.
