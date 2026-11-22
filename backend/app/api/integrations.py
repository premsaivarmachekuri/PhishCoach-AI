import hmac
from datetime import datetime, timezone

import httpx
from app.adapters.hr import HRAdapter, HTTPHRAdapter
from app.models.schemas import AuthUser, EventType
from app.services import realtime
from app.services.auth import require_admin
from app.services.config import get_settings
from app.services.db import ConflictError, DBProtocol, get_db
from app.services.hr_sync import sync_employees
from app.services.risk_engine import compute_user_risk
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

router = APIRouter(tags=["integrations"])


def get_hr_adapter() -> HRAdapter:
    return HTTPHRAdapter()


class SimWebhookPayload(BaseModel):
    simulation_id: str
    type: EventType


@router.post("/integrations/hr/sync")
async def sync_hr_employees(
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
    hr_adapter: HRAdapter = Depends(get_hr_adapter),
) -> dict:
    try:
        result = await sync_employees(db, hr_adapter)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"HR system unreachable: {exc}") from exc
    db.insert(
        "audit_log",
        {"actor": admin.anon_id, "action": "hr_sync", "entity": "users", "meta": result},
    )
    realtime.publish("metrics")
    return result


def verify_webhook_secret(x_webhook_secret: str | None = Header(default=None)) -> None:
    expected = get_settings().sim_webhook_secret.strip()
    if len(expected) < 16:
        raise HTTPException(status_code=503, detail="Webhook authentication is not configured")
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")


@router.post("/integrations/sim/webhook", dependencies=[Depends(verify_webhook_secret)])
def sim_webhook(
    payload: SimWebhookPayload,
    db: DBProtocol = Depends(get_db),
) -> dict:
    sims = db.select("simulations", filters={"id": payload.simulation_id}, limit=1)
    if not sims:
        raise HTTPException(status_code=404, detail="simulation_not_found")
    sim = sims[0]
    users = db.select("users", filters={"id": sim["user_id"]}, limit=1)
    is_synthetic = bool(users and users[0].get("is_synthetic"))

    duplicate = bool(
        db.select("events", filters={"simulation_id": payload.simulation_id, "type": payload.type}, limit=1)
    )
    if not duplicate:
        try:
            db.insert(
                "events",
                {
                    "simulation_id": payload.simulation_id,
                    "user_id": sim["user_id"],
                    "type": payload.type,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "is_synthetic": is_synthetic,
                },
            )
        except ConflictError:
            duplicate = True
    risk = compute_user_risk(db, sim["user_id"])
    if not duplicate:
        realtime.publish("metrics", "remediation", f"inbox:{sim['user_id']}")
    return {"status": "duplicate" if duplicate else "ok", "risk": risk}
