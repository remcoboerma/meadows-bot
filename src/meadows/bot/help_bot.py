#!/usr/bin/env python3
"""Help Bot — provides system help and documentation.

BUSINESS RULE (MEADOWS §5 line 130): this is the simplest production bot.
It proves that BaseBot is importable and should_handle/handle work with
no extra dependencies. A docent can copy this file, change BOT_NAME and
BOT_COMMANDS, and have a new info bot.

Commands:
    @help help       - Show general help message
    @help bots       - List available bots
    @help commands   - Show all available commands
    @help groups     - Show group management help
    @help guide      - Show quick start guide
"""

from __future__ import annotations

from typing import Any, ClassVar

from meadows.bot import BaseBot


class HelpBot(BaseBot):
    """Provides help and documentation about the chat system.

    BUSINESS RULE (MEADOWS §5 line 130): this is the first bot a new
    user encounters. Each command returns a static text block that
    explains a different aspect of the system. No external dependencies.
    """

    BOT_NAME = "help"
    BOT_DESCRIPTION = "General help bot that explains how to use the chat system"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "help", "description": "Show this help message"},
        {"name": "bots", "description": "List all available bots"},
        {"name": "commands", "description": "Show all available commands"},
        {"name": "groups", "description": "Show how to create and join groups"},
        {"name": "guide", "description": "Show quick start guide"},
    ]

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        """Handle all HelpBot commands."""
        return command in {"help", "bots", "commands", "groups", "guide"}

    def handle(
        self,
        command: str,
        args: list[str],  # noqa: ARG002
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],  # noqa: ARG002
        thread_context: list[dict[str, Any]],  # noqa: ARG002
    ) -> str | None:
        """Process HelpBot commands — return static help text for each command."""
        if command == "help":
            return (
                "Welcome to the Chat!\n\n"
                "To address a bot, use @botname followed by a command.\n"
                "Example: @echo ping\n\n"
                "Use @help to see this message."
            )
        if command == "bots":
            return (
                "Available bots in this chat:\n"
                "  @echo - Echo bot (repeats messages)\n"
                "  @rag - RAG search bot for media fragments\n"
                "  @ollama - AI assistant using local LLM\n"
                "  @help - This help bot\n\n"
                "Use @botname help to see each bot's commands."
            )
        if command == "commands":
            return (
                "General commands:\n"
                "  Type any message to chat with the group\n"
                "  @botname command - Address a bot\n"
                "  @botname help --all - Get full thread context\n\n"
                "Bot commands use --flags for options:\n"
                "  --all : Use entire thread history instead of last 30 messages"
            )
        if command == "groups":
            return (
                "Group Chat Commands:\n"
                "  Groups are created automatically when you create them\n"
                "  Use the sidebar to see all groups\n"
                "  Click on a group name to join it\n"
                "  All groups are public and visible to everyone"
            )
        if command == "guide":
            return (
                "Quick Start Guide:\n"
                "1. Join the 'general' group or create a new one\n"
                "2. Chat with others in the group\n"
                "3. Address bots with @botname command\n"
                "4. Use --all flag for bot commands to include full history\n"
                "Example: @rag video about history --all"
            )
        return None


if __name__ == "__main__":
    HelpBot().connect()
