"""Internal MongoDB document schema for users (not exposed via API)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UserDocument(BaseModel):
    """Represents a document in the 'users' MongoDB collection."""

    user_id: str               # Google sub claim — unique identifier
    email: str
    name: str
    token_data: dict           # Serialised google.oauth2.credentials.Credentials fields
    created_at: datetime
    updated_at: datetime
