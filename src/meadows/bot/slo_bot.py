#!/usr/bin/env python3
"""SLO Bot — Search learning outcomes from SLO curriculum database.

BUSINESS RULE (MEADOWS §5 line 130): this bot proves that a bot with
external HTTP dependencies works through the SDK. It calls the SLO
search REST API directly with no authentication required.

BUSINESS RULE (MEADOWS §7 line 152): "de monoliet deed het fout-maar-werkend."
The monolith imported from base via sys.path. The new bot imports cleanly
from meadows.bot.

Usage:
    @slo <query>              - Search (10 results, threshold 0.01)
    @slo <query> --limit 20   - Search with more results
    @slo <query> --threshold 0.5 - Search with higher threshold
    @slo <query> --all        - Alias for --limit 20

Environment Variables:
    SLO_API_BASE_URL: SLO search API URL (default: https://slo-search-rest-api.greenserver.verzimpel.nl/api/search)
"""

from __future__ import annotations

import os
import re
from contextlib import suppress
from typing import Any, ClassVar

import httpx

from meadows.bot import BaseBot


class SLOBot(BaseBot):
    """Search learning outcomes from SLO curriculum database using public REST API.

    Makes direct HTTP POST to the SLO search API endpoint. Supports
    hybrid search with semantic embeddings + BM25 + RRF ranking.
    """

    BOT_NAME = "slo"
    BOT_DESCRIPTION = "Zoek leeruitkomsten en competenties uit het SLO curriculum"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = []

    API_BASE_URL = "https://slo-search-rest-api.greenserver.verzimpel.nl/api/search"
    DEFAULT_LIMIT = 10
    DEFAULT_THRESHOLD = 0.01
    DEFAULT_WEIGHT = 0.7
    REQUEST_TIMEOUT = 30.0

    def __init__(self, token: str | None = None) -> None:
        super().__init__(token=token)
        self.api_url = os.environ.get("SLO_API_BASE_URL", self.API_BASE_URL)

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return True

    def _parse_search_params(self, raw_args: list[str]) -> dict[str, Any]:
        raw_string = " ".join(raw_args)

        limit = self.DEFAULT_LIMIT
        threshold = self.DEFAULT_THRESHOLD
        weight = self.DEFAULT_WEIGHT

        if re.search(r"--all\b", raw_string):
            limit = 20

        match = re.search(r"--limit\s+(\d+)", raw_string)
        if match:
            with suppress(ValueError):
                limit = min(int(match.group(1)), 100)

        match = re.search(r"^-(\d+)(?:\s|$)", raw_string)
        if match:
            with suppress(ValueError):
                limit = min(int(match.group(1)), 100)

        match = re.search(r"--threshold\s+([\d.]+)", raw_string)
        if match:
            with suppress(ValueError):
                threshold = float(match.group(1))

        match = re.search(r"--weight\s+([\d.]+)", raw_string)
        if match:
            with suppress(ValueError):
                weight = float(match.group(1))

        query = re.sub(
            r"(--limit\s+\d+|--threshold\s+[\d.]+|--weight\s+[\d.]+|-\d+|--all)\s*",
            "",
            raw_string,
        ).strip()

        return {
            "query": query,
            "limit": limit,
            "threshold": threshold,
            "weight": weight,
        }

    def _format_results(self, results: dict) -> str:
        if not results:
            return "No results or search error"

        query = results.get("query", "")
        count = results.get("count", 0)
        items = results.get("results", [])

        if count == 0 or not items:
            return f"No results found for '{query}'"

        output = f"**Search Results for '{query}'** ({count} found)\n\n"

        for i, item in enumerate(items, 1):
            title = item.get("title", "Untitled")
            description = item.get("description", "")
            soort = item.get("soort", "")
            prefix = item.get("prefix", "")
            similarity = item.get("similarity", 0)

            output += f"{i}. **{title}**"

            meta = []
            if soort:
                meta.append(soort)
            if prefix:
                meta.append(f"#{prefix}")
            if meta:
                output += f" • {' • '.join(meta)}"

            output += f" • {similarity:.2%}\n"

            if description:
                output += f"   {description}\n"

            elaborations = item.get("uitwerking_texts", [])
            if elaborations:
                output += "   **Elaborations:**\n"
                for elab in elaborations[:3]:
                    output += f"   • {elab}\n"

            output += "\n"

        return output.strip()

    def handle(
        self,
        command: str,  # noqa: ARG002
        args: list[str],  # noqa: ARG002
        raw_args: list[str],
        message: dict[str, Any],  # noqa: ARG002
        thread_context: list[dict[str, Any]],  # noqa: ARG002
    ) -> str | None:
        if not raw_args:
            return "Usage: @slo <query> [--limit 10] [--threshold 0.01] [--all]"

        params = self._parse_search_params(raw_args)
        query = params["query"]

        if not query:
            return "Usage: @slo <query> [--limit 10] [--threshold 0.01] [--all]"

        self.log(f"Searching SLO: '{query}' (limit={params['limit']}, threshold={params['threshold']})")

        try:
            response = httpx.post(
                self.api_url,
                json={
                    "query": query,
                    "limit": params["limit"],
                    "threshold": params["threshold"],
                    "weight": params["weight"],
                    "rerank": False,
                },
                params={
                    "limit": params["limit"],
                    "threshold": params["threshold"],
                    "weight": params["weight"],
                    "rerank": False,
                },
                timeout=self.REQUEST_TIMEOUT,
            )

            if response.status_code >= 400:
                error_msg = f"SLO API returned status {response.status_code}"
                self.log(error_msg, level="ERROR")
                return f"[{error_msg}]"

            results = response.json()
            return self._format_results(results)

        except httpx.ConnectError:
            error_msg = f"Cannot connect to SLO API at {self.api_url}"
            self.log(error_msg, level="ERROR")
            return f"[{error_msg}]"

        except httpx.TimeoutException:
            error_msg = "SLO API request timed out (30s)"
            self.log(error_msg, level="ERROR")
            return f"[{error_msg}]"

        except Exception as e:
            error_msg = f"SLO search error: {str(e)[:100]}"
            self.log(error_msg, level="ERROR")
            return f"[{error_msg}]"


if __name__ == "__main__":
    SLOBot().connect()
