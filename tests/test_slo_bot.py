"""Tests for SLOBot."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from meadows.bot.slo_bot import SLOBot


MOCK_SLO_RESPONSE = {
    "query": "rekenen",
    "count": 2,
    "results": [
        {
            "id": "1",
            "title": "Getallen en bewerkingen",
            "description": "Leerlingen leren rekenen met getallen",
            "soort": "eindterm",
            "prefix": "8",
            "similarity": 0.85,
            "uitwerking_texts": [
                "Toelichting: basisbewerkingen",
                "Voorbeeld: 2+2=4",
            ],
        },
        {
            "id": "2",
            "title": "Meten en meetkunde",
            "description": "Leerlingen leren meten en meetkunde toepassen",
            "soort": "eindterm",
            "prefix": "9",
            "similarity": 0.72,
        },
    ],
}


class TestSLOBotConstruction:
    def test_construct(self, bot_token):
        bot = SLOBot(token=bot_token)
        assert bot.BOT_NAME == "slo"
        assert bot.DEFAULT_LIMIT == 10


class TestSLOBotShouldHandle:
    def test_handles_all_commands(self, make_bot):
        bot, _ = make_bot(SLOBot)
        assert bot.should_handle("anything", [])


class TestSLOBotParseParams:
    def test_defaults(self, make_bot):
        bot, _ = make_bot(SLOBot)
        params = bot._parse_search_params(["rekenen"])
        assert params["query"] == "rekenen"
        assert params["limit"] == 10
        assert params["threshold"] == 0.01

    def test_all_flag(self, make_bot):
        bot, _ = make_bot(SLOBot)
        params = bot._parse_search_params(["rekenen", "--all"])
        assert params["limit"] == 20

    def test_limit_flag(self, make_bot):
        bot, _ = make_bot(SLOBot)
        params = bot._parse_search_params(["rekenen", "--limit", "5"])
        assert params["limit"] == 5

    def test_threshold_flag(self, make_bot):
        bot, _ = make_bot(SLOBot)
        params = bot._parse_search_params(["rekenen", "--threshold", "0.5"])
        assert params["threshold"] == 0.5

    def test_shorthand_number(self, make_bot):
        bot, _ = make_bot(SLOBot)
        params = bot._parse_search_params(["-20", "rekenen"])
        assert params["limit"] == 20


class TestSLOBotHandle:
    def test_usage_when_no_args(self, make_bot):
        bot, _ = make_bot(SLOBot)
        result = bot.handle("", [], [], {"group_id": "general"}, [])
        assert "Usage: @slo" in result

    @patch("httpx.post")
    def test_search_with_results(self, mock_post, make_bot):
        mock_response = httpx.Response(200, json=MOCK_SLO_RESPONSE)
        mock_post.return_value = mock_response

        bot, _ = make_bot(SLOBot)
        result = bot.handle("", [], ["rekenen"], {"group_id": "general"}, [])
        assert "Search Results for 'rekenen'" in result
        assert "Getallen en bewerkingen" in result
        assert "Meten en meetkunde" in result
        assert "Elaborations" in result

    @patch("httpx.post")
    def test_no_results(self, mock_post, make_bot):
        mock_response = httpx.Response(
            200, json={"query": "test", "count": 0, "results": []}
        )
        mock_post.return_value = mock_response

        bot, _ = make_bot(SLOBot)
        result = bot.handle("", [], ["test"], {"group_id": "general"}, [])
        assert "No results found" in result

    @patch("httpx.post")
    def test_connection_error(self, mock_post, make_bot):
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        bot, _ = make_bot(SLOBot)
        result = bot.handle("", [], ["test"], {"group_id": "general"}, [])
        assert "Cannot connect to SLO API" in result

    @patch("httpx.post")
    def test_timeout_error(self, mock_post, make_bot):
        mock_post.side_effect = httpx.TimeoutException("Timed out")

        bot, _ = make_bot(SLOBot)
        result = bot.handle("", [], ["test"], {"group_id": "general"}, [])
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    @patch("httpx.post")
    async def test_dispatch_search_command(self, mock_post, make_bot):
        mock_response = httpx.Response(200, json=MOCK_SLO_RESPONSE)
        mock_post.return_value = mock_response

        _bot, fake = make_bot(SLOBot)
        await fake.trigger("bot_authenticated", {"groups": ["general"]})
        await fake.trigger("bot_command", {
            "command": "",
            "args": ["rekenen"],
            "raw_args": ["rekenen"],
            "message": {
                "group_id": "general", "id": "msg1", "user_id": "user1",
                "content": "@slo rekenen",
            },
            "thread_context": [],
        })
        emits = fake.emits_for("bot_response")
        assert len(emits) >= 1
        assert "Search Results" in emits[0]["content"]


class TestSLOBotExceptionSafety:
    def test_handle_does_not_raise(self, make_bot):
        bot, _ = make_bot(SLOBot)
        bot.handle("", [], [], {}, [])
