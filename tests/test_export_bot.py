"""Tests for ExportBot."""

from __future__ import annotations

import pytest

from meadows.bot.export_bot import ExportBot


class TestExportBotConstruction:
    def test_construct(self, bot_token):
        bot = ExportBot(token=bot_token)
        assert bot.BOT_NAME == "export"
        assert len(bot.BOT_COMMANDS) == 2


class TestExportBotShouldHandle:
    def test_handles_known_commands(self, make_bot):
        bot, _ = make_bot(ExportBot)
        for cmd in ("md", "help", ""):
            assert bot.should_handle(cmd, [])

    def test_rejects_unknown(self, make_bot):
        bot, _ = make_bot(ExportBot)
        assert not bot.should_handle("pdf", [])
        assert not bot.should_handle("unknown", [])


class TestExportBotHandle:
    def test_help(self, make_bot):
        bot, _ = make_bot(ExportBot)
        result = bot.handle("help", [], [], {"group_id": "general"}, [])
        assert "Export Bot" in result

    def test_empty_command_returns_help(self, make_bot):
        bot, _ = make_bot(ExportBot)
        result = bot.handle("", [], [], {"group_id": "general"}, [])
        assert "Export Bot" in result

    def test_no_thread_context(self, make_bot):
        bot, _ = make_bot(ExportBot)
        result = bot.handle("md", [], [], {"group_id": "general"}, [])
        assert "Geen berichten" in result

    def test_export_md_with_messages(self, make_bot):
        bot, _ = make_bot(ExportBot)
        thread_context = [
            {
                "type": "user", "username": "Alice", "content": "Hallo!",
                "timestamp": "2024-01-15T10:00:00Z",
            },
            {
                "type": "bot", "bot_name": "echo", "content": "Echo: Hallo!",
                "timestamp": "2024-01-15T10:00:05Z",
            },
        ]
        result = bot.handle(
            "md", [], [], {"group_id": "general"}, thread_context
        )
        assert "Export voltooid" in result
        assert "Alice" in result
        assert "@echo" in result
        assert "Hallo!" in result

    def test_export_uses_tempdir(self, make_bot, tmp_path):  # noqa: ARG002
        bot, _ = make_bot(ExportBot)
        thread_context = [
            {
                "type": "user", "username": "Test", "content": "Message",
                "timestamp": "2024-01-15T10:00:00Z",
            },
        ]
        result = bot.handle(
            "md", [], [], {"group_id": "testgroup"}, thread_context
        )
        assert "Export voltooid" in result
        assert "Markdown" in result

    def test_format_author_user(self, make_bot):
        bot, _ = make_bot(ExportBot)
        author = bot._format_author({"type": "user", "username": "Alice"})
        assert author == "Alice"

    def test_format_author_bot(self, make_bot):
        bot, _ = make_bot(ExportBot)
        author = bot._format_author({"type": "bot", "bot_name": "echo"})
        assert author == "@echo"

    def test_format_author_email(self, make_bot):
        bot, _ = make_bot(ExportBot)
        author = bot._format_author({
            "type": "user", "email": "alice@example.com"
        })
        assert author == "alice"

    def test_format_timestamp(self, make_bot):
        bot, _ = make_bot(ExportBot)
        formatted = bot._format_timestamp("2024-01-15T10:00:00Z")
        assert "15-01-2024" in formatted

    def test_format_timestamp_invalid(self, make_bot):
        bot, _ = make_bot(ExportBot)
        formatted = bot._format_timestamp("invalid")
        assert formatted == "invalid"

    @pytest.mark.asyncio
    async def test_dispatch_export_command(self, make_bot):
        _bot, fake = make_bot(ExportBot)
        await fake.trigger("bot_authenticated", {"groups": ["general"]})
        await fake.trigger("bot_command", {
            "command": "md",
            "args": [],
            "raw_args": [],
            "message": {
                "group_id": "general", "id": "msg1", "user_id": "user1",
                "content": "@export md",
            },
            "thread_context": [
                {
                    "type": "user", "username": "Test", "content": "Hello",
                    "timestamp": "2024-01-15T10:00:00Z",
                },
            ],
        })
        emits = [e for e in fake.emits_for("message") if e.get("type") == "bot"]
        assert len(emits) >= 1
        assert "Export voltooid" in emits[0]["content"]


class TestExportBotExceptionSafety:
    def test_handle_does_not_raise(self, make_bot):
        bot, _ = make_bot(ExportBot)
        bot.handle("md", [], [], {"group_id": "general"}, [])
