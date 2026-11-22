from typing import Any, Protocol

import httpx
from app.services.config import get_settings


class SimulationPlatformAdapter(Protocol):
    async def deploy_campaign(
        self,
        campaign_id: str,
        deliveries: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    async def fetch_events(self, campaign_id: str) -> list[dict[str, Any]]: ...


class HTTPSimPlatformAdapter:
    """HTTP adapter talking to the external/mock simulation platform."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or get_settings().sim_api_url).rstrip("/")

    async def deploy_campaign(
        self,
        campaign_id: str,
        deliveries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.base_url}/mock/sim/campaigns",
                json={"campaign_id": campaign_id, "deliveries": deliveries},
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_events(self, campaign_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self.base_url}/mock/sim/events",
                params={"campaign_id": campaign_id},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("events", data) if isinstance(data, dict) else data
