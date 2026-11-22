import math
import statistics
from datetime import datetime, timezone
from typing import Any

from app.agents.campaign_graph import run_campaign_generation
from app.models.schemas import AuthUser, CampaignBrief, ConfigUpdate
from app.services import realtime
from app.services.auth import require_admin
from app.services.db import DBProtocol, get_db
from app.services.export import export_metrics_csv, export_metrics_pdf
from app.services.llm_gateway import LLMGateway
from app.services.risk_engine import get_adaptive_difficulty
from fastapi import APIRouter, Depends, HTTPException, Response

router = APIRouter(tags=["admin"])


def _wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)) / denom
    return round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)


def _compute_dashboard_data(db: DBProtocol, include_synthetic: bool = False) -> dict[str, Any]:
    users = db.select("users")
    if not include_synthetic:
        users = [u for u in users if not u.get("is_synthetic", False)]
    user_map = {u["id"]: u for u in users}
    user_ids = set(user_map.keys())

    sims = [s for s in db.select("simulations") if s["user_id"] in user_ids]
    sim_map = {s["id"]: s for s in sims}
    events = [e for e in db.select("events") if e["user_id"] in user_ids]
    risk_rows = [r for r in db.select("risk_scores") if r["user_id"] in user_ids]
    sessions = [cs for cs in db.select("coaching_sessions") if cs["user_id"] in user_ids]

    delivered = len(sims)
    clicked_sims = {e["simulation_id"] for e in events if e["type"] == "clicked"}
    submitted_sims = {e["simulation_id"] for e in events if e["type"] == "submitted"}
    reported_sims = {e["simulation_id"] for e in events if e["type"] == "reported"}

    # Median time-to-report in minutes
    report_durations: list[float] = []
    for e in events:
        if e["type"] == "reported" and e["simulation_id"] in sim_map:
            sim = sim_map[e["simulation_id"]]
            try:
                t_deliv = datetime.fromisoformat(str(sim["delivered_at"]).replace("Z", "+00:00"))
                t_rep = datetime.fromisoformat(str(e["ts"]).replace("Z", "+00:00"))
                report_durations.append(max(0.0, (t_rep - t_deliv).total_seconds() / 60.0))
            except Exception:
                pass
    median_ttr_min = round(statistics.median(report_durations), 2) if report_durations else None

    # Repeat-failure rate: users failing in 2+ campaigns / users failing >= 1
    user_failed_camps: dict[str, set[str]] = {}
    for e in events:
        if e["type"] in ("clicked", "submitted", "replied") and e["simulation_id"] in sim_map:
            cid = sim_map[e["simulation_id"]]["campaign_id"]
            user_failed_camps.setdefault(e["user_id"], set()).add(cid)
    users_failed_once = len(user_failed_camps)
    users_failed_multi = sum(1 for cs in user_failed_camps.values() if len(cs) >= 2)

    # Department breakdown
    dept_buckets: dict[str, dict[str, Any]] = {}
    for u in users:
        d = u["department"]
        dept_buckets.setdefault(
            d,
            {"department": d, "user_count": 0, "delivered": 0, "clicked": 0, "submitted": 0, "reported": 0, "scores": []},
        )
        dept_buckets[d]["user_count"] += 1
    for s in sims:
        d = user_map[s["user_id"]]["department"]
        dept_buckets[d]["delivered"] += 1
        if s["id"] in clicked_sims:
            dept_buckets[d]["clicked"] += 1
        if s["id"] in submitted_sims:
            dept_buckets[d]["submitted"] += 1
        if s["id"] in reported_sims:
            dept_buckets[d]["reported"] += 1
    for r in risk_rows:
        d = user_map[r["user_id"]]["department"]
        dept_buckets[d]["scores"].append(float(r["score"]))

    by_department = []
    for b in dept_buckets.values():
        scores = b.pop("scores")
        b["avg_risk_score"] = round(sum(scores) / len(scores), 2) if scores else 0.0
        by_department.append(b)

    band_counts = {"Low": 0, "Medium": 0, "High": 0}
    for r in risk_rows:
        band = r.get("band", "Low")
        band_counts[band] = band_counts.get(band, 0) + 1

    recent_events = [
        {
            "anon_id": user_map[e["user_id"]]["anon_id"],
            "department": user_map[e["user_id"]]["department"],
            "type": e["type"],
            "ts": e["ts"],
        }
        for e in sorted(events, key=lambda ev: str(ev["ts"]), reverse=True)[:15]
    ]

    return {
        "include_synthetic": include_synthetic,
        "recent_events": recent_events,
        "summary": {
            "total_users": len(users),
            "delivered": delivered,
            "click_rate": round(len(clicked_sims) / delivered, 4) if delivered else 0.0,
            "submit_rate": round(len(submitted_sims) / delivered, 4) if delivered else 0.0,
            "report_rate": round(len(reported_sims) / delivered, 4) if delivered else 0.0,
            "median_time_to_report_min": median_ttr_min,
            "repeat_failure_rate": round(users_failed_multi / users_failed_once, 4) if users_failed_once else 0.0,
            "coaching_views": sum(1 for cs in sessions if cs["kind"] == "feedback"),
            "chat_sessions": sum(1 for cs in sessions if cs["kind"] == "chat"),
            "chat_completed": sum(1 for cs in sessions if cs["kind"] == "chat" and cs.get("ended_at")),
        },
        "risk_bands": band_counts,
        "by_department": by_department,
    }


@router.get("/admin/dashboard")
def admin_dashboard(
    include_synthetic: bool = False,
    show_query: bool = False,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict[str, Any]:
    capture = getattr(db, "capture_sql", None)
    if show_query and capture:
        # Show the statements that actually ran for this response, not a hand-written approximation.
        with capture() as executed:
            data = _compute_dashboard_data(db, include_synthetic=include_synthetic)
        data["queries"] = list(dict.fromkeys(executed))
    else:
        data = _compute_dashboard_data(db, include_synthetic=include_synthetic)
    return data


@router.get("/admin/users/risk")
def admin_users_risk(
    include_synthetic: bool = False,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> list[dict[str, Any]]:
    users = db.select("users")
    if not include_synthetic:
        users = [u for u in users if not u.get("is_synthetic", False)]
    risk_by_uid = {r["user_id"]: r for r in db.select("risk_scores")}
    result = []
    for u in users:
        r = risk_by_uid.get(u["id"], {"score": 0.0, "band": "Low", "updated_at": None})
        result.append(
            {
                "user_id": u["id"],
                "anon_id": u["anon_id"],
                "department": u["department"],
                "role_name": u["role_name"],
                "arm": u["arm"],
                "is_synthetic": u.get("is_synthetic", False),
                "score": float(r["score"]),
                "band": r["band"],
                "updated_at": r.get("updated_at"),
            }
        )
    result.sort(key=lambda x: x["score"], reverse=True)
    return result


@router.get("/admin/remediation")
def admin_remediation_queue(
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> list[dict[str, Any]]:
    queue = db.select("remediation_queue", order="created_at", desc=True)
    users = {u["id"]: u for u in db.select("users")}
    for item in queue:
        u = users.get(item["user_id"], {})
        item["anon_id"] = u.get("anon_id")
        item["department"] = u.get("department")
        item["role_name"] = u.get("role_name")
    return queue


@router.post("/admin/remediation/{item_id}/launch")
async def launch_remediation(
    item_id: str,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict[str, Any]:
    rows = db.select("remediation_queue", filters={"id": item_id}, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="Remediation item not found")
    item = rows[0]
    if item["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Remediation item is already {item['status']}")
    u_rows = db.select("users", filters={"id": item["user_id"]}, limit=1)
    if not u_rows:
        raise HTTPException(status_code=404, detail="Target user not found")
    user = u_rows[0]

    # Follow-up difficulty tracks the person's live risk band; the email is generated for their role by the LLM.
    brief = CampaignBrief(
        theme="Targeted Remediation Follow-up",
        department=user["department"],
        role_name=user["role_name"],
        difficulty=get_adaptive_difficulty(db, user["id"]),
        wave_no=2,
        notes=f"Follow-up after: {item['reason']}",
        target_user_ids=[user["id"]],
    )
    email_json, source = await run_campaign_generation(db, LLMGateway(db), brief)

    camp = db.insert(
        "campaigns",
        {
            "created_by": admin.id,
            "brief_json": brief.model_dump(),
            "target_filter": {
                "department": user["department"],
                "role_name": user["role_name"],
                "target_user_ids": [user["id"]],
            },
            "wave_no": 2,
            "status": "draft",
        },
    )[0]
    tmpl = db.insert(
        "templates",
        {
            "campaign_id": camp["id"],
            "email_json": email_json,
            "planted_flags": email_json.get("planted_flags", []),
            "difficulty": brief.difficulty,
            "source": source,
            "status": "draft",
        },
    )[0]
    updated = db.update(
        "remediation_queue",
        {"status": "launched", "campaign_id": camp["id"]},
        {"id": item_id},
    )[0]
    db.insert(
        "audit_log",
        {
            "actor": admin.anon_id,
            "action": "remediation_launched",
            "entity": item_id,
            "meta": {"campaign_id": camp["id"], "target_anon_id": user["anon_id"]},
        },
    )
    realtime.publish("remediation", "campaigns")
    return {"remediation": updated, "campaign": camp, "template": tmpl}


@router.get("/admin/config")
def get_admin_config(
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict[str, Any]:
    rows = db.select("app_config")
    cfg = {r["key"]: r["value_json"] for r in rows}
    budget = LLMGateway(db).get_budget_status()
    return {"config": cfg, "llm_budget": budget}


def _validate_config_update(key: str, existing: dict[str, Any], new: dict[str, Any]) -> None:
    """Keep config structurally compatible with the code that reads it."""
    problems: list[str] = []
    for field, old_val in existing.items():
        if field not in new:
            if key == "role_multipliers" and field != "default":
                continue  # departments may be removed
            problems.append(f"missing field '{field}'")
            continue
        val = new[field]
        old_is_num = isinstance(old_val, (int, float)) and not isinstance(old_val, bool)
        if old_is_num:
            if not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val):
                problems.append(f"'{field}' must be a finite number")
            elif key != "risk_weights" and val < 0:
                problems.append(f"'{field}' must not be negative")
        elif type(old_val) is not type(val):
            problems.append(f"'{field}' must be {type(old_val).__name__}")
    if key == "role_multipliers":
        for field, val in new.items():
            if not isinstance(val, (int, float)) or isinstance(val, bool) or val <= 0:
                problems.append(f"multiplier '{field}' must be a positive number")
    if key == "band_thresholds" and not problems and not new["medium"] < new["high"]:
        problems.append("'medium' must be lower than 'high'")
    if key == "chat_turn_cap" and not problems and not 1 <= new["max_turns"] <= 20:
        problems.append("'max_turns' must be between 1 and 20")
    if key == "min_cohort_size" and not problems and new["min_cohort_size"] < 2:
        problems.append("'min_cohort_size' must be at least 2 to preserve anonymity")
    if problems:
        raise HTTPException(status_code=422, detail=f"Invalid value for {key}: {'; '.join(problems)}")


@router.put("/admin/config/{key}")
def update_admin_config(
    key: str,
    payload: ConfigUpdate,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict[str, Any]:
    current = db.select("app_config", filters={"key": key}, limit=1)
    if not current:
        raise HTTPException(status_code=404, detail=f"Unknown config key '{key}'")
    _validate_config_update(key, current[0]["value_json"], payload.value_json)
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = db.upsert(
        "app_config",
        {
            "key": key,
            "value_json": payload.value_json,
            "updated_by": admin.anon_id,
            "updated_at": now_iso,
        },
        on_conflict="key",
    )
    db.insert(
        "audit_log",
        {
            "actor": admin.anon_id,
            "action": "config_updated",
            "entity": key,
            "meta": {"value_json": payload.value_json},
        },
    )
    realtime.publish("config", "metrics")
    return updated[0]


@router.get("/admin/pilot")
def admin_pilot_view(
    include_synthetic: bool = False,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict[str, Any]:
    users = db.select("users")
    if not include_synthetic:
        users = [u for u in users if not u.get("is_synthetic", False)]
    user_map = {u["id"]: u for u in users}

    campaigns = {c["id"]: c for c in db.select("campaigns")}
    sims = [s for s in db.select("simulations") if s["user_id"] in user_map]
    events = [e for e in db.select("events") if e["user_id"] in user_map]
    clicked_sims = {e["simulation_id"] for e in events if e["type"] == "clicked"}
    reported_sims = {e["simulation_id"] for e in events if e["type"] == "reported"}

    arms: dict[str, dict[int, dict[str, int]]] = {
        "control": {1: {"delivered": 0, "clicked": 0, "reported": 0}, 2: {"delivered": 0, "clicked": 0, "reported": 0}},
        "treatment": {1: {"delivered": 0, "clicked": 0, "reported": 0}, 2: {"delivered": 0, "clicked": 0, "reported": 0}},
    }

    for s in sims:
        arm = user_map[s["user_id"]]["arm"]
        wave = int(campaigns.get(s["campaign_id"], {}).get("wave_no", 1))
        wave_key = 1 if wave <= 1 else 2
        arms[arm][wave_key]["delivered"] += 1
        if s["id"] in clicked_sims:
            arms[arm][wave_key]["clicked"] += 1
        if s["id"] in reported_sims:
            arms[arm][wave_key]["reported"] += 1

    summary = {}
    for arm in ("control", "treatment"):
        summary[arm] = {}
        for w in (1, 2):
            d = arms[arm][w]["delivered"]
            c = arms[arm][w]["clicked"]
            r = arms[arm][w]["reported"]
            summary[arm][f"wave_{w}"] = {
                "delivered": d,
                "clicked": c,
                "click_rate": round(c / d, 4) if d else 0.0,
                "click_ci_95": _wilson_ci(c, d),
                "reported": r,
                "report_rate": round(r / d, 4) if d else 0.0,
                "report_ci_95": _wilson_ci(r, d),
            }

    ctrl_delta = summary["control"]["wave_2"]["click_rate"] - summary["control"]["wave_1"]["click_rate"]
    trt_delta = summary["treatment"]["wave_2"]["click_rate"] - summary["treatment"]["wave_1"]["click_rate"]
    did_click = round(trt_delta - ctrl_delta, 4)

    return {
        "include_synthetic": include_synthetic,
        "sample_size_users": len(users),
        "arms": summary,
        "diff_in_diff_click_rate": did_click,
        "interpretation_note": "With small pilot samples, confidence intervals are wide; treat results as indicative, not conclusive.",
    }


@router.get("/admin/export")
def admin_export(
    format: str = "csv",
    include_synthetic: bool = False,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
):
    dash = _compute_dashboard_data(db, include_synthetic=include_synthetic)
    rows = dash["by_department"]
    if format.lower() == "pdf":
        pdf_bytes = export_metrics_pdf("PhishCoach AI - Department Readiness Report", rows)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=phishcoach_report.pdf"},
        )
    csv_text = export_metrics_csv(rows)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=phishcoach_report.csv"},
    )
