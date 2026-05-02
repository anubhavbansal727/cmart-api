from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    ANSWER = "answer"
    CLARIFY = "clarify"
    ESCALATE = "escalate"


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    user_id: str
    account_id: str
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievedDoc(BaseModel):
    chunk_id: str
    doc_id: str
    content: str
    score: float
    title: str | None = None
    source_url: str | None = None


class QueryResponse(BaseModel):
    decision: DecisionType
    answer: str | None = None
    clarification_question: str | None = None
    session_id: str | None = None
    escalation_context: dict[str, Any] | None = None
    sources: list[RetrievedDoc] = Field(default_factory=list)
    reason: str
    latency_ms: int
