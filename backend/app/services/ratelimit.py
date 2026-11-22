"""Sliding-window rate limiting. Limits for authenticated endpoints come from app_config['rate_limits']."""
import threading
import time
from collections import defaultdict, deque

from app.models.schemas import AuthUser
from app.services.appconfig import get_config, require_field
from app.services.auth import get_current_user
from app.services.db import DBProtocol, get_db
from fastapi import Depends, HTTPException, Request, status

_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def check_rate(key: str, limit: int, window_s: float = 60.0) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, int(window_s - (now - q[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry in {retry}s.",
                headers={"Retry-After": str(retry)},
            )
        q.append(now)


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()


def rate_limit(kind: str):
    """Dependency factory: kind is one of the keys inside app_config['rate_limits']."""

    def _dep(
        user: AuthUser = Depends(get_current_user),
        db: DBProtocol = Depends(get_db),
    ) -> AuthUser:
        limits = get_config(db, "rate_limits")
        check_rate(f"{kind}:{user.id}", int(require_field(limits, "rate_limits", kind)))
        return user

    return _dep


def login_rate_limit(request: Request) -> None:
    host = request.client.host if request.client else "unknown"
    check_rate(f"login:{host}", 10)
