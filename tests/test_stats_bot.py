"""Tests for StatsBot."""

from __future__ import annotations

import pytest

from meadows.bot.stats_bot import StatsBot
from meadows.protocol import EventName


class TestStatsBotConstruction:
    def test_construct(self, bot_token):
        bot = StatsBot(token=bot_token)
        assert bot.BOT_NAME == "stats"
        assert bot.stats["total_messages"] == 0

    def test_patterns_registered_on_auth(self, make_bot):
        bot, _ = make_bot(StatsBot)
        assert len(bot._registered_patterns) == 0


class TestStatsBotShouldHandle:
    def test_handles_known_commands(self, make_bot):
        bot, _ = make_bot(StatsBot)
        for cmd in ("", "stats", "group", "top", "reset", "help"):
            assert bot.should_handle(cmd, [])

    def test_rejects_unknown(self, make_bot):
        bot, _ = make_bot(StatsBot)
        assert not bot.should_handle("unknown", [])
        assert not bot.should_handle("echo", [])


class TestStatsBotHandle:
    def test_stats_dashboard(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("stats", [], [], {"group_id": "general"}, [])
        assert "Chat Statistics Dashboard" in result
        assert "Total messages" in result

    def test_stats_empty_command(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("", [], [], {"group_id": "general"}, [])
        assert "Chat Statistics Dashboard" in result

    def test_group_lists_groups(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("group", [], [], {"group_id": "general"}, [])
        assert "Groups by activity" in result

    def test_group_specific(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("group", ["general"], [], {"group_id": "general"}, [])
        assert "No messages recorded for group" in result

    def test_top_users(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("top", ["5"], [], {"group_id": "general"}, [])
        assert "Top 5 Most Active Users" in result

    def test_top_users_default(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("top", [], [], {"group_id": "general"}, [])
        assert "Top 10 Most Active Users" in result

    def test_reset(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("reset", [], [], {}, [])
        assert "Statistics have been reset" in result

    def test_help(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("help", [], [], {}, [])
        assert "Stats Bot Commands" in result

    def test_unknown_returns_none(self, make_bot):
        bot, _ = make_bot(StatsBot)
        result = bot.handle("unknown", [], [], {}, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_dispatch_stats_command(self, make_bot):
        _bot, fake = make_bot(StatsBot)
        await fake.trigger("bot_authenticated", {"groups": ["general"]})
        await fake.trigger("bot_command", {
            "command": "stats",
            "args": [],
            "raw_args": [],
            "message": {
                "group_id": "general", "id": "msg1", "user_id": "user1",
                "content": "@stats",
            },
            "thread_context": [],
        })
        emits = [e for e in fake.emits_for("message") if e.get("type") == "bot"]
        assert len(emits) >= 1
        assert "Chat Statistics Dashboard" in emits[0]["content"]


class TestStatsBotPatternRegistration:
    def test_register_pattern_queues_before_auth(self, make_bot):
        bot, _ = make_bot(StatsBot)
        bot.register_pattern("all_msgs", ".*", scope="global")
        assert len(bot._registered_patterns) == 1
        assert bot._registered_patterns[0]["name"] == "all_msgs"

    @pytest.mark.asyncio
    async def test_register_pattern_emits_after_auth(self, make_bot):
        bot, fake = make_bot(StatsBot)
        bot.register_pattern("all_msgs", ".*", scope="global")
        await fake.trigger("bot_authenticated", {"groups": ["general"]})
        emits = fake.emits_for(EventName.REGISTER_PATTERN.value)
        assert len(emits) >= 1
        assert emits[0]["name"] == "all_msgs"


class TestStatsBotExceptionSafety:
    def test_handle_does_not_raise(self, make_bot):
        bot, _ = make_bot(StatsBot)
        bot.handle("stats", [], [], {}, [])
