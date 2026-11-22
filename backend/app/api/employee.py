from datetime import datetime, timezone

from app.models.schemas import AuthUser, EventCreate
from app.services import realtime
from app.services.auth import get_current_user
from app.services.db import ConflictError, DBProtocol, get_db
from app.services.ratelimit import rate_limit
from app.services.risk_engine import compute_user_risk, get_adaptive_difficulty
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(tags=["employee"])


@router.get("/me/inbox")
def get_my_inbox(
    user: AuthUser = Depends(get_current_user),
    db: DBProtocol = Depends(get_db),
) -> list[dict]:
    sims = db.select("simulations", filters={"user_id": user.id}, order="delivered_at", desc=True)
    if not sims:
        return []
    templates = {t["id"]: t for t in db.select("templates", filters={"id": list({s["template_id"] for s in sims})})}
    events = db.select("events", filters={"user_id": user.id})
    events_by_sim: dict[str, list[str]] = {}
    for ev in events:
        events_by_sim.setdefault(ev["simulation_id"], []).append(ev["type"])

    inbox = []
    for sim in sims:
        tmpl = templates.get(sim["template_id"], {})
        if tmpl.get("source") == "fallback":  # legacy static template rows: only LLM-generated content is shown
            continue
        # planted_flags are the answer key: never ship them to the trainee before they act.
        email = {k: v for k, v in (tmpl.get("email_json") or {}).items() if k != "planted_flags"}
        inbox.append(
            {
                "simulation_id": sim["id"],
                "campaign_id": sim["campaign_id"],
                "delivered_at": sim["delivered_at"],
                "difficulty": tmpl.get("difficulty"),
                "source": tmpl.get("source"),
                "email": email,
                "actions": events_by_sim.get(sim["id"], []),
            }
        )
    return inbox


@router.get("/me/progress")
def get_my_progress(
    user: AuthUser = Depends(get_current_user),
    db: DBProtocol = Depends(get_db),
) -> dict:
    risk_rows = db.select("risk_scores", filters={"user_id": user.id}, limit=1)
    risk = risk_rows[0] if risk_rows else {"score": 0.0, "band": "Low", "updated_at": None}
    events = db.select("events", filters={"user_id": user.id}, order="ts", desc=True)
    sessions = db.select("coaching_sessions", filters={"user_id": user.id}, order="started_at", desc=True)
    sims = db.select("simulations", filters={"user_id": user.id})

    reported_count = len({e["simulation_id"] for e in events if e["type"] == "reported"})
    clicked_count = len({e["simulation_id"] for e in events if e["type"] == "clicked"})
    submitted_count = len({e["simulation_id"] for e in events if e["type"] == "submitted"})

    return {
        "anon_id": user.anon_id,
        "arm": user.arm,
        "department": user.department,
        "role_name": user.role_name,
        "risk_score": float(risk["score"]),
        "risk_band": risk["band"],
        "next_difficulty": get_adaptive_difficulty(db, user.id),
        "simulations_received": len(sims),
        "reported_count": reported_count,
        "clicked_count": clicked_count,
        "submitted_count": submitted_count,
        "coaching_sessions_count": len(sessions),
        "recent_sessions": [
            {k: v for k, v in s.items() if k != "messages_json"} for s in sessions[:5]
        ],
    }


@router.post("/events")
def record_event(
    payload: EventCreate,
    user: AuthUser = Depends(rate_limit("events_per_min")),
    db: DBProtocol = Depends(get_db),
) -> dict:
    sims = db.select("simulations", filters={"id": payload.simulation_id, "user_id": user.id}, limit=1)
    if not sims:
        raise HTTPException(status_code=404, detail="Simulation not found for current user")

    duplicate = False
    existing = db.select(
        "events",
        filters={"simulation_id": payload.simulation_id, "type": payload.type},
        limit=1,
    )
    if existing:
        ev, duplicate = existing[0], True
    else:
        try:
            ev = db.insert(
                "events",
                {
                    "simulation_id": payload.simulation_id,
                    "user_id": user.id,
                    "type": payload.type,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    # Only accounts provisioned as synthetic may emit synthetic events (no self-exclusion from metrics).
                    "is_synthetic": user.is_synthetic,
                },
            )[0]
        except ConflictError:  # concurrent duplicate hit the UNIQUE(simulation_id, type) constraint
            ev = db.select(
                "events",
                filters={"simulation_id": payload.simulation_id, "type": payload.type},
                limit=1,
            )[0]
            duplicate = True

    risk = compute_user_risk(db, user.id)
    if not duplicate:
        realtime.publish("metrics", "remediation", f"inbox:{user.id}")
    return {"event": ev, "duplicate": duplicate, "risk": risk}
