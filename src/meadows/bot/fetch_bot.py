#!/usr/bin/env python3
"""Fetch Bot — Download URLs and convert to markdown.

BUSINESS RULE (MEADOWS §5 line 130): this bot proves that a bot with
heavy dependencies (httpx, trafilatura, beautifulsoup4) and async HTTP
works through the SDK. It extracts URLs from messages, fetches them
concurrently, and returns the content as markdown.

BUSINESS RULE (MEADOWS §7 line 152): the monolith's fetch_bot was 1000+
lines with cookie-wall detection, AMP fallback, and BeautifulSoup
heuristics. This version keeps the core behavior but organizes it as
a clean SDK bot with no sys.path hacks.

Usage:
    @fetch https://example.com                    - Fetch single URL
    @fetch https://url1 https://url2             - Fetch multiple URLs
    @fetch --all                                  - Fetch URLs from thread context
    (reply to message with URL) @fetch           - Fetch URL from quoted message
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, ClassVar
from urllib.parse import urlparse

import httpx

from meadows.bot import BaseBot
from meadows.protocol import EventName
from meadows.protocol.envelope import Message, MessageType, QuotedMessage, generate_message_id, now_iso


class FetchBot(BaseBot):
    """Fetch URLs and convert their content to markdown.

    Extracts URLs from command arguments, quoted messages, or thread
    context, then fetches them concurrently using httpx. Content is
    extracted using trafilatura with BeautifulSoup fallback.
    """

    BOT_NAME = "fetch"
    BOT_DESCRIPTION = "Download URLs en converteer naar markdown"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = []

    URL_PATTERN = r"https?://[^\s\)\"'\]<>]+"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    MAX_CONCURRENCY = 5
    DEFAULT_MAX_CHARS = 5000
    HTTP_TIMEOUT = 5.0
    MIN_CONTENT_LENGTH = 100

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return True

    def _parse_context_flags(self, raw_args: list[str]) -> int | None:
        raw_string = " ".join(raw_args)
        if re.search(r"(-{1,2}all)\b", raw_string):
            return None
        match = re.search(r"-(\d+)(?:\s|$)", raw_string)
        if match:
            return int(match.group(1))
        return 30

    def handle(
        self,
        command: str,  # noqa: ARG002
        args: list[str],
        raw_args: list[str],
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],
    ) -> str | None:
        context_limit = self._parse_context_flags(raw_args)
        urls = self._collect_urls(args, message, thread_context, context_limit)

        if not urls:
            return "Usage: @fetch <url> [more urls...]"

        has_full = bool(re.search(r"(-{1,2}full)\b", " ".join(raw_args)))
        max_chars = None if has_full else self.DEFAULT_MAX_CHARS

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self._fetch_all(urls, max_chars))
            loop.close()
        except Exception as e:
            self.log(f"Error in async fetch: {e!s}", level="ERROR")
            return f"Error fetching URLs: {e!s}"

        for url, content in zip(urls, results):
            if isinstance(content, Exception):
                self._emit_single_response(f"Error fetching {url}: {content}", message)
            else:
                self._emit_single_response(content, message)

        return None

    def _collect_urls(
        self,
        args: list[str],
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],
        context_limit: int | None,
    ) -> list[str]:
        urls = []
        urls.extend(self._extract_urls_from_text(" ".join(args)))

        if message.get("content"):
            urls.extend(self._extract_urls_from_text(message["content"]))
        quoted = message.get("quoted_message")
        if isinstance(quoted, dict) and quoted.get("content"):
            urls.extend(self._extract_urls_from_text(quoted["content"]))

        if not args and context_limit is not None:
            msgs = thread_context[-context_limit:] if context_limit else thread_context
            for msg in msgs:
                if msg.get("content"):
                    urls.extend(self._extract_urls_from_text(msg["content"]))

        return self._deduplicate(urls)

    def _emit_single_response(self, content: str, message: dict[str, Any]) -> None:
        group_id = message.get("group_id", "general")
        quoted_msg = None
        if message.get("id") and message.get("user_id"):
            quoted_msg = QuotedMessage(
                id=message["id"],
                author=message.get("username") or message.get("user_id", "unknown"),
                user_id=message.get("user_id"),
                username=message.get("username"),
                content=message.get("content", ""),
                timestamp=message.get("timestamp", ""),
            )

        response = Message(
            id=generate_message_id(),
            type=MessageType.BOT,
            user_id=self.claims.sub,
            bot_name=self.BOT_NAME,
            group_id=group_id,
            content=content,
            original_command=f"@{self.BOT_NAME}",
            quoted_message=quoted_msg,
            timestamp=now_iso(),
        )
        self._fire_and_forget(EventName.MESSAGE, response.model_dump(exclude_none=True))

    async def _fetch_all(self, urls: list[str], max_chars: int | None) -> list:
        async with httpx.AsyncClient(
            timeout=self.HTTP_TIMEOUT,
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
        ) as client:
            semaphore = asyncio.Semaphore(self.MAX_CONCURRENCY)

            async def fetch_one(url: str) -> str | Exception:
                async with semaphore:
                    return await self._fetch_url(client, url, max_chars)

            tasks = [fetch_one(url) for url in urls]
            return await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_url(self, client: httpx.AsyncClient, url: str, max_chars: int | None) -> str:
        if not self._is_valid_url(url):
            return f"Invalid URL: {url}"

        try:
            response = await client.get(url)
            if response.status_code >= 400:
                return f"HTTP error {response.status_code}: {url}"

            html = response.text
            extracted = self._extract_content(html)
            if not extracted:
                return f"No content could be extracted from {url}"

            return self._format_content(url, extracted, max_chars)

        except httpx.TimeoutException:
            return f"Timeout fetching {url}"
        except httpx.RequestError as e:
            return f"Failed to fetch {url}: {e!s}"
        except Exception as e:
            return f"Error processing {url}: {e!s}"

    def _extract_content(self, html: str) -> str | None:  # noqa: C901
        # Lazy imports for heavy dependencies
        try:
            import trafilatura
        except ImportError:
            trafilatura = None  # type: ignore[assignment]

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            BeautifulSoup = None  # noqa: N806

        results: list[tuple[str, int]] = []

        if trafilatura is not None:
            extracted = trafilatura.extract(html, include_comments=False, favor_precision=True)
            if extracted and len(extracted) >= 50:
                results.append(("trafilatura", len(extracted)))

        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
                tag.decompose()

            main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
            if main:
                text = main.get_text(strip=True)
                if text and len(text) >= 50:
                    results.append(("beautifulsoup", len(text)))
            else:
                body = soup.find("body")
                if body:
                    text = body.get_text(strip=True)
                    if text and len(text) >= 50:
                        results.append(("beautifulsoup", len(text)))

        if not results:
            return None

        results.sort(key=lambda x: x[1], reverse=True)
        best_method = results[0][0]

        if best_method == "trafilatura":
            return trafilatura.extract(html, include_comments=False, favor_precision=True)

        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
                tag.decompose()
            body = soup.find("body") or soup
            return str(body)

        return None

    def _format_content(self, url: str, extracted: str, max_chars: int | None) -> str:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.body_width = 0
        markdown = h.handle(extracted)

        markdown = re.sub(r"¶", "\n", markdown)
        markdown = re.sub(r"\n\n\n+", "\n\n", markdown)

        status = ""
        if max_chars and len(markdown) > max_chars:
            markdown = markdown[:max_chars] + f"\n\n[Content truncated to {max_chars} chars]"
            status = " (truncated)"

        return f"### {url}{status}\n\n{markdown.strip()}"

    def _extract_urls_from_text(self, text: str) -> list[str]:
        if not text:
            return []
        return re.findall(self.URL_PATTERN, text)

    def _deduplicate(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        result = []
        for item in items:
            normalized = item.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                result.append(item)
        return result

    def _is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return bool(result.scheme in ("http", "https") and result.netloc)
        except Exception:
            return False


if __name__ == "__main__":
    FetchBot().connect()
