"""Preferences router — GET and PUT user scheduling preferences."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbDep
from app.models.schedule import UserPreferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get(
    "",
    response_model=UserPreferences,
    summary="Retrieve stored scheduling preferences",
)
async def get_preferences(current_user: CurrentUser, db: DbDep):
    """
    Return the authenticated user's persisted scheduling preferences.

    Returns 404 if no preferences have been saved yet.
    """
    doc = await db.preferences.find_one(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No preferences found. Please submit preferences first.",
        )
    # Strip internal fields before returning
    doc.pop("user_id", None)
    doc.pop("updated_at", None)
    return UserPreferences(**doc)


@router.put(
    "",
    response_model=UserPreferences,
    summary="Save or update scheduling preferences",
)
async def upsert_preferences(
    preferences: UserPreferences,
    current_user: CurrentUser,
    db: DbDep,
):
    """
    Save or update the authenticated user's scheduling preferences in MongoDB.

    Preferences are persisted across sessions and returned on next load.
    """
    doc = preferences.model_dump()
    doc["user_id"] = current_user["user_id"]
    doc["updated_at"] = datetime.now(tz=timezone.utc)

    await db.preferences.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": doc},
        upsert=True,
    )
    return preferences
