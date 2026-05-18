from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class IngestDocument(BaseModel):
    """A single document submitted for ingestion."""

    doc_id: str = Field(..., description="Caller-supplied stable identifier for this document.")
    title: str = Field(..., description="Human-readable document title.")
    content: str | None = Field(
        default=None, description="Raw document content: plain text, markdown, or HTML."
    )
    url: str | None = Field(
        default=None, description="URL to fetch content from. Mutually exclusive with content."
    )
    source_url: str | None = Field(
        default=None, description="Canonical URL for attribution. Defaults to url when url is used."
    )

    @model_validator(mode="after")
    def _require_exactly_one_source(self) -> IngestDocument:
        has_content = bool(self.content and self.content.strip())
        has_url = bool(self.url and self.url.strip())
        if has_content == has_url:
            raise ValueError("Provide either 'content' or 'url', not both and not neither.")
        return self


class IngestRequest(BaseModel):
    """Request body for POST /ingest."""

    documents: list[IngestDocument] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Between 1 and 50 documents to ingest in a single request.",
    )


class IngestResponse(BaseModel):
    """Response body for POST /ingest."""

    ingested: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Successfully ingested documents. Each entry: {doc_id, chunk_count, status}.",
    )
    failed: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Documents that failed ingestion. Each entry: {doc_id, error}.",
    )


class DeleteResponse(BaseModel):
    """Response body for DELETE /ingest/{doc_id}."""

    doc_id: str = Field(..., description="The document identifier that was deleted.")
    deleted: bool = Field(..., description="True when the document was successfully removed.")
