"""Tests for ChatBot."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("httpx")

import httpx
import pytest

from meadows.bot.chat_bot import ChatBot


class TestChatBotConstruction:
    def test_construct(self, bot_token):
        bot = ChatBot(token=bot_token)
        assert bot.BOT_NAME == "bot"
        assert isinstance(bot, ChatBot)


class TestChatBotShouldHandle:
    def test_handles_all_commands(self, make_bot):
        bot, _ = make_bot(ChatBot)
        assert bot.should_handle("anything", [])


class TestChatBotLanguageDetection:
    def test_detects_dutch(self, make_bot):
        bot, _ = make_bot(ChatBot)
        assert bot._detect_language("Hallo, wat is dit?") == "Dutch"

    def test_detects_english(self, make_bot):
        bot, _ = make_bot(ChatBot)
        assert bot._detect_language("Hello world, this seems like English") == "English"


class TestChatBotContextParsing:
    def test_default_context(self, make_bot):
        bot, _ = make_bot(ChatBot)
        assert bot._parse_context_flags([]) == 30

    def test_all_flag(self, make_bot):
        bot, _ = make_bot(ChatBot)
        assert bot._parse_context_flags(["--all"]) is None

    def test_number_flag(self, make_bot):
        bot, _ = make_bot(ChatBot)
        assert bot._parse_context_flags(["-50"]) == 50


class TestChatBotHandle:
    def test_empty_message_returns_empty(self, make_bot):
        bot, _ = make_bot(ChatBot)
        result = bot.handle("", [], [], {"group_id": "general"}, [])
        assert result == ""

    def test_blank_message_returns_empty(self, make_bot):
        bot, _ = make_bot(ChatBot)
        result = bot.handle("", [], ["   "], {"group_id": "general"}, [])
        assert result == ""

    @patch.object(ChatBot, "query_llm", return_value="Hallo! Hoe kan ik je helpen?")
    def test_sends_prompt_to_llm(self, mock_query, make_bot):
        bot, _ = make_bot(ChatBot)
        result = bot.handle(
            "", [], ["Hallo"], {
                "group_id": "general", "id": "msg1", "user_id": "u1",
                "username": "Alice",
            }, []
        )
        assert "Hallo!" in result
        mock_query.assert_called_once()

    @patch.object(ChatBot, "query_llm", return_value="Test response")
    def test_includes_context_in_prompt(self, mock_query, make_bot):
        bot, _ = make_bot(ChatBot)
        bot.handle(
            "", [], ["Hallo"], {"group_id": "general", "id": "msg1", "user_id": "u1"},
            [{"username": "Bob", "content": "Eerste bericht", "id": "old1"}],
        )
        prompt = mock_query.call_args[0][0]
        assert "Eerste bericht" in prompt
        assert "Bob:" in prompt

    @patch.object(ChatBot, "query_llm", return_value="Dutch response")
    def test_detects_dutch_language(self, mock_query, make_bot):
        bot, _ = make_bot(ChatBot)
        bot.handle(
            "", [], ["Hallo, wat is dit voor een systeem?"],
            {"group_id": "general", "id": "msg1", "user_id": "u1"}, []
        )
        prompt = mock_query.call_args[0][0]
        assert "Dutch" in prompt or "Hallo" in prompt


class TestChatBotQueryLLM:
    @patch("httpx.post")
    def test_query_llm_success(self, mock_post, make_bot):
        mock_response = httpx.Response(200, json={"response": "Antwoord van Ollama"})
        mock_post.return_value = mock_response

        bot, _ = make_bot(ChatBot)
        result = bot.query_llm("Test prompt")
        assert result == "Antwoord van Ollama"

    @patch("httpx.post")
    def test_query_llm_connection_error(self, mock_post, make_bot):
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        bot, _ = make_bot(ChatBot)
        result = bot.query_llm("Test")
        assert "Kan geen verbinding maken" in result

    @patch("httpx.post")
    def test_query_llm_timeout(self, mock_post, make_bot):
        mock_post.side_effect = httpx.TimeoutException("Timed out")

        bot, _ = make_bot(ChatBot)
        result = bot.query_llm("Test")
        assert "time-out" in result.lower()

    def test_query_llm_no_model(self, make_bot):
        bot, _ = make_bot(ChatBot)
        bot.model = ""
        result = bot.query_llm("Test")
        assert "niet geconfigureerd" in result

    @pytest.mark.asyncio
    @patch.object(ChatBot, "query_llm", return_value="Antwoord")
    async def test_dispatch_chat_command(self, mock_query, make_bot):  # noqa: ARG002
        _bot, fake = make_bot(ChatBot)
        await fake.trigger("bot_authenticated", {"groups": ["general"]})
        await fake.trigger("bot_command", {
            "command": "",
            "args": ["Hallo"],
            "raw_args": ["Hallo"],
            "message": {
                "group_id": "general", "id": "msg1", "user_id": "u1",
                "username": "Alice", "content": "@bot Hallo",
            },
            "thread_context": [],
        })
        emits = fake.emits_for("bot_response")
        assert len(emits) >= 1
        assert "Antwoord" in emits[0]["content"]


class TestChatBotExceptionSafety:
    def test_handle_does_not_raise(self, make_bot):
        bot, _ = make_bot(ChatBot)
        bot.handle("", [], [], {"group_id": "general"}, [])
