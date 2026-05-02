"""initial

Revision ID: 0001
Revises:
Create Date: 2026-05-01

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("api_key", sa.String(256), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_accounts_api_key", "accounts", ["api_key"])

    op.create_table(
        "query_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rs_signal", sa.Text(), nullable=True),
        sa.Column("gc_signal", sa.Text(), nullable=True),
        sa.Column("qc_signal", sa.Text(), nullable=True),
        sa.Column("sa_signal", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_query_logs_account_id", "query_logs", ["account_id"])
    op.create_index("ix_query_logs_session_id", "query_logs", ["session_id"])

    op.create_table(
        "feedbacks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "query_id",
            UUID(as_uuid=True),
            sa.ForeignKey("query_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_feedbacks_query_id", "feedbacks", ["query_id"])
    op.create_index("ix_feedbacks_account_id", "feedbacks", ["account_id"])

    op.create_table(
        "doc_metas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_id", sa.String(256), nullable=False),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_doc_metas_doc_id", "doc_metas", ["doc_id"])
    op.create_index("ix_doc_metas_account_id", "doc_metas", ["account_id"])


def downgrade() -> None:
    op.drop_table("doc_metas")
    op.drop_table("feedbacks")
    op.drop_table("query_logs")
    op.drop_table("accounts")
