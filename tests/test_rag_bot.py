"""Tests for RagBot."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("httpx")

import httpx
import pytest

from meadows.bot.rag_bot import RagBot


MOCK_SEARCH_RESPONSE = {
    "results": [
        {
            "id": "doc-1",
            "title": "History of AI",
            "content": "Artificial intelligence has evolved rapidly.",
            "similarity": 0.85,
            "rrf_score": 0.92,
            "metadata": {
                "doc_type": "document",
                "title": "History of AI",
                "series": "Tech Talks",
                "date": "2024-01-15",
                "resource_id": "res-1",
            },
        },
        {
            "id": "chunk-1",
            "title": "AI in Education",
            "content": "AI can help personalize learning experiences.",
            "similarity": 0.78,
            "rrf_score": 0.85,
            "metadata": {
                "doc_type": "transcript_chunk",
                "title": "AI in Education",
                "series": "Future Classrooms",
                "start": 120.5,
                "end": 145.3,
                "date": "2024-02-01",
                "resource_id": "res-2",
            },
        },
    ]
}


class TestRagBotConstruction:
    def test_construct(self, bot_token):
        bot = RagBot(token=bot_token)
        assert bot.BOT_NAME == "rag"


class TestRagBotShouldHandle:
    def test_handles_all_commands(self, make_bot):
        bot, _ = make_bot(RagBot)
        assert bot.should_handle("anything", [])


class TestRagBotHandle:
    def test_usage_when_no_args(self, make_bot):
        bot, _ = make_bot(RagBot)
        result = bot.handle("", [], [], {"group_id": "general"}, [])
        assert "Usage: @rag" in result

    @patch("httpx.post")
    def test_search_with_results(self, mock_post, make_bot):
        mock_response = httpx.Response(200, json=MOCK_SEARCH_RESPONSE)
        mock_post.return_value = mock_response

        bot, _ = make_bot(RagBot)
        result = bot.handle(
            "", ["history", "of", "AI"], [], {"group_id": "general"}, []
        )
        assert "Full Documents" in result
        assert "History of AI" in result
        assert "Transcript Chunks" in result

    @patch("httpx.post")
    def test_search_with_all_flag(self, mock_post, make_bot):
        mock_response = httpx.Response(200, json=MOCK_SEARCH_RESPONSE)
        mock_post.return_value = mock_response

        bot, _ = make_bot(RagBot)
        result = bot.handle(
            "", ["history"], ["history", "--all"], {"group_id": "general"}, []
        )
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["limit"] == 60
        assert "Full Documents" in result

    @patch("httpx.post")
    def test_no_results(self, mock_post, make_bot):
        mock_response = httpx.Response(200, json={"results": []})
        mock_post.return_value = mock_response

        bot, _ = make_bot(RagBot)
        result = bot.handle("", ["test"], [], {"group_id": "general"}, [])
        assert "No results found" in result

    @patch("httpx.post")
    def test_connection_error(self, mock_post, make_bot):
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        bot, _ = make_bot(RagBot)
        result = bot.handle("", ["test"], [], {"group_id": "general"}, [])
        assert "Cannot connect to RAG API" in result

    @patch("httpx.post")
    def test_timeout_error(self, mock_post, make_bot):
        mock_post.side_effect = httpx.TimeoutException("Timed out")

        bot, _ = make_bot(RagBot)
        result = bot.handle("", ["test"], [], {"group_id": "general"}, [])
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    @patch("httpx.post")
    async def test_dispatch_search_command(self, mock_post, make_bot):
        mock_response = httpx.Response(200, json=MOCK_SEARCH_RESPONSE)
        mock_post.return_value = mock_response

        _bot, fake = make_bot(RagBot)
        await fake.trigger("bot_authenticated", {"groups": ["general"]})
        await fake.trigger("bot_command", {
            "command": "",
            "args": ["history"],
            "raw_args": ["history"],
            "message": {
                "group_id": "general", "id": "msg1", "user_id": "user1",
                "content": "@rag history",
            },
            "thread_context": [],
        })
        emits = fake.emits_for("bot_response")
        assert len(emits) >= 1
        assert "Full Documents" in emits[0]["content"]


class TestRagBotExceptionSafety:
    def test_handle_does_not_raise(self, make_bot):
        bot, _ = make_bot(RagBot)
        bot.handle("", [], [], {}, [])
