import asyncio
import json
from typing import AsyncIterator

from app.models.schemas import AuthUser
from app.services import realtime
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["realtime"])


@router.get("/realtime/stream")
async def realtime_stream(user: AuthUser = Depends(get_current_user)):
    """Server-sent 'something changed' signals scoped to the caller's role. Clients refetch via normal APIs."""
    sub = realtime.subscribe(realtime.topics_for_role(user.app_role, user.id))

    async def gen() -> AsyncIterator[dict[str, str]]:
        try:
            yield {"event": "ready", "data": json.dumps({"topics": sorted(sub.topics)})}
            while True:
                try:
                    topic = await asyncio.wait_for(sub.queue.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "change", "data": json.dumps({"topic": topic})}
        finally:
            realtime.unsubscribe(sub)

    return EventSourceResponse(gen(), ping=None)
