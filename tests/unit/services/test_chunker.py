"""Unit tests for DocumentChunker.

These tests are fully self-contained and require no external services.
"""

from __future__ import annotations

import pytest

from cmart.services.chunker import DocumentChunker

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def chunker() -> DocumentChunker:
    """Default chunker with small chunk_size to make splitting predictable."""
    return DocumentChunker(chunk_size=100, chunk_overlap=10)


@pytest.fixture()
def default_chunker() -> DocumentChunker:
    """Chunker with production defaults (512 / 64)."""
    return DocumentChunker()


# ---------------------------------------------------------------------------
# Plain text chunking
# ---------------------------------------------------------------------------


def test_long_text_splits_into_multiple_chunks(chunker: DocumentChunker) -> None:
    """Content longer than chunk_size must be split into more than one chunk."""
    # 20 sentences of ~30 chars each → well above chunk_size=100
    content = " ".join([f"This is sentence number {i}." for i in range(20)])

    chunks = chunker.chunk(
        content=content,
        doc_id="doc-001",
        title="Test Doc",
        source_url="https://example.com/doc",
        account_id="acc-1",
    )

    assert len(chunks) > 1


def test_chunk_metadata_fields_are_correct(chunker: DocumentChunker) -> None:
    """Every chunk must carry the expected metadata fields with correct values."""
    content = "word " * 200  # 1000 chars, forces multiple chunks with chunk_size=100

    chunks = chunker.chunk(
        content=content,
        doc_id="doc-002",
        title="Metadata Test",
        source_url="https://example.com/meta",
        account_id="acc-2",
    )

    for i, chunk in enumerate(chunks):
        assert chunk["doc_id"] == "doc-002"
        assert chunk["title"] == "Metadata Test"
        assert chunk["source_url"] == "https://example.com/meta"
        assert chunk["account_id"] == "acc-2"
        assert chunk["chunk_index"] == i
        assert chunk["id"] == f"doc-002_chunk_{i}"
        assert isinstance(chunk["content"], str)
        assert len(chunk["content"]) > 0


# ---------------------------------------------------------------------------
# HTML detection and stripping
# ---------------------------------------------------------------------------


def test_html_content_is_stripped_before_chunking(default_chunker: DocumentChunker) -> None:
    """HTML documents must be converted to plain text before chunking.

    The raw HTML tags (<p>, <html>, etc.) must not appear in any chunk's content.
    """
    html_content = """
    <html>
      <body>
        <h1>Getting Started</h1>
        <p>CMART is an API-first AI support agent for B2B SaaS companies.</p>
        <p>It resolves support queries using retrieval-augmented generation.</p>
        <div>
          <p>The system uses four confidence signals to make routing decisions.</p>
        </div>
      </body>
    </html>
    """

    chunks = default_chunker.chunk(
        content=html_content,
        doc_id="html-doc",
        title="Getting Started",
        source_url=None,
        account_id="acc-3",
    )

    assert len(chunks) >= 1
    full_text = " ".join(c["content"] for c in chunks)

    # HTML tags must not appear in the extracted content
    assert "<html" not in full_text
    assert "<body" not in full_text
    assert "<p>" not in full_text
    assert "<div" not in full_text

    # Meaningful text must be preserved
    assert "CMART" in full_text or "Getting Started" in full_text


def test_html_with_body_tag_triggers_conversion(chunker: DocumentChunker) -> None:
    """Content containing <body> must be treated as HTML."""
    html = "<body><p>Hello world.</p></body>"

    chunks = chunker.chunk(
        content=html,
        doc_id="body-doc",
        title="Body Tag Test",
        source_url=None,
        account_id="acc-4",
    )

    full_text = " ".join(c["content"] for c in chunks)
    assert "<body" not in full_text
    assert "Hello world" in full_text


def test_plain_text_is_not_treated_as_html(chunker: DocumentChunker) -> None:
    """Plain text without HTML markers must pass through as-is."""
    plain = "This is plain text with no HTML. " * 10

    chunks = chunker.chunk(
        content=plain,
        doc_id="plain-doc",
        title="Plain Text",
        source_url=None,
        account_id="acc-5",
    )

    assert len(chunks) >= 1
    # The original words must survive unchanged
    assert "plain text" in chunks[0]["content"]


# ---------------------------------------------------------------------------
# Short content — single chunk
# ---------------------------------------------------------------------------


def test_short_content_returns_exactly_one_chunk(default_chunker: DocumentChunker) -> None:
    """Content shorter than chunk_size must produce exactly one chunk."""
    short_content = "This is a short document."

    chunks = default_chunker.chunk(
        content=short_content,
        doc_id="short-doc",
        title="Short Doc",
        source_url=None,
        account_id="acc-6",
    )

    assert len(chunks) == 1
    assert chunks[0]["content"] == short_content
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["id"] == "short-doc_chunk_0"


# ---------------------------------------------------------------------------
# Chunk ID uniqueness
# ---------------------------------------------------------------------------


def test_chunk_ids_are_unique_per_doc_id(chunker: DocumentChunker) -> None:
    """All chunk IDs within a single document must be unique."""
    content = "sentence number one. " * 50  # enough to produce many chunks

    chunks = chunker.chunk(
        content=content,
        doc_id="unique-id-doc",
        title="Uniqueness Test",
        source_url=None,
        account_id="acc-7",
    )

    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids)), "Duplicate chunk IDs detected"


def test_chunk_ids_from_different_docs_do_not_collide() -> None:
    """Chunks from different documents must not share IDs even with identical content."""
    chunker = DocumentChunker(chunk_size=50, chunk_overlap=5)
    content = "same content for both documents. " * 10

    chunks_a = chunker.chunk(
        content=content,
        doc_id="doc-a",
        title="Doc A",
        source_url=None,
        account_id="acc-8",
    )
    chunks_b = chunker.chunk(
        content=content,
        doc_id="doc-b",
        title="Doc B",
        source_url=None,
        account_id="acc-8",
    )

    ids_a = {c["id"] for c in chunks_a}
    ids_b = {c["id"] for c in chunks_b}
    assert ids_a.isdisjoint(ids_b), "Chunk IDs collided across documents"


# ---------------------------------------------------------------------------
# source_url fallback
# ---------------------------------------------------------------------------


def test_none_source_url_stored_as_empty_string(default_chunker: DocumentChunker) -> None:
    """When source_url is None it must be stored as an empty string in chunk metadata."""
    chunks = default_chunker.chunk(
        content="Some content here.",
        doc_id="no-url-doc",
        title="No URL",
        source_url=None,
        account_id="acc-9",
    )

    for chunk in chunks:
        assert chunk["source_url"] == ""
