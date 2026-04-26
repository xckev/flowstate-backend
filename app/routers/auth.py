"""Auth router — Google OAuth 2.0 login, callback, status, and logout."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.dependencies import CurrentUser, DbDep
from app.services import auth_service
from app.services.jwt_service import create_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login", summary="Get Google OAuth authorization URL")
async def login(db: DbDep, redirect_uri: str | None = Query(default=None)):
    """
    Generate and return the Google OAuth authorization URL.

    The frontend should redirect the user to this URL to begin the OAuth flow.
    Pass redirect_uri to override the default (used by Chrome extensions).
    """
    authorization_url, state = await auth_service.get_authorization_url(
        db, redirect_uri=redirect_uri
    )
    return {"authorization_url": authorization_url, "state": state}


@router.get("/callback", summary="OAuth 2.0 callback handler")
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    db: DbDep = None,
):
    """
    Handle the OAuth callback from Google.

    Exchanges the authorization code for credentials, fetches the user's
    Google profile, stores credentials in MongoDB, and returns a signed JWT.
    """
    try:
        credentials = await auth_service.exchange_code_for_credentials(code, state, db)
    except Exception as exc:
        logger.error("OAuth code exchange failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code.",
        )

    # Fetch user info from Google
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch user info from Google.",
            )
        user_info = resp.json()

    user_id: str = user_info["sub"]
    email: str = user_info.get("email", "")
    name: str = user_info.get("name", "")

    # Persist credentials to MongoDB
    await auth_service.save_credentials(user_id, email, name, credentials, db)

    # Issue a signed JWT
    token = create_token(user_id, email, name)
    return {"token": token, "email": email, "name": name}


@router.get("/status", summary="Check authentication status")
async def auth_status(current_user: CurrentUser):
    """
    Validate the Bearer JWT and return the user's identity.

    Returns 401 if the token is missing, invalid, or expired.
    """
    return {
        "authenticated": True,
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "name": current_user["name"],
    }


@router.post("/logout", summary="Revoke credentials and log out")
async def logout(current_user: CurrentUser, db: DbDep):
    """
    Revoke the user's stored OAuth token and remove them from MongoDB.

    The frontend should discard its JWT after this call.
    """
    await auth_service.delete_credentials(current_user["user_id"], db)
    return {"message": "Logged out successfully."}
