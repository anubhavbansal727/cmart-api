"""Integration tests for POST /ingest and DELETE /ingest/{doc_id}.

All external I/O (OpenAI embeddings, Pinecone, PostgreSQL) is mocked so these
tests run without any real infrastructure.  The FastAPI dependency injection
system is used to override get_current_account and get_db cleanly.
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from cmart.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_ACCOUNT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_FAKE_EMBEDDING = [0.0] * 1536


def _make_account() -> MagicMock:
    """Return a MagicMock that behaves like an Account ORM object.

    Using MagicMock avoids SQLAlchemy instrumentation issues when constructing
    transient model instances outside a mapped session.  The route only reads
    .id and .name, so a plain mock is sufficient.
    """
    account = MagicMock()
    account.id = _FAKE_ACCOUNT_ID
    account.name = "Test Account"
    account.api_key = "test-key-integration"
    account.is_active = True
    return account


def _make_doc_meta(doc_id: str) -> MagicMock:
    """Return a MagicMock that behaves like a DocMeta ORM object."""
    meta = MagicMock()
    meta.id = uuid.uuid4()
    meta.doc_id = doc_id
    meta.account_id = _FAKE_ACCOUNT_ID
    meta.title = "Existing Doc"
    meta.source_url = None
    meta.chunk_count = 3
    meta.is_deleted = False
    return meta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client_with_mocks(
    mocker: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with all external dependencies mocked.

    Mocked:
    - get_current_account -> returns a fake Account without hitting the DB
    - get_db             -> yields a MagicMock AsyncSession
    - OpenAIEmbeddingClient.embed_batch -> returns fake 1536-dim zero vectors
    - PineconeVectorStoreClient.upsert  -> no-op
    - PineconeVectorStoreClient.delete  -> no-op
    - doc_meta repository functions     -> controlled per-test via mocker
    """
    from cmart.api.dependencies import get_current_account, get_db

    fake_account = _make_account()

    # --- DB session mock ---
    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.execute = AsyncMock()

    async def _override_db() -> AsyncGenerator:
        yield mock_db

    async def _override_account() -> MagicMock:
        return fake_account

    app.dependency_overrides[get_current_account] = _override_account
    app.dependency_overrides[get_db] = _override_db

    # --- Patch external service calls ---
    mocker.patch(
        "cmart.api.routes.ingest._embedding_client.embed_batch",
        new=AsyncMock(side_effect=lambda texts: [[0.0] * 1536 for _ in texts]),
    )
    mocker.patch(
        "cmart.api.routes.ingest._vector_store.upsert",
        new=AsyncMock(return_value=None),
    )
    mocker.patch(
        "cmart.api.routes.ingest._vector_store.delete",
        new=AsyncMock(return_value=None),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    # Clean up overrides so other test modules are not affected
    app.dependency_overrides.pop(get_current_account, None)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# POST /ingest — happy path (plain text / markdown)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_markdown_document_returns_200(
    client_with_mocks: AsyncClient,
    mocker: MagicMock,
) -> None:
    """POST /ingest with a URL must return 200 with chunk_count > 0."""
    mocker.patch(
        "cmart.api.routes.ingest.get_by_doc_id",
        new=AsyncMock(return_value=None),
    )
    mocker.patch(
        "cmart.api.routes.ingest.upsert_doc_meta",
        new=AsyncMock(return_value=_make_doc_meta("md-doc-1")),
    )
    fetched_content = "# Overview\n\n" + ("CMART resolves support queries autonomously. " * 30)
    mocker.patch(
        "cmart.api.routes.ingest.fetch_text",
        new=AsyncMock(return_value=fetched_content),
    )

    response = await client_with_mocks.post(
        "/ingest",
        json={
            "documents": [
                {
                    "doc_id": "md-doc-1",
                    "title": "Overview",
                    "url": "https://docs.example.com/overview",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["ingested"]) == 1
    assert body["ingested"][0]["doc_id"] == "md-doc-1"
    assert body["ingested"][0]["chunk_count"] > 0
    assert body["ingested"][0]["status"] == "ok"
    assert body["failed"] == []


# ---------------------------------------------------------------------------
# POST /ingest — HTML document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_html_document_strips_tags(
    client_with_mocks: AsyncClient,
    mocker: MagicMock,
) -> None:
    """POST /ingest with an HTML document must succeed; HTML tags stripped before chunking."""
    ingested_chunks: list[list[dict]] = []

    async def _capture_upsert(namespace: str, vectors: list[dict]) -> None:
        ingested_chunks.append(vectors)

    mocker.patch("cmart.api.routes.ingest._vector_store.upsert", new=_capture_upsert)

    mocker.patch(
        "cmart.api.routes.ingest.get_by_doc_id",
        new=AsyncMock(return_value=None),
    )
    mocker.patch(
        "cmart.api.routes.ingest.upsert_doc_meta",
        new=AsyncMock(return_value=_make_doc_meta("html-doc-1")),
    )

    mocker.patch(
        "cmart.api.routes.ingest.fetch_text",
        new=AsyncMock(
            return_value=(
                "Reset Password\n\nGo to Settings and click Reset Password.\n\n"
                "You will receive an email with a reset link valid for 24 hours."
            )
        ),
    )

    response = await client_with_mocks.post(
        "/ingest",
        json={
            "documents": [
                {
                    "doc_id": "html-doc-1",
                    "title": "Reset Password",
                    "url": "https://docs.example.com/reset-password",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ingested"][0]["doc_id"] == "html-doc-1"
    assert body["ingested"][0]["chunk_count"] >= 1

    # Verify that HTML tags were stripped from the vector metadata
    if ingested_chunks:
        for vector in ingested_chunks[0]:
            content_in_metadata = vector["metadata"]["content"]
            assert "<html" not in content_in_metadata
            assert "<p>" not in content_in_metadata


# ---------------------------------------------------------------------------
# POST /ingest — authentication failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_without_auth_returns_401() -> None:
    """POST /ingest without an Authorization header must return 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        response = await ac.post(
            "/ingest",
            json={
                "documents": [
                    {
                        "doc_id": "unauth-doc",
                        "title": "Unauth",
                        "url": "https://docs.example.com/unauth",
                    }
                ]
            },
        )

    assert response.status_code == 401
    body = response.json()
    assert "error" in body


# ---------------------------------------------------------------------------
# POST /ingest — per-document error does not abort batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_batch_continues_after_per_document_failure(
    client_with_mocks: AsyncClient,
    mocker: MagicMock,
) -> None:
    """A failure on one document must not abort the remaining documents in the batch."""
    call_count = 0

    async def _flaky_upsert(namespace: str, vectors: list[dict]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Simulated Pinecone timeout")

    mocker.patch("cmart.api.routes.ingest._vector_store.upsert", new=_flaky_upsert)
    mocker.patch(
        "cmart.api.routes.ingest.get_by_doc_id",
        new=AsyncMock(return_value=None),
    )
    mocker.patch(
        "cmart.api.routes.ingest.upsert_doc_meta",
        new=AsyncMock(return_value=_make_doc_meta("ok-doc")),
    )
    mocker.patch(
        "cmart.api.routes.ingest.fetch_text",
        new=AsyncMock(side_effect=["Content A.", "Content B."]),
    )

    response = await client_with_mocks.post(
        "/ingest",
        json={
            "documents": [
                {"doc_id": "fail-doc", "title": "Fail", "url": "https://docs.example.com/a"},
                {"doc_id": "ok-doc", "title": "OK", "url": "https://docs.example.com/b"},
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["failed"]) == 1
    assert body["failed"][0]["doc_id"] == "fail-doc"
    assert len(body["ingested"]) == 1
    assert body["ingested"][0]["doc_id"] == "ok-doc"


# ---------------------------------------------------------------------------
# DELETE /ingest/{doc_id} — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_existing_doc_returns_200(
    client_with_mocks: AsyncClient,
    mocker: MagicMock,
) -> None:
    """DELETE /ingest/{doc_id} on an existing document must return 200 with deleted=True."""
    mocker.patch(
        "cmart.api.routes.ingest.get_by_doc_id",
        new=AsyncMock(return_value=_make_doc_meta("existing-doc")),
    )
    mocker.patch(
        "cmart.db.repositories.doc_meta.mark_deleted",
        new=AsyncMock(return_value=True),
    )

    response = await client_with_mocks.delete("/ingest/existing-doc")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == "existing-doc"
    assert body["deleted"] is True


# ---------------------------------------------------------------------------
# DELETE /ingest/{doc_id} — not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_nonexistent_doc_returns_404(
    client_with_mocks: AsyncClient,
    mocker: MagicMock,
) -> None:
    """DELETE /ingest/{doc_id} on a non-existent document must return 404."""
    mocker.patch(
        "cmart.api.routes.ingest.get_by_doc_id",
        new=AsyncMock(return_value=None),  # document not found
    )

    response = await client_with_mocks.delete("/ingest/ghost-doc")

    assert response.status_code == 404
    body = response.json()
    assert "error" in body


# ---------------------------------------------------------------------------
# POST /ingest — re-ingest existing document (idempotency)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reingest_existing_doc_deletes_old_vectors_first(
    client_with_mocks: AsyncClient,
    mocker: MagicMock,
) -> None:
    """Re-ingesting an existing doc_id must delete old vectors before upserting new ones."""
    delete_mock = AsyncMock(return_value=None)
    mocker.patch("cmart.api.routes.ingest._vector_store.delete", new=delete_mock)
    mocker.patch(
        "cmart.api.routes.ingest.get_by_doc_id",
        new=AsyncMock(return_value=_make_doc_meta("re-ingest-doc")),  # doc exists
    )
    mocker.patch(
        "cmart.api.routes.ingest.upsert_doc_meta",
        new=AsyncMock(return_value=_make_doc_meta("re-ingest-doc")),
    )

    mocker.patch(
        "cmart.api.routes.ingest.fetch_text",
        new=AsyncMock(return_value="Updated content for the document."),
    )

    response = await client_with_mocks.post(
        "/ingest",
        json={
            "documents": [
                {
                    "doc_id": "re-ingest-doc",
                    "title": "Updated Doc",
                    "url": "https://docs.example.com/updated",
                }
            ]
        },
    )

    assert response.status_code == 200
    # delete must have been called for the old vectors
    delete_mock.assert_awaited_once_with(
        namespace=str(_FAKE_ACCOUNT_ID),
        doc_id="re-ingest-doc",
    )
