from typing import Any

from app.models.schemas import AuthUser
from app.services.appconfig import get_config, require_field
from app.services.auth import require_hr_or_admin
from app.services.db import DBProtocol, get_db
from fastapi import APIRouter, Depends

router = APIRouter(tags=["hr"])


@router.get("/hr/aggregates")
def get_hr_aggregates(
    include_synthetic: bool = False,
    user: AuthUser = Depends(require_hr_or_admin),
    db: DBProtocol = Depends(get_db),
) -> dict[str, Any]:
    cfg = get_config(db, "min_cohort_size")
    min_cohort = int(require_field(cfg, "min_cohort_size", "min_cohort_size"))

    users = db.select("users")
    if not include_synthetic:
        users = [u for u in users if not u.get("is_synthetic", False)]
    user_map = {u["id"]: u for u in users}
    user_ids = set(user_map.keys())

    sims = [s for s in db.select("simulations") if s["user_id"] in user_ids]
    events = [e for e in db.select("events") if e["user_id"] in user_ids]
    risk_rows = [r for r in db.select("risk_scores") if r["user_id"] in user_ids]

    clicked_sims = {e["simulation_id"] for e in events if e["type"] == "clicked"}
    submitted_sims = {e["simulation_id"] for e in events if e["type"] == "submitted"}
    reported_sims = {e["simulation_id"] for e in events if e["type"] == "reported"}

    buckets: dict[str, dict[str, Any]] = {}
    for u in users:
        d = u["department"]
        buckets.setdefault(
            d,
            {"department": d, "user_count": 0, "delivered": 0, "clicked": 0, "submitted": 0, "reported": 0, "scores": []},
        )
        buckets[d]["user_count"] += 1

    for s in sims:
        d = user_map[s["user_id"]]["department"]
        buckets[d]["delivered"] += 1
        if s["id"] in clicked_sims:
            buckets[d]["clicked"] += 1
        if s["id"] in submitted_sims:
            buckets[d]["submitted"] += 1
        if s["id"] in reported_sims:
            buckets[d]["reported"] += 1

    for r in risk_rows:
        d = user_map[r["user_id"]]["department"]
        buckets[d]["scores"].append(float(r["score"]))

    # Enforce minimum cohort size — never return cohorts below min_cohort or individual IDs
    cohorts = []
    suppressed_count = 0
    for b in buckets.values():
        if b["user_count"] < min_cohort:
            suppressed_count += 1
            continue
        scores = b.pop("scores")
        d_count = b["delivered"]
        cohorts.append(
            {
                "department": b["department"],
                "user_count": b["user_count"],
                "delivered": d_count,
                "click_rate": round(b["clicked"] / d_count, 4) if d_count else 0.0,
                "submit_rate": round(b["submitted"] / d_count, 4) if d_count else 0.0,
                "report_rate": round(b["reported"] / d_count, 4) if d_count else 0.0,
                "avg_risk_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            }
        )

    return {
        "min_cohort_size": min_cohort,
        "suppressed_departments": suppressed_count,
        "cohorts": cohorts,
    }
