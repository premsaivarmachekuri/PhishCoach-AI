import asyncio

import httpx
from app.models.schemas import AuthUser
from app.services.auth import require_admin
from app.services.config import get_settings
from app.services.db import DBProtocol, get_db
from fastapi import APIRouter, Depends

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "phishcoach-api"}


async def _probe(client: httpx.AsyncClient, name: str, url: str, headers: dict[str, str] | None = None) -> dict:
    try:
        resp = await client.get(url, headers=headers)
        return {"name": name, "ok": resp.status_code < 400, "detail": f"HTTP {resp.status_code}"}
    except httpx.HTTPError as exc:
        return {"name": name, "ok": False, "detail": type(exc).__name__}


@router.get("/health/deps")
async def dependency_health(
    admin: AuthUser = Depends(require_admin),
    db: DBProtocol = Depends(get_db),
) -> dict:
    """Live reachability of every dependency, so the UI never has to guess."""
    s = get_settings()
    try:
        db.select("app_config", limit=1)
        db_check = {"name": "database", "ok": True, "detail": "query ok"}
    except Exception as exc:
        db_check = {"name": "database", "ok": False, "detail": type(exc).__name__}
    async with httpx.AsyncClient(timeout=5.0) as client:
        probes = await asyncio.gather(
            _probe(client, "llm (groq)", "https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {s.groq_api_key}"}),
            _probe(client, "hr system", f"{s.hr_api_url.rstrip('/')}/health"),
            _probe(client, "simulation platform", f"{s.sim_api_url.rstrip('/')}/health"),
        )
    return {"checks": [db_check, *probes]}
