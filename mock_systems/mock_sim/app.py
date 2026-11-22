from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Mock Simulation Platform", version="1.0.0")

_CAMPAIGNS: dict[str, list[dict]] = {}
_EVENTS: list[dict] = []


class DeployPayload(BaseModel):
    campaign_id: str
    deliveries: list[dict]


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-sim"}


@app.post("/mock/sim/campaigns")
def deploy_campaign(payload: DeployPayload):
    _CAMPAIGNS[payload.campaign_id] = payload.deliveries
    return {
        "status": "accepted",
        "campaign_id": payload.campaign_id,
        "queued_deliveries": len(payload.deliveries),
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/mock/sim/events")
def get_events(campaign_id: str | None = None):
    if campaign_id:
        return {"events": [e for e in _EVENTS if e.get("campaign_id") == campaign_id]}
    return {"events": _EVENTS}
