"""Google OAuth 2.0 flow and credential management backed by MongoDB."""
from __future__ import annotations

from datetime import datetime, timezone

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings

# Scopes requested from Google
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar",
]


def _build_client_config(settings) -> dict:
    """Construct the client_config dict expected by google_auth_oauthlib."""
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.oauth_redirect_uri],
        }
    }


def get_google_auth_flow() -> Flow:
    """Build and return a configured OAuth 2.0 Flow object."""
    settings = get_settings()
    flow = Flow.from_client_config(
        _build_client_config(settings),
        scopes=SCOPES,
        redirect_uri=settings.oauth_redirect_uri,
    )
    return flow


async def get_authorization_url(db: AsyncIOMotorDatabase) -> tuple[str, str]:
    """
    Generate the Google OAuth authorization URL and persist the PKCE state to MongoDB.

    google_auth_oauthlib adds a PKCE code_challenge to the URL automatically.
    The matching code_verifier is stored in the oauth_states MongoDB collection so it
    survives server reloads, restarts, and multi-process deployments.

    Returns:
        (authorization_url, state)
    """
    flow = get_google_auth_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # ensures refresh_token is always returned
    )
    # requests_oauthlib stores the generated code_verifier on the session after
    # authorization_url() is called (only present when PKCE is active).
    code_verifier = getattr(flow.oauth2session, "_code_verifier", None)

    await db.oauth_states.replace_one(
        {"state": state},
        {
            "state": state,
            "code_verifier": code_verifier,
            "created_at": datetime.now(tz=timezone.utc),
        },
        upsert=True,
    )
    return authorization_url, state


async def exchange_code_for_credentials(
    code: str, state: str, db: AsyncIOMotorDatabase
) -> Credentials:
    """
    Exchange an authorization code for OAuth credentials.

    Retrieves the PKCE code_verifier from MongoDB, injects it back into a fresh
    Flow, then performs the token exchange. The state document is deleted after use.
    """
    doc = await db.oauth_states.find_one_and_delete({"state": state})
    code_verifier = doc.get("code_verifier") if doc else None

    flow = get_google_auth_flow()
    if code_verifier:
        # Restore the verifier so fetch_token() includes it in the POST body
        flow.oauth2session._code_verifier = code_verifier
    flow.fetch_token(code=code)
    return flow.credentials


def credentials_to_dict(creds: Credentials) -> dict:
    """Serialise a Credentials object to a storable dict."""
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }


def credentials_from_dict(token_data: dict) -> Credentials:
    """Reconstruct a Credentials object from a stored dict."""
    return Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes"),
    )


async def save_credentials(
    user_id: str,
    email: str,
    name: str,
    credentials: Credentials,
    db: AsyncIOMotorDatabase,
) -> None:
    """Upsert user document with latest credentials into MongoDB."""
    now = datetime.now(tz=timezone.utc)
    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "email": email,
                "name": name,
                "token_data": credentials_to_dict(credentials),
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def get_credentials(user_id: str, db: AsyncIOMotorDatabase) -> Credentials | None:
    """
    Load credentials from MongoDB, refresh if expired, and persist the refreshed token.

    Returns None if no credentials exist for the user.
    """
    doc = await db.users.find_one({"user_id": user_id})
    if not doc:
        return None

    creds = credentials_from_dict(doc["token_data"])

    # Refresh if expired or close to expiry
    if creds.expired and creds.refresh_token:
        request = google.auth.transport.requests.Request()
        creds.refresh(request)
        # Persist the refreshed token
        await db.users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "token_data": credentials_to_dict(creds),
                    "updated_at": datetime.now(tz=timezone.utc),
                }
            },
        )

    return creds


async def delete_credentials(user_id: str, db: AsyncIOMotorDatabase) -> None:
    """Remove the user's OAuth document from MongoDB."""
    await db.users.delete_one({"user_id": user_id})
