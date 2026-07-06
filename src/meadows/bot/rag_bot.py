#!/usr/bin/env python3
"""RAG Bot — Search media fragments via RAG API.

BUSINESS RULE (MEADOWS §5 line 130): this bot proves that a bot with
external HTTP dependencies works through the SDK. It calls the RAG
search API directly — the monolith's internal `rag` module is left behind.

BUSINESS RULE (MEADOWS §7 line 152): "de monoliet deed het fout-maar-werkend."
The monolith imported `from rag import search` via sys.path. The new bot
makes a direct httpx POST to the RAG search API, which is the same
behavior but with a clean import chain.

Usage:
    @rag <query>              - Search (10 results)
    @rag <query> --all        - Search with more results (20 instead of 10)

Environment Variables:
    RAG_SEARCH_API_URL: URL to RAG search API (default: http://localhost:8000/api/search)
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

import httpx

from meadows.bot import BaseBot


class RagBot(BaseBot):
    """Search video/audio fragments using the RAG search API.

    Makes direct HTTP calls to the RAG search API endpoint. No local
    imports from the monolith's `rag` module — the API is the boundary.
    """

    BOT_NAME = "rag"
    BOT_DESCRIPTION = "Zoek naar video of audio via RAG"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = []
    REQUEST_TIMEOUT = 30.0

    def __init__(self, token: str | None = None) -> None:
        super().__init__(token=token)
        self.api_url = os.environ.get("RAG_SEARCH_API_URL", "http://localhost:8000/api/search")

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return True

    def _format_results(self, results: dict, thread_context: list[dict[str, Any]]) -> str:  # noqa: C901
        if not results:
            return "No results found or search error"

        full_docs = results.get("full", [])
        chunks = results.get("chunks", [])

        if not full_docs and not chunks:
            return "No results found."

        output = ""

        if full_docs:
            output += f"**Full Documents** ({len(full_docs)} results)\n\n"
            for i, doc in enumerate(full_docs, 1):
                title = doc.get("title", "Untitled")
                output += f"{i}. **{title}**"

                meta = []
                if doc.get("series"):
                    meta.append(f"*{doc['series']}*")
                if doc.get("date"):
                    meta.append(f"📅 {doc['date']}")
                if meta:
                    output += f" • {' • '.join(meta)}"

                output += f" • ⭐ {doc.get('rrf_score', 0):.2f}\n"

                if doc.get("content"):
                    output += f"{doc['content']}\n"
                output += "\n"

        if chunks:
            output += f"**Transcript Chunks** ({len(chunks)} results)\n\n"
            for i, chunk in enumerate(chunks, 1):
                title = chunk.get("title", "Untitled")
                output += f"{i}. **{title}**"

                meta = []
                if chunk.get("series"):
                    meta.append(f"*{chunk['series']}*")
                if chunk.get("start") is not None and chunk.get("end") is not None:
                    meta.append(f"⏱️ {chunk['start']:.1f}s-{chunk['end']:.1f}s")
                if meta:
                    output += f" • {' • '.join(meta)}"

                output += f" • ⭐ {chunk.get('rrf_score', 0):.2f}\n"

                if chunk.get("content"):
                    output += f"{chunk['content']}\n"
                output += "\n"

        if thread_context:
            output += f"_[Based on {len(thread_context)} messages of context]_"

        return output

    def handle(
        self,
        command: str,  # noqa: ARG002
        args: list[str],
        raw_args: list[str],
        message: dict[str, Any],  # noqa: ARG002
        thread_context: list[dict[str, Any]],
    ) -> str | None:
        if not args:
            return "Usage: @rag <search query>\nExample: @rag video about history"

        query = " ".join(args)
        top_k = 20 if "--all" in raw_args else 10

        self.log(f"Searching RAG: '{query}' (top_k={top_k})")

        try:
            response = httpx.post(
                self.api_url,
                json={
                    "query": query,
                    "limit": top_k * 3,
                    "hybrid": True,
                    "semantic_weight": 5.0,
                    "bm25_weight": 1.0,
                },
                timeout=self.REQUEST_TIMEOUT,
            )
            if response.status_code >= 400:
                self.log(f"RAG API returned status {response.status_code}", level="ERROR")
                return f"[RAG API error: {response.status_code}]"

            api_results = response.json()
            raw_results = api_results.get("results", [])

            results: dict[str, list[dict[str, Any]]] = {"query": query, "full": [], "chunks": []}

            for r in raw_results:
                metadata = r.get("metadata", {})
                doc_type = metadata.get("doc_type", "")
                item = {
                    "id": r.get("id"),
                    "title": metadata.get("title", r.get("title", "")),
                    "content": (r.get("content", "") or "")[:500],
                    "score": round(r.get("similarity", 0), 4),
                    "rrf_score": round(r.get("rrf_score", 0), 4),
                }

                if doc_type == "transcript_chunk":
                    item.update({
                        "doc_id": metadata.get("resource_id", ""),
                        "series": metadata.get("series", ""),
                        "start": metadata.get("start"),
                        "end": metadata.get("end"),
                        "date": metadata.get("date", ""),
                    })
                    results["chunks"].append(item)
                else:
                    item.update({
                        "series": metadata.get("series", ""),
                        "date": metadata.get("date", ""),
                        "resource_id": metadata.get("resource_id", ""),
                    })
                    results["full"].append(item)

            results["full"] = results["full"][:top_k]
            seen_docs: dict[str, dict] = {}
            for c in results["chunks"]:
                doc_id = c.get("doc_id") or c.get("resource_id", "")
                if doc_id and doc_id not in seen_docs:
                    seen_docs[doc_id] = c
            results["chunks"] = list(seen_docs.values())[:top_k]

            self.log(f"Found {len(results['full'])} documents + {len(results['chunks'])} chunks")

            return self._format_results(results, thread_context)

        except httpx.ConnectError:
            error_msg = f"Cannot connect to RAG API at {self.api_url}"
            self.log(error_msg, level="ERROR")
            return f"[{error_msg}]"

        except httpx.TimeoutException:
            error_msg = "RAG API request timed out"
            self.log(error_msg, level="ERROR")
            return f"[{error_msg}]"


if __name__ == "__main__":
    RagBot().connect()
