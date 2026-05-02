from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel


class RSSignal(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


class QCSignal(str, Enum):
    CLEAR = "CLEAR"
    AMBIGUOUS = "AMBIGUOUS"
    INCOMPLETE = "INCOMPLETE"


class GCSignal(str, Enum):
    FULLY_SUPPORTED = "FULLY_SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class SASignal(str, Enum):
    AGREES = "AGREES"
    PARTIAL = "PARTIAL"
    CONFLICT = "CONFLICT"


# ---------------------------------------------------------------------------
# Pydantic models — used as structured output schemas for LLM calls
# ---------------------------------------------------------------------------

class AnalysisResult(BaseModel):
    qc: QCSignal
    clarification_question: str | None = None


class GroundingResult(BaseModel):
    gc: GCSignal
    unsupported_claims: list[str] = []


class AgreementResult(BaseModel):
    sa: SASignal
    conflict_summary: str | None = None


# ---------------------------------------------------------------------------
# Dataclasses — internal pipeline DTOs
# ---------------------------------------------------------------------------

@dataclass
class RetrievedDoc:
    chunk_id: str
    doc_id: str
    content: str
    score: float
    title: str | None = None
    source_url: str | None = None


@dataclass
class RetrievalResult:
    docs: list[RetrievedDoc]
    rs_signal: RSSignal
    top_score: float
    retrieval_failed: bool = False


@dataclass
class GenerationResult:
    answer: str


@dataclass
class ValidationResult:
    gc: GCSignal
    sa: SASignal
    unsupported_claims: list[str] = field(default_factory=list)
    conflict_summary: str | None = None


@dataclass
class DecisionResult:
    decision: str  # "answer" | "clarify" | "escalate"
    reason: str


@dataclass
class PipelineContext:
    query: str
    user_id: str
    account_id: str
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    clarify_rounds: int = 0

    # Populated as pipeline stages execute
    analysis: AnalysisResult | None = None
    retrieval: RetrievalResult | None = None
    generation: GenerationResult | None = None
    validation: ValidationResult | None = None
    decision_result: DecisionResult | None = None
    escalation_context: dict[str, Any] | None = None

    # Per-stage latency in ms
    stage_latencies: dict[str, int] = field(default_factory=dict)
