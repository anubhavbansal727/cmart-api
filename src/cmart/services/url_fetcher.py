from __future__ import annotations

import html2text
import httpx

_TIMEOUT = 15.0
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB — guard against huge pages
_HEADERS = {"User-Agent": "CMART-Ingest/1.0"}

_converter = html2text.HTML2Text()
_converter.ignore_links = False
_converter.ignore_images = True
_converter.body_width = 0


async def fetch_text(url: str) -> str:
    """Fetch a URL and return its content as plain text.

    HTML is converted to markdown-flavoured plain text via html2text.
    Plain-text responses are returned as-is.

    Raises httpx.HTTPError on network or HTTP errors.
    Raises ValueError if the response exceeds 5 MB.
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=_TIMEOUT) as client:
        response = await client.get(url, headers=_HEADERS)
        response.raise_for_status()

        if len(response.content) > _MAX_BYTES:
            raise ValueError(f"Response from {url} exceeds 5 MB limit.")

        content_type = response.headers.get("content-type", "")
        if "html" in content_type:
            return _converter.handle(response.text).strip()

        return response.text.strip()
