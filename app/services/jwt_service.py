"""JWT creation and verification using PyJWT."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings

_ALGORITHM = "HS256"
_EXPIRY_DAYS = 7


def create_token(user_id: str, email: str, name: str) -> str:
    """Sign and return a JWT containing user identity claims."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "exp": datetime.now(tz=timezone.utc) + timedelta(days=_EXPIRY_DAYS),
        "iat": datetime.now(tz=timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """
    Validate the JWT signature and expiry.

    Returns the decoded payload dict on success, or None if invalid/expired.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
        return {
            "user_id": payload["sub"],
            "email": payload["email"],
            "name": payload["name"],
        }
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
