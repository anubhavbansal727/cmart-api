from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cmart.db.engine import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Account(Base):
    """Tenant account — one row per API consumer."""

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    api_key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    query_logs: Mapped[list[QueryLog]] = relationship("QueryLog", back_populates="account")
    feedbacks: Mapped[list[Feedback]] = relationship("Feedback", back_populates="account")
    doc_metas: Mapped[list[DocMeta]] = relationship("DocMeta", back_populates="account")


class QueryLog(Base):
    """Audit log for every query processed by the pipeline."""

    __tablename__ = "query_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Pipeline signal columns — nullable because they are populated as stages run
    rs_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    gc_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    qc_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    sa_signal: Mapped[str | None] = mapped_column(Text, nullable=True)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="query_logs")
    feedback: Mapped[Feedback | None] = relationship(
        "Feedback", back_populates="query_log", uselist=False
    )


class Feedback(Base):
    """Human-in-the-loop feedback on a pipeline decision."""

    __tablename__ = "feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("query_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Allowed values: "correct" | "incorrect" | "partial"
    rating: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="feedbacks")
    query_log: Mapped[QueryLog] = relationship("QueryLog", back_populates="feedback")


class DocMeta(Base):
    """Metadata for an ingested document, scoped to an account."""

    __tablename__ = "doc_metas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # doc_id is the caller-supplied identifier; unique per (doc_id, account_id)
    doc_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    account: Mapped[Account] = relationship("Account", back_populates="doc_metas")
