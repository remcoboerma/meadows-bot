"""Tests for LLMBot — the minimal abstract LLM bot.

BUSINESS RULE (MEADOWS §3.3 line 78): provider specifics stay out of
the PoC. LLMBot gives authors one seam — query_llm — and a default
handle() that wires it into the conversation context.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from meadows.bot import LLMBot


class _StubLLMBot(LLMBot):
    """Concrete LLMBot that records prompts and returns a canned response.

    BUSINESS RULE (MEADOWS §3.3 line 78): a real subclass would call
    Ollama/Scaleway/OpenRouter in query_llm. This stub stands in so
    tests don't need a network or an LLM.
    """

    BOT_NAME = "stubllm"
    BOT_DESCRIPTION = "stub llm bot"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [{"name": "ask", "description": "ask the LLM"}]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.prompts: list[str] = []

    def query_llm(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"LLM-RESPONSE-FOR: {prompt.splitlines()[-1]}"


class TestLLMBotAbstract:
    def test_llmbot_is_abstract_without_query_llm(self, jwt_secret_file):
        """BUSINESS RULE (MEADOWS §5 line 130): LLMBot is abstract —
        you can't run an LLM bot without writing query_llm.
        """

        class _Incomplete(LLMBot):  # does not implement query_llm
            pass

        with pytest.raises(TypeError):
            _Incomplete(jwt_secret_path=str(jwt_secret_file))  # type: ignore[abstract]

    def test_llmbot_is_abstract_via_base(self):
        """BUSINESS RULE: LLMBot inherits BaseBot's abstractness, so it
        can't be instantiated directly either.
        """
        with pytest.raises(TypeError):
            LLMBot()  # type: ignore[abstract]


class TestLLMBotHandle:
    def _message(self) -> dict[str, Any]:
        return {
            "id": "m1",
            "user_id": "user-alice",
            "username": "alice",
            "email": "alice@example.com",
            "content": "@stubllm ask what is the weather",
            "group_id": "general",
            "timestamp": "2026-01-01T00:00:00.000000",
        }

    def test_handle_calls_query_llm(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 130): the default handle()
        calls query_llm — the single seam an author fills.
        """
        bot, _ = make_bot(_StubLLMBot)
        result = bot.handle("ask", ["what", "is", "the", "weather"], [], self._message(), [])
        assert len(bot.prompts) == 1
        assert "what is the weather" in bot.prompts[0]
        assert result == "LLM-RESPONSE-FOR: alice: ask what is the weather"

    def test_handle_includes_thread_context_in_prompt(self, make_bot):
        """BUSINESS RULE: the prompt is the thread context (as
        "sender: content" lines) plus the current command.
        """
        bot, _ = make_bot(_StubLLMBot)
        thread = [
            {"username": "bob", "content": "hi"},
            {"username": "alice", "content": "hello"},
        ]
        bot.handle("ask", ["why"], [], self._message(), thread)
        prompt = bot.prompts[0]
        assert "bob: hi" in prompt
        assert "alice: hello" in prompt
        assert "alice: ask why" in prompt

    def test_should_handle_defaults_to_advertised_commands(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 130): an LLM bot author who
        just wants "respond to what I advertised" doesn't write
        should_handle. The default is the manifest allowlist.
        """
        bot, _ = make_bot(_StubLLMBot)
        assert bot.should_handle("ask", []) is True
        assert bot.should_handle("other", []) is False

    def test_handle_returns_llm_output(self, make_bot):
        """BUSINESS RULE: handle() returns whatever query_llm() returns,
        so the LLM's output becomes the bot_response content.
        """
        bot, _ = make_bot(_StubLLMBot)
        result = bot.handle("ask", ["x"], [], self._message(), [])
        assert result is not None
        assert result.startswith("LLM-RESPONSE-FOR:")
