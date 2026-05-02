from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class FeedbackRating(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"


class FeedbackRequest(BaseModel):
    query_id: uuid.UUID
    rating: FeedbackRating
    agent_id: str | None = None
    note: str | None = None


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    query_id: uuid.UUID
    rating: FeedbackRating
    created_at: datetime
