from app.models.schemas import AuthUser, PublicUser
from app.services.auth import (
    DUMMY_HASH,
    create_access_token,
    get_current_user,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.services.db import DBProtocol, get_db
from app.services.ratelimit import login_rate_limit
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/login", dependencies=[Depends(login_rate_limit)])
def login(payload: LoginRequest, db: DBProtocol = Depends(get_db)) -> dict:
    accounts = db.select("auth_accounts", filters={"email": payload.email.strip().lower()}, limit=1)
    stored = accounts[0]["password_hash"] if accounts else DUMMY_HASH
    valid = verify_password(payload.password, stored)
    if not accounts or not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    auth_uid = accounts[0]["id"]
    users = db.select("users", filters={"auth_user_id": auth_uid}, limit=1)
    if not users:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not enrolled in PhishCoach AI",
        )
    if needs_rehash(stored):
        db.update("auth_accounts", {"password_hash": hash_password(payload.password)}, {"id": auth_uid})
    token = create_access_token(auth_uid)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": PublicUser(**users[0]).model_dump(mode="json"),
    }


@router.get("/auth/me", response_model=PublicUser)
def get_me(user: AuthUser = Depends(get_current_user)) -> PublicUser:
    return PublicUser(**user.model_dump())


@router.get("/demo/personas")
def list_personas(db: DBProtocol = Depends(get_db)) -> list[dict]:
    """Real enrolled users (anonymised ids only) for the role switcher. No hardcoded data."""
    rows = db.select("users", filters={"is_synthetic": False}, limit=200) or db.select("users", limit=200)
    return [
        {k: r.get(k) for k in ("id", "anon_id", "app_role", "arm", "department", "role_name")}
        for r in rows
    ]


@router.get("/demo/llm")
def llm_status(db: DBProtocol = Depends(get_db)) -> dict:
    """Active model chain and whether the most recent successful call used a fallback."""
    from app.services.config import get_settings

    st = get_settings()
    chain = [st.model_chat] + [m.strip() for m in st.model_fallbacks.split(",") if m.strip()]
    last = db.select("llm_calls", filters={"status": "ok"}, order="ts", desc=True, limit=1)
    used = last[0]["model"] if last else None
    return {"chain": chain, "primary": chain[0], "last_used": used, "fallback_active": bool(used and used != chain[0])}
