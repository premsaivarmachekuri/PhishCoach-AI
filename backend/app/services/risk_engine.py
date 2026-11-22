import math
from datetime import datetime, timezone
from typing import Any

from app.services.appconfig import get_all_config, require_config, require_field
from app.services.db import DBProtocol


def compute_user_risk(db: DBProtocol, user_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Recompute risk score and band for a user from events + app_config (no in-code defaults)."""
    now = now or datetime.now(timezone.utc)
    cfg = get_all_config(db)

    weights = require_config(cfg, "risk_weights")
    half_life = float(require_field(require_config(cfg, "decay_half_life_days"), "decay_half_life_days", "days"))
    role_multipliers = require_config(cfg, "role_multipliers")
    thresholds = require_config(cfg, "band_thresholds")
    med_t = float(require_field(thresholds, "band_thresholds", "medium"))
    high_t = float(require_field(thresholds, "band_thresholds", "high"))

    user_rows = db.select("users", filters={"id": user_id}, limit=1)
    if not user_rows:
        raise ValueError(f"User {user_id} not found")
    user = user_rows[0]
    role_key = str(user.get("department", "")).lower()
    role_mult = float(role_multipliers.get(role_key, require_field(role_multipliers, "role_multipliers", "default")))

    events = db.select("events", filters={"user_id": user_id})
    sims = {s["id"]: s for s in db.select("simulations", filters={"user_id": user_id})}
    template_ids = list({s["template_id"] for s in sims.values()})
    templates = {t["id"]: t for t in db.select("templates", filters={"id": template_ids})}

    raw = 0.0
    failed_campaigns: set[str] = set()

    for ev in events:
        ev_type = ev["type"]
        w = float(weights.get(ev_type, 0.0))
        ts_val = ev.get("ts")
        if isinstance(ts_val, str):
            ts_dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
        elif isinstance(ts_val, datetime):
            ts_dt = ts_val
        else:
            ts_dt = now
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)

        age_days = max(0.0, (now - ts_dt).total_seconds() / 86400.0)
        decay = math.pow(0.5, age_days / max(half_life, 1.0))

        sim = sims.get(ev["simulation_id"], {})
        tmpl = templates.get(sim.get("template_id", ""), {})
        difficulty = int(tmpl.get("difficulty", 1))
        difficulty_factor = 1.0 + 0.15 * (difficulty - 1)

        raw += w * decay * difficulty_factor

        if ev_type in ("clicked", "submitted", "replied") and sim.get("campaign_id"):
            failed_campaigns.add(sim["campaign_id"])

    scaled = raw * role_mult
    if scaled <= 0:
        score = 0.0
    else:
        # Smooth saturation to 0..100
        score = round(min(100.0, max(0.0, 100.0 * scaled / (scaled + 25.0))), 2)

    if score >= high_t:
        band = "High"
    elif score >= med_t:
        band = "Medium"
    else:
        band = "Low"

    db.upsert(
        "risk_scores",
        {
            "user_id": user_id,
            "score": score,
            "band": band,
            "updated_at": now.isoformat(),
        },
        on_conflict="user_id",
    )

    # Remediation rule: High band or 2+ distinct failed campaigns
    reason: str | None = None
    if band == "High":
        reason = "Entered High risk band"
    elif len(failed_campaigns) >= 2:
        reason = "Repeat failure across multiple campaigns"

    if reason:
        open_item = [
            r
            for r in db.select("remediation_queue", filters={"user_id": user_id})
            if r["status"] in ("pending", "approved")
        ]
        if not open_item:
            db.insert(
                "remediation_queue",
                {"user_id": user_id, "reason": reason, "status": "pending"},
            )

    return {"user_id": user_id, "score": score, "band": band}


def get_adaptive_difficulty(db: DBProtocol, user_id: str) -> int:
    cfg = get_all_config(db)
    diff_map = require_config(cfg, "difficulty_map")
    risk_rows = db.select("risk_scores", filters={"user_id": user_id}, limit=1)
    band = risk_rows[0]["band"] if risk_rows else "Low"
    return int(require_field(diff_map, "difficulty_map", band))
