from __future__ import annotations

from typing import Any

import html2text
from langchain_text_splitters import RecursiveCharacterTextSplitter

# HTML tag markers used to detect HTML content
_HTML_MARKERS = ("<html", "<body", "<div", "<p")


def _is_html(content: str) -> bool:
    """Return True if content appears to be HTML."""
    lowered = content.lower()
    return any(marker in lowered for marker in _HTML_MARKERS)


class DocumentChunker:
    """Splits document content into overlapping chunks suitable for embedding.

    HTML is converted to clean markdown via html2text before splitting.
    Only plain text, markdown, and HTML are supported — no PDF.

    Each returned chunk dict carries all metadata fields needed to build a
    Pinecone vector and reconstruct source attribution at query time.
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,  # character-based, not token-based (MVP)
        )

    def chunk(
        self,
        content: str,
        doc_id: str,
        title: str,
        source_url: str | None,
        account_id: str,
    ) -> list[dict[str, Any]]:
        """Split *content* into chunks and attach document metadata.

        Returns a list of dicts, one per chunk:
        {
            "id": "<doc_id>_chunk_<i>",
            "doc_id": str,
            "chunk_index": int,
            "content": str,
            "title": str,
            "source_url": str,
            "account_id": str,
        }
        """
        # Strip HTML to markdown when necessary
        if _is_html(content):
            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.ignore_images = True
            content = converter.handle(content)

        texts = self._splitter.split_text(content)

        return [
            {
                "id": f"{doc_id}_chunk_{i}",
                "doc_id": doc_id,
                "chunk_index": i,
                "content": text,
                "title": title,
                "source_url": source_url or "",
                "account_id": account_id,
            }
            for i, text in enumerate(texts)
        ]
