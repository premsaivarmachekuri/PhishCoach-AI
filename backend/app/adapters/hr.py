from typing import Any, Protocol

import httpx
from app.services.config import get_settings


class HRAdapter(Protocol):
    async def fetch_employees(self) -> list[dict[str, Any]]: ...


class HTTPHRAdapter:
    """HTTP adapter talking to the external/mock HR service."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or get_settings().hr_api_url).rstrip("/")

    async def fetch_employees(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.base_url}/mock/hr/employees")
            resp.raise_for_status()
            data = resp.json()
            return data.get("employees", data) if isinstance(data, dict) else data
