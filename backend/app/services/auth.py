import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from app.models.schemas import AuthUser
from app.services.config import get_settings
from app.services.db import DBProtocol, get_db
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)

PBKDF2_ITERATIONS = 600_000
LEGACY_ITERATIONS = 100_000
SCHEME = "pbkdf2_sha256"


def _pbkdf2(password: str, salt: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    return f"{SCHEME}${PBKDF2_ITERATIONS}${salt}${_pbkdf2(password, salt, PBKDF2_ITERATIONS)}"


def verify_password(password: str, stored_hash: str) -> bool:
    parts = stored_hash.split("$")
    if len(parts) == 4 and parts[0] == SCHEME:
        try:
            iterations = int(parts[1])
        except ValueError:
            return False
        return hmac.compare_digest(_pbkdf2(password, parts[2], iterations), parts[3])
    if len(parts) == 2:  # legacy "salt$digest" (100k iterations)
        return hmac.compare_digest(_pbkdf2(password, parts[0], LEGACY_ITERATIONS), parts[1])
    return False


def needs_rehash(stored_hash: str) -> bool:
    return not stored_hash.startswith(f"{SCHEME}${PBKDF2_ITERATIONS}$")


# Used to equalise response time when the account does not exist (avoids user enumeration by timing).
DUMMY_HASH = hash_password("not-a-real-password", salt="0" * 32)


def create_access_token(auth_user_id: str, expires_hours: int = 12) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": auth_user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm="HS256")


def _decode_jwt(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.effective_jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"], "verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
        ) from exc


VALID_ROLES = ("employee", "security_admin", "hr_viewer")


def _persona_from_headers(db: DBProtocol, role: str, user_id: str | None) -> AuthUser:
    """Role-switcher identity: resolve a REAL enrolled user for the requested role (no login screen)."""
    if role not in VALID_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role '{role}'")
    if user_id:
        rows = db.select("users", filters={"id": user_id, "app_role": role}, limit=1)
    else:
        rows = db.select("users", filters={"app_role": role}, limit=1)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No enrolled '{role}' user found. Run tools/create_demo_users.py.",
        )
    row = dict(rows[0])
    row["auth_user_id"] = row.get("auth_user_id") or row["id"]
    return AuthUser(**row)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: DBProtocol = Depends(get_db),
    x_role: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> AuthUser:
    if (not creds or not creds.credentials) and x_role:
        return _persona_from_headers(db, x_role, x_user_id)
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Role header",
        )
    payload = _decode_jwt(creds.credentials)
    auth_uid = payload["sub"]
    rows = db.select("users", filters={"auth_user_id": auth_uid}, limit=1)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not enrolled in PhishCoach AI",
        )
    return AuthUser(**rows[0])


def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if user.app_role != "security_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security admin role required",
        )
    return user


def require_hr_or_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if user.app_role not in ("hr_viewer", "security_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HR viewer or security admin role required",
        )
    return user
