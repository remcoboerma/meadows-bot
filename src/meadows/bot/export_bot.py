#!/usr/bin/env python3
"""Export Bot — Export chat threads to Markdown.

BUSINESS RULE (MEADOWS §5 line 130): this bot proves that a bot can
format thread context into a downloadable file. Markdown-only per the
migration plan — PDF and DOCX require fpdf2/python-docx and are
postponed.

BUSINESS RULE (MEADOWS §7 line 152): the monolith's export_bot read
JSONL files directly from the server's filesystem. The SDK version
uses only the thread_context the server sends, proving the protocol
envelope is sufficient for export.

Usage:
    @export         - Export current thread as Markdown
    @export help    - Show help
"""

from __future__ import annotations

import pathlib
import tempfile
from datetime import datetime
from typing import Any, ClassVar

from meadows.bot import BaseBot


class ExportBot(BaseBot):
    """Export chat threads to Markdown format.

    Uses thread_context from the server — no direct filesystem access.
    Writes to a temporary directory and returns the file path and
    content in the response.
    """

    BOT_NAME = "export"
    BOT_DESCRIPTION = "Exporteer chat geschiedenis naar Markdown"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "md", "description": "Export als Markdown"},
        {"name": "help", "description": "Toon help"},
    ]

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return command in {"md", "help", ""}

    def handle(
        self,
        command: str,
        args: list[str],
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],
    ) -> str | None:
        if command == "help" or (command == "" and not args):
            return self._show_help()

        if not thread_context:
            return "Geen berichten gevonden om te exporteren. Stuur eerst wat berichten in deze thread."

        if command == "md":
            return self._export_markdown(message, thread_context)

        return None

    def _show_help(self) -> str:
        return (
            "**Export Bot**\n\n"
            "Exporteer de huidige thread naar Markdown.\n\n"
            "**Commando's:**\n"
            "- `@export md` - Exporteer als Markdown\n"
        )

    def _export_markdown(self, message: dict[str, Any], thread_context: list[dict[str, Any]]) -> str:
        group_id = message.get("group_id", "general")
        now = datetime.now()

        lines = [
            f"# Chat Export: {group_id}",
            "",
            f"*Geëxporteerd op {now.strftime('%d-%m-%Y %H:%M')}*",
            "",
            "---",
            "",
        ]

        for msg in thread_context:
            author = self._format_author(msg)
            timestamp = self._format_timestamp(msg.get("timestamp", ""))
            content = msg.get("content", "")

            lines.append(f"### {author}")
            lines.append(f"*{timestamp}*")
            lines.append("")
            lines.append(content if content else "*geen inhoud*")
            lines.append("")
            lines.append("---")
            lines.append("")

        markdown = "\n".join(lines)

        export_dir = pathlib.Path(tempfile.mkdtemp(prefix="meadows_export_"))
        filename = f"export_{group_id}_{now.strftime('%Y%m%d_%H%M%S')}.md"
        filepath = export_dir / filename
        filepath.write_text(markdown, encoding="utf-8")

        self.log(f"Exported Markdown: {filepath} ({len(thread_context)} messages)")

        return (
            f"**Export voltooid!**\n\n"
            f"- **Berichten:** {len(thread_context)}\n"
            f"- **Formaat:** Markdown\n\n"
            f"```markdown\n{markdown[:3000]}"
            + ("\n..." if len(markdown) > 3000 else "")
            + "\n```"
        )

    def _format_author(self, msg: dict[str, Any]) -> str:
        if msg.get("type") == "bot":
            bot_name = msg.get("bot_name", "bot")
            return f"@{bot_name}"
        username = msg.get("username", "")
        email = msg.get("email", "")
        if username:
            return username
        if email:
            return email.split("@")[0]
        return msg.get("user_id", "unknown")

    def _format_timestamp(self, timestamp: str) -> str:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%d-%m-%Y %H:%M")
        except Exception:
            return timestamp


if __name__ == "__main__":
    ExportBot().connect()
