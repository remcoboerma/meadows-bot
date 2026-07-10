"""Dependent Bot — demonstrates async call_rpc.

This bot listens for all messages and, for each one, calls the math
service via call_rpc to compute 'add 1 1'.  It logs the result.

Usage:
    MEADOWS_JWT_TOKEN=<token> python -m meadows.bot.examples.dependent_bot
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from meadows.bot import BaseBot
from meadows.protocol import EventName, MessageType


class DependentBot(BaseBot):
    """Calls the math service via async call_rpc for every message."""

    BOT_NAME = "dependent"
    BOT_DESCRIPTION = "Demonstrates async call_rpc to math service"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = []

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.call_count = 0

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return False

    def handle(self, command, args, raw_args, message, thread_context) -> str | None:  # noqa: ARG002
        return None

    def _on_message(self, data: dict[str, Any]) -> None:
        """Schedule an async RPC call for incoming user/webhook messages only.

        BUSINESS RULE: skip RPC_REQUEST and RPC_RESPONSE to avoid loops.
        """
        msg_type = data.get("type", "")
        if msg_type in (MessageType.RPC_REQUEST.value, MessageType.RPC_RESPONSE.value):
            return
        content = data.get("content", "")
        self.log(f"Received: {content[:50]} — calling math service...")
        asyncio.create_task(self._do_math(content))

    async def _do_math(self, content: str) -> None:
        """Call the math service and log the result."""
        self.call_count += 1
        try:
            result = await self.call_rpc("service:math", f"add {self.call_count} 1", timeout=10.0)
            self.log(f"RPC result #{self.call_count}: {result}")
        except asyncio.TimeoutError:
            self.log(f"RPC call #{self.call_count} timed out")
        except Exception as e:
            self.log(f"RPC call #{self.call_count} failed: {e}")


if __name__ == "__main__":
    bot = DependentBot()
    # Subscribe to all messages to trigger RPC calls
    bot.register_label_subscription("all_msgs", {}, scope="global", deliver="message_only")
    bot.client.on(EventName.MESSAGE, bot._on_message)
    bot.connect()
