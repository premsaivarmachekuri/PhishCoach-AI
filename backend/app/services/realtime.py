"""In-process pub/sub that pushes 'something changed' signals to connected clients over SSE.

Payloads carry only a topic name; clients re-fetch authoritative data through the normal
RBAC-protected endpoints, so this channel can never leak data.

Topics: metrics, campaigns, remediation, config, inbox:<user_id>
"""
import asyncio
import threading
from dataclasses import dataclass, field


@dataclass(eq=False)
class Subscriber:
    topics: frozenset[str]
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[str] = field(default_factory=lambda: asyncio.Queue(maxsize=256))


_subscribers: set[Subscriber] = set()
_lock = threading.Lock()


def subscribe(topics: set[str]) -> Subscriber:
    sub = Subscriber(topics=frozenset(topics), loop=asyncio.get_running_loop())
    with _lock:
        _subscribers.add(sub)
    return sub


def unsubscribe(sub: Subscriber) -> None:
    with _lock:
        _subscribers.discard(sub)


def _deliver(sub: Subscriber, topic: str) -> None:
    try:
        sub.queue.put_nowait(topic)
    except asyncio.QueueFull:
        # Client is far behind; a dropped signal is fine because the next one triggers a full refetch.
        pass


def publish(*topics: str) -> None:
    """Thread-safe: callable from sync (threadpool) and async endpoints."""
    with _lock:
        targets = list(_subscribers)
    for sub in targets:
        for topic in topics:
            if topic in sub.topics:
                try:
                    sub.loop.call_soon_threadsafe(_deliver, sub, topic)
                except RuntimeError:
                    # Subscriber's loop has closed; it will be removed on unsubscribe.
                    pass


def topics_for_role(app_role: str, user_id: str) -> set[str]:
    if app_role == "security_admin":
        return {"metrics", "campaigns", "remediation", "config"}
    if app_role == "hr_viewer":
        return {"metrics"}
    return {f"inbox:{user_id}"}
