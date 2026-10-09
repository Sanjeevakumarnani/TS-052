import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from . import db
from .config import ADMIN_BOOTSTRAP_PASSWORD, ADMIN_BOOTSTRAP_USERNAME, SESSION_SECRET

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 100,000 iterations and a random salt."""
    salt = secrets.token_bytes(16)
    iterations = 100_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plain password against a stored PBKDF2-HMAC-SHA256 string."""
    try:
        algorithm, iter_str, salt_hex, derived_hex = hashed.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(derived_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding and padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def create_token(user_id: str, role: str, username: str, expires_in_seconds: int = 86400 * 7) -> str:
    """Generate a tamper-evident signed token using HMAC-SHA256."""
    payload = {
        "sub": user_id,
        "role": role,
        "username": username,
        "exp": int(time.time()) + expires_in_seconds,
        "nonce": secrets.token_hex(4),
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64_encode(payload_json)
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = _b64_encode(signature)
    return f"{payload_b64}.{sig_b64}"


def decode_token(token: str) -> Optional[dict]:
    """Verify and decode a signed token."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        expected_sig = hmac.new(SESSION_SECRET.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
        actual_sig = _b64_decode(sig_b64)
        if not secrets.compare_digest(actual_sig, expected_sig):
            return None
        payload = json.loads(_b64_decode(payload_b64).decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> Optional[dict]:
    """Return the authenticated user dict if a valid token is provided, else None."""
    if not credentials or not credentials.credentials:
        return None
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        return None
    user = db.get_user_by_id(payload.get("sub"))
    if not user or user.get("status") != "active":
        return None
    return user


def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> dict:
    """Dependency that enforces a valid authenticated user."""
    user = get_optional_user(credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required or token expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that enforces administrator role."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required for this action.",
        )
    return user


def require_resident(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that enforces resident (or admin acting as resident) role."""
    if user.get("role") not in ("resident", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Resident membership required.",
        )
    return user


def bootstrap_admin():
    """Create initial administrator and demo resident accounts if configured or missing."""
    # 1. Environment-driven bootstrap if provided
    if ADMIN_BOOTSTRAP_USERNAME and ADMIN_BOOTSTRAP_PASSWORD:
        existing = db.get_user_by_username(ADMIN_BOOTSTRAP_USERNAME)
        if not existing:
            pwd_hash = hash_password(ADMIN_BOOTSTRAP_PASSWORD)
            db.create_user(
                username=ADMIN_BOOTSTRAP_USERNAME,
                password_hash=pwd_hash,
                role="admin",
                display_name="System Administrator (Bootstrap)",
            )

    # 2. Seed standard demo admin account
    if not db.get_user_by_username("admin"):
        db.create_user(
            username="admin",
            password_hash=hash_password("admin123"),
            role="admin",
            display_name="Demo Administrator",
        )

    # 3. Seed standard demo resident/citizen account
    if not db.get_user_by_username("citizen"):
        db.create_user(
            username="citizen",
            password_hash=hash_password("citizen123"),
            role="resident",
            display_name="Demo Resident Citizen",
        )


