from datetime import datetime, timezone

import httpx
from app.adapters.sim_platform import HTTPSimPlatformAdapter, SimulationPlatformAdapter
from app.agents.campaign_graph import BriefRejectedError, run_campaign_generation
from app.models.schemas import AuthUser, CampaignBrief, TemplatePatch
from app.services import realtime
from app.services.auth import require_admin
from app.services.db import DBProtocol, get_db
from app.services.guardrails import check_email_guardrails, check_planted_flags
from app.services.llm_gateway import LLMGateway
from app.services.risk_engine import get_adaptive_difficulty
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(tags=["campaigns"])


def get_sim_adapter() -> SimulationPlatformAdapter:
    return HTTPSimPlatformAdapter()


def _get_campaign(db: DBProtocol, campaign_id: str) -> dict:
    camps = db.select("campaigns", filters={"id": campaign_id}, limit=1)
    if not camps:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return camps[0]


@router.get("/campaigns")
def list_campaigns(
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> list[dict]:
    campaigns = db.select("campaigns", order="created_at", desc=True)
    tmpl_by_camp: dict[str, list[dict]] = {}
    for t in db.select("templates", order="created_at"):
        tmpl_by_camp.setdefault(t["campaign_id"], []).append(t)
    sims_by_camp: dict[str, int] = {}
    for s in db.select("simulations", columns="campaign_id"):
        sims_by_camp[s["campaign_id"]] = sims_by_camp.get(s["campaign_id"], 0) + 1
    for c in campaigns:
        c["templates"] = tmpl_by_camp.get(c["id"], [])
        c["delivered_count"] = sims_by_camp.get(c["id"], 0)
    return campaigns


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    brief: CampaignBrief,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict:
    # Generation happens first: if the LLM pipeline fails, nothing is persisted and the admin sees the real error.
    try:
        email_json, source = await run_campaign_generation(db, LLMGateway(db), brief)
    except BriefRejectedError as exc:
        db.insert(
            "audit_log",
            {
                "actor": admin.anon_id,
                "action": "campaign_brief_rejected",
                "entity": "campaign_brief",
                "meta": {"theme": brief.theme[:200], "department": brief.department, "reason": exc.reason},
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Not acceptable: {exc.reason} Guardrails only allow realistic, fictional, "
                "department-relevant phishing-awareness scenarios."
            ),
        ) from exc

    target_filter = {
        "department": brief.department,
        "role_name": brief.role_name,
        "target_user_ids": brief.target_user_ids,
    }
    campaign = db.insert(
        "campaigns",
        {
            "created_by": admin.id,
            "brief_json": brief.model_dump(),
            "target_filter": target_filter,
            "wave_no": brief.wave_no,
            "status": "draft",
        },
    )[0]
    template = db.insert(
        "templates",
        {
            "campaign_id": campaign["id"],
            "email_json": email_json,
            "planted_flags": email_json.get("planted_flags", []),
            "difficulty": brief.difficulty,
            "source": source,
            "status": "draft",
        },
    )[0]
    db.insert(
        "audit_log",
        {
            "actor": admin.anon_id,
            "action": "campaign_created",
            "entity": campaign["id"],
            "meta": {"source": source, "wave_no": brief.wave_no},
        },
    )
    realtime.publish("campaigns")
    return {"campaign": campaign, "template": template}


@router.get("/campaigns/{campaign_id}")
def get_campaign(
    campaign_id: str,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict:
    camp = _get_campaign(db, campaign_id)
    return {"campaign": camp, "templates": db.select("templates", filters={"campaign_id": campaign_id})}


def _get_template(db: DBProtocol, campaign_id: str, template_id: str) -> dict:
    tmpls = db.select("templates", filters={"id": template_id, "campaign_id": campaign_id}, limit=1)
    if not tmpls:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpls[0]


@router.post("/campaigns/{campaign_id}/templates/{template_id}/approve")
def approve_template(
    campaign_id: str,
    template_id: str,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict:
    camp = _get_campaign(db, campaign_id)
    _get_template(db, campaign_id, template_id)
    if camp["status"] == "closed":
        raise HTTPException(status_code=400, detail="Campaign is closed")
    # One approved template per campaign: approving one supersedes any previously approved draft.
    for other in db.select("templates", filters={"campaign_id": campaign_id, "status": "approved"}):
        if other["id"] != template_id:
            db.update("templates", {"status": "draft"}, {"id": other["id"]})
    updated = db.update("templates", {"status": "approved"}, {"id": template_id})
    if camp["status"] == "draft":
        db.update("campaigns", {"status": "approved"}, {"id": campaign_id})
    db.insert(
        "audit_log",
        {
            "actor": admin.anon_id,
            "action": "template_approved",
            "entity": template_id,
            "meta": {"campaign_id": campaign_id},
        },
    )
    realtime.publish("campaigns")
    return updated[0]


@router.post("/campaigns/{campaign_id}/templates/{template_id}/reject")
def reject_template(
    campaign_id: str,
    template_id: str,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict:
    camp = _get_campaign(db, campaign_id)
    tmpl = _get_template(db, campaign_id, template_id)
    if camp["status"] == "live" and tmpl["status"] == "approved":
        raise HTTPException(status_code=400, detail="Cannot reject the template of a live campaign")
    updated = db.update("templates", {"status": "rejected"}, {"id": template_id})
    if not db.select("templates", filters={"campaign_id": campaign_id, "status": "approved"}, limit=1) and camp["status"] == "approved":
        db.update("campaigns", {"status": "draft"}, {"id": campaign_id})
    db.insert(
        "audit_log",
        {
            "actor": admin.anon_id,
            "action": "template_rejected",
            "entity": template_id,
            "meta": {"campaign_id": campaign_id},
        },
    )
    realtime.publish("campaigns")
    return updated[0]


@router.patch("/templates/{template_id}")
def patch_template(
    template_id: str,
    patch: TemplatePatch,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict:
    tmpls = db.select("templates", filters={"id": template_id}, limit=1)
    if not tmpls:
        raise HTTPException(status_code=404, detail="Template not found")
    if db.select("simulations", filters={"template_id": template_id}, limit=1):
        raise HTTPException(status_code=409, detail="Template already delivered to employees and can no longer be edited")
    rules_ok, reasons = check_email_guardrails(patch.email_json)
    if not rules_ok:
        raise HTTPException(status_code=400, detail=f"Guardrail violation: {'; '.join(reasons)}")
    flags_ok, missing = check_planted_flags(patch.email_json)
    if not flags_ok:
        raise HTTPException(status_code=400, detail=f"Missing planted_flags signals: {', '.join(missing)}")

    updated = db.update(
        "templates",
        {
            "email_json": patch.email_json.model_dump(),
            "planted_flags": patch.planted_flags or patch.email_json.planted_flags,
            "source": "admin_edit",
            "status": "draft",
        },
        {"id": template_id},
    )
    realtime.publish("campaigns")
    return updated[0]


def select_targets(db: DBProtocol, camp: dict) -> list[dict]:
    all_users = db.select("users", filters={"app_role": "employee"})
    tfilter = camp.get("target_filter") or {}
    dept = str(tfilter.get("department") or "all").lower()
    role_name = str(tfilter.get("role_name") or "all").lower()
    explicit_ids = tfilter.get("target_user_ids")
    if explicit_ids is not None:
        return [u for u in all_users if u["id"] in explicit_ids]
    return [
        u
        for u in all_users
        if (dept == "all" or u["department"].lower() == dept)
        and (role_name == "all" or u["role_name"].lower() == role_name)
    ]


@router.post("/campaigns/{campaign_id}/deploy")
async def deploy_campaign(
    campaign_id: str,
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
    sim_adapter: SimulationPlatformAdapter = Depends(get_sim_adapter),
) -> dict:
    camp = _get_campaign(db, campaign_id)
    if camp["status"] == "closed":
        raise HTTPException(status_code=400, detail="Campaign is closed")

    approved_tmpls = db.select("templates", filters={"campaign_id": campaign_id, "status": "approved"}, limit=1)
    if not approved_tmpls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deploy campaign without an approved template",
        )
    template = approved_tmpls[0]

    targets = select_targets(db, camp)
    if not targets:
        raise HTTPException(status_code=400, detail="No matching employees found for target filter")

    deliveries = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for u in targets:
        existing = db.select("simulations", filters={"campaign_id": campaign_id, "user_id": u["id"]}, limit=1)
        sim = existing[0] if existing else db.insert(
            "simulations",
            {
                "campaign_id": campaign_id,
                "user_id": u["id"],
                "template_id": template["id"],
                "delivered_at": now_iso,
            },
        )[0]
        deliveries.append(
            {
                "simulation_id": sim["id"],
                "anon_id": u["anon_id"],
                "adaptive_difficulty": get_adaptive_difficulty(db, u["id"]),
            }
        )

    # The external platform must accept the deployment; no silent "queued locally" substitute.
    # Deploy is idempotent (existing simulations are reused), so the admin can simply retry.
    try:
        adapter_resp = await sim_adapter.deploy_campaign(campaign_id, deliveries)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Simulation platform rejected or could not be reached: {exc}") from exc

    db.update("campaigns", {"status": "live"}, {"id": campaign_id})
    db.insert(
        "audit_log",
        {
            "actor": admin.anon_id,
            "action": "campaign_deployed",
            "entity": campaign_id,
            "meta": {"delivered_count": len(deliveries)},
        },
    )
    realtime.publish("campaigns", "metrics", "remediation", *[f"inbox:{u['id']}" for u in targets])
    return {"campaign_id": campaign_id, "delivered_count": len(deliveries), "sim_adapter": adapter_resp}
