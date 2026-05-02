from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cmart.db.models import DocMeta


async def insert_doc_meta(
    db: AsyncSession,
    *,
    doc_id: str,
    account_id: uuid.UUID,
    title: str,
    source_url: str | None,
    chunk_count: int,
) -> DocMeta:
    """Create and persist a new DocMeta row.

    All columns are supplied as keyword-only arguments so call sites are
    explicit and immune to positional-argument drift.
    """
    doc_meta = DocMeta(
        doc_id=doc_id,
        account_id=account_id,
        title=title,
        source_url=source_url,
        chunk_count=chunk_count,
        is_deleted=False,
    )
    db.add(doc_meta)
    await db.flush()
    await db.refresh(doc_meta)
    return doc_meta


async def get_by_doc_id(
    db: AsyncSession,
    doc_id: str,
    account_id: uuid.UUID,
) -> DocMeta | None:
    """Return the active DocMeta for (doc_id, account_id), or None."""
    result = await db.execute(
        select(DocMeta).where(
            DocMeta.doc_id == doc_id,
            DocMeta.account_id == account_id,
            DocMeta.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def upsert_doc_meta(
    db: AsyncSession,
    *,
    doc_id: str,
    account_id: uuid.UUID,
    title: str,
    source_url: str | None,
    chunk_count: int,
) -> DocMeta:
    """Insert a new DocMeta row or update an existing one in-place.

    When the document already exists (including soft-deleted rows), the row is
    updated with the new metadata and is_deleted is reset to False.  This
    supports idempotent re-ingest without leaving orphaned rows.
    """
    # Query without the is_deleted filter so we can revive soft-deleted rows
    result = await db.execute(
        select(DocMeta).where(
            DocMeta.doc_id == doc_id,
            DocMeta.account_id == account_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.title = title
        existing.source_url = source_url
        existing.chunk_count = chunk_count
        existing.is_deleted = False
        await db.flush()
        await db.refresh(existing)
        return existing

    return await insert_doc_meta(
        db,
        doc_id=doc_id,
        account_id=account_id,
        title=title,
        source_url=source_url,
        chunk_count=chunk_count,
    )


async def mark_deleted(
    db: AsyncSession,
    doc_id: str,
    account_id: uuid.UUID,
) -> bool:
    """Soft-delete a DocMeta row.

    Returns True if a row was found and marked deleted, False otherwise.
    """
    doc_meta = await get_by_doc_id(db, doc_id, account_id)
    if doc_meta is None:
        return False

    doc_meta.is_deleted = True
    await db.flush()
    return True
