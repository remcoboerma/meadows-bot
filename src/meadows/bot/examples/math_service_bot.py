#!/usr/bin/env python3
"""Math Service Bot — RPC service for calculations.

BUSINESS RULE (MEADOWS-labeling-intent §2.10): this bot demonstrates
a more realistic RPC service.  It offers arithmetic operations as a
service that other bots can call via RPC_REQUEST.

Supported operations (sent as content):
  "add 2 3"      → "5"
  "multiply 4 5" → "20"
  "subtract 10 3"→ "7"
  "divide 10 2"  → "5.0"
  "power 2 8"    → "256"

Usage:
    MEADOWS_JWT_TOKEN=<token> python -m meadows.bot.examples.math_service_bot
"""

from __future__ import annotations

import operator
from typing import Any, ClassVar

from meadows.bot import BaseBot
from meadows.protocol import EventName, MessageType

OPERATIONS = {
    "add": operator.add,
    "subtract": operator.sub,
    "multiply": operator.mul,
    "divide": operator.truediv,
    "power": operator.pow,
}


class MathServiceBot(BaseBot):
    """RPC service for arithmetic operations.

    BUSINESS RULE (§2.10): the service bot is a passive listener.  It
    subscribes to its service label and responds to requests.  It never
    initiates conversations.
    """

    BOT_NAME = "math-svc"
    BOT_DESCRIPTION = "RPC math service — add, subtract, multiply, divide, power"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "help", "description": "Show available commands"},
        {"name": "stats", "description": "Show calculation statistics"},
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.calculations = 0
        self.errors = 0
        self.client.on(EventName.MESSAGE, self._on_rpc_request)

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return command in {"help", "stats"}

    def handle(
        self,
        command: str,
        args: list[str],  # noqa: ARG002
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],  # noqa: ARG002
        thread_context: list[dict[str, Any]],  # noqa: ARG002
    ) -> str | None:
        if command == "help":
            return self.format_help_response()
        if command == "stats":
            return f"Math Service Stats:\n  Calculations: {self.calculations}\n  Errors: {self.errors}"
        return None

    def _on_rpc_request(self, data: dict[str, Any]) -> None:
        """Handle incoming RPC_REQUEST messages.

        Parses "operation arg1 arg2" from content, computes the result,
        and sends back an RPC_RESPONSE.
        """
        if data.get("type") != MessageType.RPC_REQUEST.value:
            return

        content = data.get("content", "").strip()
        labels = data.get("labels", [])

        request_id = None
        for lbl in labels:
            if len(lbl) > 3 and isinstance(lbl[3], dict):
                request_id = lbl[3].get("request_id")
                if request_id:
                    break

        if not request_id:
            return

        reply_group = data.get("group_id", "general")
        parts = content.split()
        if len(parts) != 3 or parts[0] not in OPERATIONS:
            self.errors += 1
            self.emit_rpc_response(
                request_id=request_id,
                content=f"Error: expected 'operation a b', got '{content}'",
                origin="bot-math-svc",
                service_label="service:math-response",
                group_id=reply_group,
            )
            return

        op_name, a_str, b_str = parts
        try:
            a, b = float(a_str), float(b_str)
            result = OPERATIONS[op_name](a, b)
            # Format as int if the result is a whole number
            result_str = str(int(result)) if result == int(result) else str(result)
            self.calculations += 1
            self.log(f"Calc #{self.calculations}: {op_name}({a}, {b}) = {result_str}")
            self.emit_rpc_response(
                request_id=request_id,
                content=result_str,
                origin="bot-math-svc",
                service_label="service:math-response",
                group_id=reply_group,
            )
        except (ValueError, ZeroDivisionError) as e:
            self.errors += 1
            self.emit_rpc_response(
                request_id=request_id,
                content=f"Error: {e}",
                origin="bot-math-svc",
                service_label="service:math-response",
                group_id=reply_group,
            )


if __name__ == "__main__":
    bot = MathServiceBot()
    bot.register_label_subscription(
        "math-service",
        {
            "and": [
                {"regex_match": [{"var": "origin"}, "^bot-math-svc$"]},
                {"regex_match": [{"var": "label"}, "^service:math$"]},
                {"semver_match": [">=1.0.0", {"var": "semver"}]},
            ]
        },
        scope="global",
        deliver="message_only",
    )
    bot.connect()
