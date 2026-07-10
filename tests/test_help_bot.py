"""Tests for HelpBot."""

from __future__ import annotations

import pytest

from meadows.bot.help_bot import HelpBot


class TestHelpBotConstruction:
    def test_construct(self, bot_token):
        bot = HelpBot(token=bot_token)
        assert bot.BOT_NAME == "help"
        assert len(bot.BOT_COMMANDS) == 5


class TestHelpBotShouldHandle:
    def test_handles_known_commands(self, make_bot):
        bot, _ = make_bot(HelpBot)
        for cmd in ("help", "bots", "commands", "groups", "guide"):
            assert bot.should_handle(cmd, [])

    def test_rejects_unknown(self, make_bot):
        bot, _ = make_bot(HelpBot)
        assert not bot.should_handle("unknown", [])
        assert not bot.should_handle("stats", [])


class TestHelpBotHandle:
    def test_help_command(self, make_bot):
        bot, _ = make_bot(HelpBot)
        result = bot.handle("help", [], [], {"group_id": "general"}, [])
        assert "Welcome to the Chat" in result

    def test_bots_command(self, make_bot):
        bot, _ = make_bot(HelpBot)
        result = bot.handle("bots", [], [], {}, [])
        assert "Available bots" in result
        assert "@echo" in result

    def test_commands_command(self, make_bot):
        bot, _ = make_bot(HelpBot)
        result = bot.handle("commands", [], [], {}, [])
        assert "General commands" in result

    def test_groups_command(self, make_bot):
        bot, _ = make_bot(HelpBot)
        result = bot.handle("groups", [], [], {}, [])
        assert "Group Chat Commands" in result

    def test_guide_command(self, make_bot):
        bot, _ = make_bot(HelpBot)
        result = bot.handle("guide", [], [], {}, [])
        assert "Quick Start Guide" in result

    def test_unknown_returns_none(self, make_bot):
        bot, _ = make_bot(HelpBot)
        result = bot.handle("unknown", [], [], {}, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_dispatch_emits_message(self, make_bot):
        _bot, fake = make_bot(HelpBot)
        await fake.trigger("bot_authenticated", {"groups": ["general"]})
        await fake.trigger("bot_command", {
            "command": "help",
            "args": [],
            "raw_args": [],
            "message": {
                "group_id": "general", "id": "msg1", "user_id": "user1",
                "content": "@help help",
            },
            "thread_context": [],
        })
        emits = [e for e in fake.emits_for("message") if e.get("type") == "bot"]
        assert len(emits) >= 1
        assert "Welcome to the Chat" in emits[0]["content"]


class TestHelpBotExceptionSafety:
    def test_handle_does_not_raise(self, make_bot):
        bot, _ = make_bot(HelpBot)
        bot.handle("help", [], [], {}, [])
