"""Sync employees from Mock HR Service via HRAdapter into DuckDB users table."""
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.adapters.hr import HTTPHRAdapter
from app.services.db import get_db
from app.services.hr_sync import sync_employees


async def run_sync() -> None:
    load_dotenv()
    result = await sync_employees(get_db(), HTTPHRAdapter())
    print(f"Synced employees via HRAdapter: {result}")


if __name__ == "__main__":
    asyncio.run(run_sync())
