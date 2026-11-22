import json
import uuid
from datetime import datetime, timezone

from app.agents.coach_graph import rules_coaching, stream_coaching_feedback
from app.models.schemas import AuthUser, CoachAction
from app.services import realtime
from app.services.db import DBProtocol, get_db
from app.services.llm_gateway import LLMGateway, LLMUnavailableError
from app.services.ratelimit import rate_limit
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["coaching"])


@router.post("/coach/{simulation_id}")
async def coach_simulation(
    simulation_id: str,
    action: CoachAction = "clicked",
    user: AuthUser = Depends(rate_limit("coach_per_min")),
    db: DBProtocol = Depends(get_db),
):
    sims = db.select("simulations", filters={"id": simulation_id, "user_id": user.id}, limit=1)
    if not sims:
        raise HTTPException(status_code=404, detail="Simulation not found")
    sim = sims[0]

    # Coaching must respond to something the employee actually did.
    performed = db.select("events", filters={"simulation_id": simulation_id, "type": action}, limit=1)
    if not performed:
        raise HTTPException(status_code=409, detail=f"No '{action}' event recorded for this simulation")

    tmpls = db.select("templates", filters={"id": sim["template_id"]}, limit=1)
    if not tmpls:
        raise HTTPException(status_code=404, detail="Template not found")
    tmpl = tmpls[0]

    source_tag, token_iter = await stream_coaching_feedback(
        db=db,
        gateway=LLMGateway(db),
        user=user.model_dump(),
        simulation=sim,
        template=tmpl,
        action_type=action,
    )
    session_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    async def event_generator():
        nonlocal source_tag
        yield {
            "event": "meta",
            "data": json.dumps(
                {
                    "session_id": session_id,
                    "source": source_tag,
                    "arm": user.arm,
                    "planted_flags": tmpl.get("planted_flags", []),
                }
            ),
        }
        chunks: list[str] = []
        try:
            async for tok in token_iter:
                chunks.append(tok)
                yield {"event": "token", "data": json.dumps({"token": tok})}
        except LLMUnavailableError:
            # Every model in the chain failed. Degrade to the rules coach (built from the real event +
            # playbook rows) so the employee is never left without feedback at the moment it matters.
            try:
                text = rules_coaching(
                    action,
                    tmpl.get("email_json") or {},
                    tmpl.get("planted_flags") or [],
                    db.search_kb(" ".join(tmpl.get("planted_flags") or []), limit=6),
                )
            except Exception as exc:  # noqa: BLE001 - last line of defence must not crash the stream
                yield {"event": "error", "data": json.dumps({"detail": f"Coaching unavailable: {exc}"})}
                return
            source_tag = "fallback"
            if chunks:
                text = "\n\n" + text
            chunks.append(text)
            yield {"event": "meta", "data": json.dumps({"session_id": session_id, "source": source_tag,
                                                        "arm": user.arm, "planted_flags": tmpl.get("planted_flags", [])})}
            yield {"event": "token", "data": json.dumps({"token": text})}
        db.insert(
            "coaching_sessions",
            {
                "id": session_id,
                "user_id": user.id,
                "simulation_id": simulation_id,
                "kind": "feedback",
                "turns": 1,
                "outcome": action,
                "messages_json": [{"role": "coach", "content": "".join(chunks)}],
                "source": source_tag,
                "started_at": started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        realtime.publish("metrics")
        yield {"event": "done", "data": json.dumps({"session_id": session_id, "source": source_tag})}

    return EventSourceResponse(event_generator())
