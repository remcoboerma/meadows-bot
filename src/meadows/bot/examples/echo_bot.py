#!/usr/bin/env python3
"""Echo Bot — the canonical MEADOWS example bot.

BUSINESS RULE (MEADOWS §5 line 130): the quick-start must be truly
quick. This bot is the template a groep-6 docent copies to start a new
bot. It demonstrates the full author surface (BOT_NAME, BOT_COMMANDS,
should_handle, handle) with no boilerplate beyond it.

BUSINESS RULE (MEADOWS §5 line 126): no sys.path hacks. The import is
`from meadows.bot import BaseBot` — that's it. The monolith's
echo_bot.py had a sys.path.insert; that's exactly what we leave behind.

Commands:
    @echo echo <text>   - Echo back the provided text
    @echo ping          - Check if the bot is responsive
    @echo help          - Show available commands
    @echo info          - Show bot information
"""

from __future__ import annotations

from typing import Any, ClassVar

from meadows.bot import BaseBot


class EchoBot(BaseBot):
    """Simple echo bot that repeats messages and demonstrates the bot SDK.

    BUSINESS RULE (MEADOWS §5 line 130): this is the smallest working
    bot. Copy it, rename, change BOT_COMMANDS and handle(), and you
    have a new bot. No other boilerplate.
    """

    BOT_NAME = "echo"
    BOT_DESCRIPTION = "A simple echo bot that repeats messages and provides help"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "echo", "description": "Echo back the provided text"},
        {"name": "ping", "description": "Check if the bot is responsive"},
        {"name": "help", "description": "Show available commands"},
        {"name": "info", "description": "Show bot information"},
    ]

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        """Handle all EchoBot commands.

        BUSINESS RULE (MEADOWS §5 line 130): should_handle is one of
        the two things an author writes. Here it's a simple allowlist.
        """
        return command in {"echo", "ping", "help", "info"}

    def handle(
        self,
        command: str,
        args: list[str],
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],
    ) -> str | None:
        """Process EchoBot commands.

        BUSINESS RULE (MEADOWS §5 line 130): handle is the second thing
        an author writes. Returning a string emits a message;
        returning None stays silent.
        """
        if command == "echo":
            # BUSINESS RULE (MEADOWS §5 line 130): extract_quoted_string
            # is the SDK helper for "join args into a phrase." Using it
            # instead of " ".join(args) removes a line an author could
            # get wrong.
            text = self.extract_quoted_string(args)
            if not text:
                return "Usage: @echo echo <text to echo>"
            return f"Echo: {text}"

        if command == "ping":
            # BUSINESS RULE (MEADOWS §5 line 132): address the user by
            # name — get_sender_info normalizes the message shape so
            # the author doesn't have to know it.
            sender = self.get_sender_info(message)
            return f"Pong! Hello {sender['display_name']}, I'm alive and ready to serve."

        if command == "help":
            # BUSINESS RULE (MEADOWS §5 line 130): format_help_response
            # is the one-liner for the most common bot feature.
            return self.format_help_response()

        if command == "info":
            context_msg = f"\n\nCurrent thread has {len(thread_context)} messages"
            return f"I am {self.BOT_NAME}, a {self.BOT_DESCRIPTION}.{context_msg}"

        return None


if __name__ == "__main__":
    # BUSINESS RULE (MEADOWS §5 line 130): the run line is one
    # statement. A docent copies this file, changes the class, and
    # the bot runs.
    EchoBot().connect()
