"""Tests for FetchBot."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("httpx")

from meadows.bot.fetch_bot import FetchBot


class TestFetchBotConstruction:
    def test_construct(self, bot_token):
        bot = FetchBot(token=bot_token)
        assert bot.BOT_NAME == "fetch"


class TestFetchBotShouldHandle:
    def test_handles_all_commands(self, make_bot):
        bot, _ = make_bot(FetchBot)
        assert bot.should_handle("anything", [])


class TestFetchBotUrlExtraction:
    def test_extract_urls_from_text(self, make_bot):
        bot, _ = make_bot(FetchBot)
        urls = bot._extract_urls_from_text(
            "Check https://example.com and http://test.nl/page"
        )
        assert len(urls) == 2
        assert "https://example.com" in urls
        assert "http://test.nl/page" in urls

    def test_no_urls(self, make_bot):
        bot, _ = make_bot(FetchBot)
        urls = bot._extract_urls_from_text("Just some text without URLs")
        assert urls == []

    def test_empty_text(self, make_bot):
        bot, _ = make_bot(FetchBot)
        urls = bot._extract_urls_from_text("")
        assert urls == []

    def test_deduplicate(self, make_bot):
        bot, _ = make_bot(FetchBot)
        urls = bot._deduplicate([
            "https://example.com", "https://example.com", "https://other.com"
        ])
        assert len(urls) == 2


class TestFetchBotUrlValidation:
    def test_valid_urls(self, make_bot):
        bot, _ = make_bot(FetchBot)
        assert bot._is_valid_url("https://example.com")
        assert bot._is_valid_url("http://test.nl/path?q=1")

    def test_invalid_urls(self, make_bot):
        bot, _ = make_bot(FetchBot)
        assert not bot._is_valid_url("not-a-url")
        assert not bot._is_valid_url("")
        assert not bot._is_valid_url("ftp://example.com")


class TestFetchBotCollectUrls:
    def test_urls_from_args(self, make_bot):
        bot, _ = make_bot(FetchBot)
        urls = bot._collect_urls(
            ["https://example.com"], {"group_id": "general"}, [], 30
        )
        assert "https://example.com" in urls

    def test_urls_from_message(self, make_bot):
        bot, _ = make_bot(FetchBot)
        urls = bot._collect_urls(
            [],
            {"group_id": "general", "content": "Check https://example.com out"},
            [],
            30,
        )
        assert "https://example.com" in urls

    def test_urls_from_quoted_message(self, make_bot):
        bot, _ = make_bot(FetchBot)
        urls = bot._collect_urls(
            [],
            {
                "group_id": "general",
                "quoted_message": {"content": "See https://test.com"},
            },
            [],
            30,
        )
        assert "https://test.com" in urls


class TestFetchBotHandle:
    def test_usage_when_no_urls(self, make_bot):
        bot, _ = make_bot(FetchBot)
        result = bot.handle("", [], [], {"group_id": "general"}, [])
        assert "Usage: @fetch" in result

    def test_returns_none_when_emitting(self, make_bot):
        bot, _ = make_bot(FetchBot)
        result = bot.handle(
            "", ["https://example.com"], [],
            {"group_id": "general", "id": "m1", "user_id": "u1"}, []
        )
        assert result is None

    def test_parse_context_flags_default(self, make_bot):
        bot, _ = make_bot(FetchBot)
        result = bot._parse_context_flags([])
        assert result == 30

    def test_parse_context_flags_all(self, make_bot):
        bot, _ = make_bot(FetchBot)
        result = bot._parse_context_flags(["--all"])
        assert result is None

    def test_parse_context_flags_number(self, make_bot):
        bot, _ = make_bot(FetchBot)
        result = bot._parse_context_flags(["-50"])
        assert result == 50

    def test_format_content_truncated(self, make_bot):
        bot, _ = make_bot(FetchBot)
        with patch("html2text.HTML2Text.handle", return_value="A" * 6000):
            result = bot._format_content(
                "https://example.com", "<html>content</html>", max_chars=100
            )
            assert "truncated" in result

    @pytest.mark.asyncio
    async def test_dispatch_fetch_command(self, make_bot):
        _bot, fake = make_bot(FetchBot)
        await fake.trigger("bot_authenticated", {"groups": ["general"]})
        await fake.trigger("bot_command", {
            "command": "",
            "args": ["https://example.com"],
            "raw_args": ["https://example.com"],
            "message": {
                "group_id": "general", "id": "msg1", "user_id": "user1",
                "content": "@fetch https://example.com",
            },
            "thread_context": [],
        })
        emits = fake.emits_for("bot_response")
        assert len(emits) >= 1


class TestFetchBotExceptionSafety:
    def test_handle_does_not_raise(self, make_bot):
        bot, _ = make_bot(FetchBot)
        bot.handle("", [], [], {"group_id": "general"}, [])
