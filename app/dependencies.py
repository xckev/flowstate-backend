"""Shared FastAPI dependencies — injected via Depends()."""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.services.jwt_service import decode_token

_bearer = HTTPBearer()


def get_db() -> AsyncIOMotorDatabase:
    """Dependency that returns the active MongoDB database handle."""
    return get_database()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """Validate the Bearer JWT and return the decoded payload {user_id, email, name}."""
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


# Convenience type aliases for use in route signatures
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
CurrentUser = Annotated[dict, Depends(get_current_user)]
