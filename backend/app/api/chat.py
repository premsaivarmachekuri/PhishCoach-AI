import json
from datetime import datetime, timezone

from app.agents.chat_graph import (
    generate_opener,
    stream_attacker_turn,
    summarize_chat_session,
)
from app.models.schemas import AuthUser, ChatMessageCreate, ChatOutcome, ChatSessionCreate
from app.services import realtime
from app.services.appconfig import get_config, require_field
from app.services.db import DBProtocol, get_db
from app.services.llm_gateway import LLMGateway, LLMUnavailableError
from app.services.ratelimit import rate_limit
from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["chat"])


def _require_treatment(user: AuthUser) -> None:
    if user.arm != "treatment":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Practice chat is only available to the treatment arm",
        )


def _own_session(db: DBProtocol, session_id: str, user: AuthUser) -> dict:
    rows = db.select(
        "coaching_sessions",
        filters={"id": session_id, "user_id": user.id, "kind": "chat"},
        limit=1,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return rows[0]


@router.post("/chat/sessions", status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    payload: ChatSessionCreate,
    user: AuthUser = Depends(rate_limit("chat_per_min")),
    db: DBProtocol = Depends(get_db),
) -> dict:
    _require_treatment(user)
    opener = await generate_opener(LLMGateway(db), user.role_name, user.department, payload.scenario_topic)
    session = db.insert(
        "coaching_sessions",
        {
            "user_id": user.id,
            "simulation_id": payload.simulation_id,
            "kind": "chat",
            "turns": 0,
            "messages_json": [{"role": "assistant", "content": opener}],
            "source": "llm",
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )[0]
    realtime.publish("metrics")
    return session


@router.post("/chat/sessions/{session_id}/messages")
async def send_chat_message(
    session_id: str,
    payload: ChatMessageCreate,
    user: AuthUser = Depends(rate_limit("chat_per_min")),
    db: DBProtocol = Depends(get_db),
):
    _require_treatment(user)
    session = _own_session(db, session_id, user)
    if session.get("ended_at"):
        raise HTTPException(status_code=400, detail="Chat session has already ended")

    cap_cfg = get_config(db, "chat_turn_cap")
    max_turns = int(require_field(cap_cfg, "chat_turn_cap", "max_turns"))
    current_turns = int(session.get("turns", 0))
    if current_turns >= max_turns:
        raise HTTPException(status_code=400, detail="Chat turn cap reached; please end session for debrief")

    gateway = LLMGateway(db)
    try:
        blocked, end_outcome, cleaned, token_iter = await stream_attacker_turn(
            gateway=gateway,
            session=session,
            user_message=payload.content,
            role_name=user.role_name,
            department=user.department,
        )
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}") from exc

    if blocked:
        db.insert(
            "audit_log",
            {
                "actor": user.anon_id,
                "action": "chat_guardrail_blocked",
                "entity": session_id,
                "meta": {"reason": "prompt_injection_or_unsafe"},
            },
        )

    async def event_generator():
        chunks: list[str] = []
        try:
            async for tok in token_iter:
                chunks.append(tok)
                yield {"event": "token", "data": json.dumps({"token": tok})}
        except LLMUnavailableError as exc:
            # No canned reply: tell the client the turn failed and do not record it.
            yield {"event": "error", "data": json.dumps({"detail": f"AI service unavailable: {exc}"})}
            return

        if blocked:
            # Blocked input is never persisted into history that later reaches the model.
            yield {
                "event": "done",
                "data": json.dumps(
                    {"turns": current_turns, "max_turns": max_turns, "blocked": True, "outcome": None, "debrief": None}
                ),
            }
            return

        messages: list[dict[str, str]] = list(session.get("messages_json", []))
        messages.append({"role": "user", "content": cleaned})
        messages.append({"role": "assistant", "content": "".join(chunks)})
        new_turns = current_turns + 1
        final_outcome = end_outcome or ("turn_cap" if new_turns >= max_turns else None)
        update_data: dict = {"turns": new_turns, "messages_json": messages}
        debrief = None
        if final_outcome:
            try:
                debrief = await summarize_chat_session(gateway, messages, final_outcome)
            except LLMUnavailableError as exc:
                yield {"event": "error", "data": json.dumps({"detail": f"Debrief unavailable: {exc}"})}
            update_data["outcome"] = final_outcome
            update_data["ended_at"] = datetime.now(timezone.utc).isoformat()
        db.update("coaching_sessions", update_data, {"id": session_id})
        realtime.publish("metrics")
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "turns": new_turns,
                    "max_turns": max_turns,
                    "blocked": False,
                    "outcome": final_outcome,
                    "debrief": debrief,
                }
            ),
        }

    return EventSourceResponse(event_generator())


@router.post("/chat/sessions/{session_id}/end")
async def end_chat_session(
    session_id: str,
    outcome: ChatOutcome = "completed",
    user: AuthUser = Depends(rate_limit("chat_per_min")),
    db: DBProtocol = Depends(get_db),
) -> dict:
    session = _own_session(db, session_id, user)
    if session.get("ended_at"):
        raise HTTPException(status_code=400, detail="Chat session has already ended")
    try:
        debrief = await summarize_chat_session(LLMGateway(db), session.get("messages_json", []), outcome)
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}") from exc
    updated = db.update(
        "coaching_sessions",
        {"outcome": outcome, "ended_at": datetime.now(timezone.utc).isoformat()},
        {"id": session_id},
    )
    realtime.publish("metrics")
    return {"session": updated[0], "debrief": debrief}
