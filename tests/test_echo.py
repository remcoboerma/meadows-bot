"""Tests for the canonical echo example bot.

BUSINESS RULE (MEADOWS §5 line 130): the echo bot is the template a
groep-6 docent copies. These tests pin its behavior so the template
stays trustworthy.
"""

from __future__ import annotations

from typing import Any

from meadows.bot.examples.echo_bot import EchoBot
from meadows.protocol import EventName, MessageType


def _make_echo(make_bot):
    """Construct an EchoBot with a FakeMeadowClient (no server)."""
    return make_bot(EchoBot)


class TestEchoBotConstruction:
    def test_echo_bot_can_be_instantiated(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 130): the quick-start is
        `EchoBot()` — instantiation must not require a server.
        """
        bot, _ = _make_echo(make_bot)
        assert bot.BOT_NAME == "echo"
        assert bot.claims.sub == "bot-echo"

    def test_echo_bot_commands_manifest(self, make_bot):
        """BUSINESS RULE: the command manifest is what register_bot
        advertises. It must list echo, ping, help, info.
        """
        bot, _ = _make_echo(make_bot)
        names = {c["name"] for c in bot.BOT_COMMANDS}
        assert names == {"echo", "ping", "help", "info"}


class TestEchoBotShouldHandle:
    def test_should_handle_true_for_echo(self, make_bot):
        bot, _ = _make_echo(make_bot)
        assert bot.should_handle("echo", ["hi"]) is True

    def test_should_handle_true_for_ping(self, make_bot):
        bot, _ = _make_echo(make_bot)
        assert bot.should_handle("ping", []) is True

    def test_should_handle_true_for_help(self, make_bot):
        bot, _ = _make_echo(make_bot)
        assert bot.should_handle("help", []) is True

    def test_should_handle_true_for_info(self, make_bot):
        bot, _ = _make_echo(make_bot)
        assert bot.should_handle("info", []) is True

    def test_should_handle_false_for_unknown(self, make_bot):
        """BUSINESS RULE: should_handle is a closed allowlist — an
        unknown command must not be handled.
        """
        bot, _ = _make_echo(make_bot)
        assert bot.should_handle("unknown", []) is False


class TestEchoBotHandle:
    def _message(self) -> dict[str, Any]:
        return {
            "id": "m1",
            "user_id": "user-alice",
            "username": "alice",
            "email": "alice@example.com",
            "content": "@echo echo hello",
            "group_id": "general",
            "timestamp": "2026-01-01T00:00:00.000000",
        }

    def test_echo_returns_echo_text(self, make_bot):
        """BUSINESS RULE: @echo echo <text> -> "Echo: <text>"."""
        bot, _ = _make_echo(make_bot)
        result = bot.handle("echo", ["hello", "world"], ["hello", "world"], self._message(), [])
        assert result == "Echo: hello world"

    def test_echo_with_no_args_returns_usage(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 132): a usage message in human
        language, not a silent failure.
        """
        bot, _ = _make_echo(make_bot)
        result = bot.handle("echo", [], [], self._message(), [])
        assert "Usage" in result

    def test_ping_returns_pong_with_sender_name(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 132): address the user by name."""
        bot, _ = _make_echo(make_bot)
        result = bot.handle("ping", [], [], self._message(), [])
        assert "Pong" in result
        assert "alice" in result

    def test_help_returns_formatted_help(self, make_bot):
        """BUSINESS RULE: @echo help -> the formatted command list."""
        bot, _ = _make_echo(make_bot)
        result = bot.format_help_response()
        assert "Echo Bot Commands:" in result
        assert "@echo echo" in result
        assert "@echo ping" in result
        assert "@echo help" in result
        assert "@echo info" in result

    def test_info_returns_bot_description(self, make_bot):
        """BUSINESS RULE: @echo info -> the bot's self-description."""
        bot, _ = _make_echo(make_bot)
        result = bot.handle("info", [], [], self._message(), [{"content": "x"}])
        assert "echo" in result
        assert "simple echo bot" in result
        # Includes thread context count.
        assert "1 messages" in result


class TestEchoBotRouting:
    def _command_data(self, command: str, args: list[str]) -> dict[str, Any]:
        return {
            "command": command,
            "args": args,
            "raw_args": args,
            "message": {
                "id": "m1",
                "user_id": "user-alice",
                "username": "alice",
                "email": "alice@example.com",
                "content": f"@echo {command} {' '.join(args)}",
                "group_id": "general",
                "timestamp": "2026-01-01T00:00:00.000000",
            },
            "thread_context": [],
        }

    async def test_on_bot_command_emits_bot_response_for_echo(self, make_bot):
        """BUSINESS RULE (MEADOWS §2 line 41): the response goes out as
        a protocol Message (bot_response event), not a hand-built dict.
        """
        bot, fake = _make_echo(make_bot)
        await bot.on_bot_command(self._command_data("echo", ["hello"]))
        responses = fake.emits_for(EventName.BOT_RESPONSE)
        assert len(responses) == 1
        data = responses[0]
        assert data["type"] == MessageType.BOT
        assert data["bot_name"] == "echo"
        assert data["content"] == "Echo: hello"
        assert data["group_id"] == "general"

    async def test_on_bot_command_no_emit_for_unknown_command(self, make_bot):
        """BUSINESS RULE: an unknown command produces no bot_response."""
        bot, fake = _make_echo(make_bot)
        await bot.on_bot_command(self._command_data("unknown", []))
        assert fake.emits_for(EventName.BOT_RESPONSE) == []
