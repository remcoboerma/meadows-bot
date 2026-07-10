#!/usr/bin/env python3
"""RPC Caller Bot — demonstrates calling RPC services.

BUSINESS RULE (MEADOWS-labeling-intent §2.10): this bot demonstrates
the caller side of bot-to-bot RPC.  It sends RPC_REQUEST messages to
service bots and receives RPC_RESPONSE via label subscriptions.

Commands:
    @caller echo <text>     - Call the echo service
    @caller math <op> <a> <b> - Call the math service (add/subtract/multiply/divide/power)
    @caller help            - Show available commands
    @caller stats           - Show RPC statistics

The correlation flow:
  1. Bot sends RPC_REQUEST via emit_rpc_request() → gets request_id
  2. Bot registers callback via on_rpc_response(request_id)
  3. Server routes RPC_RESPONSE via labels → callback fires

Usage:
    MEADOWS_JWT_TOKEN=<token> python -m meadows.bot.examples.rpc_caller_bot
"""

from __future__ import annotations

from typing import Any, ClassVar

from meadows.bot import BaseBot
from meadows.protocol import EventName, MessageType


class RPCCallerBot(BaseBot):
    """Bot that calls RPC services and displays results.

    Demonstrates:
    - Sending RPC_REQUEST with labels
    - Subscribing to RPC_RESPONSE labels
    - Correlating responses by request_id
    """

    BOT_NAME = "caller"
    BOT_DESCRIPTION = "Calls RPC services (echo, math) and displays results"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "echo", "description": "Call the echo service: @caller echo <text>"},
        {"name": "math", "description": "Call the math service: @caller math <op> <a> <b>"},
        {"name": "help", "description": "Show available commands"},
        {"name": "stats", "description": "Show RPC statistics"},
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.rpc_calls = 0
        self.rpc_responses = 0
        self.rpc_errors = 0
        # Listen for RPC_RESPONSE messages via label subscription
        self.client.on(EventName.MESSAGE, self._on_rpc_response)

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return command in {"echo", "math", "help", "stats"}

    def handle(
        self,
        command: str,
        args: list[str],
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],  # noqa: ARG002
        thread_context: list[dict[str, Any]],  # noqa: ARG002
    ) -> str | None:
        if command == "help":
            return self.format_help_response()

        if command == "stats":
            return (
                f"RPC Caller Stats:\n"
                f"  Calls sent: {self.rpc_calls}\n"
                f"  Responses received: {self.rpc_responses}\n"
                f"  Errors: {self.rpc_errors}"
            )

        if command == "echo":
            text = self.extract_quoted_string(args)
            if not text:
                return "Usage: @caller echo <text to echo>"
            request_id = self.emit_rpc_request(
                service_label="service:echo",
                content=text,
                origin="bot-echo-svc",
            )
            self.rpc_calls += 1
            self.log(f"Sent echo request {request_id}: {text[:50]}")
            return None  # Response comes asynchronously via label

        if command == "math":
            if len(args) < 3:
                return "Usage: @caller math <operation> <a> <b>\nOperations: add, subtract, multiply, divide, power"
            op, a, b = args[0], args[1], args[2]
            request_id = self.emit_rpc_request(
                service_label="service:math",
                content=f"{op} {a} {b}",
                origin="bot-math-svc",
            )
            self.rpc_calls += 1
            self.log(f"Sent math request {request_id}: {op} {a} {b}")
            return None  # Response comes asynchronously via label

        return None

    def _on_rpc_response(self, data: dict[str, Any]) -> None:
        """Handle incoming RPC_RESPONSE messages.

        BUSINESS RULE (§2.10): correlation uses request_id in label
        metadata.  The caller matches the response to the original
        request.
        """
        if data.get("type") != MessageType.RPC_RESPONSE.value:
            return

        content = data.get("content", "")
        labels = data.get("labels", [])

        request_id = None
        for lbl in labels:
            if len(lbl) > 3 and isinstance(lbl[3], dict):
                request_id = lbl[3].get("request_id")
                if request_id:
                    break

        self.rpc_responses += 1
        if content.startswith("Error:"):
            self.rpc_errors += 1

        self.log(f"RPC response (req={request_id}): {content}")


if __name__ == "__main__":
    bot = RPCCallerBot()
    # Subscribe to echo service responses
    bot.register_label_subscription(
        "echo-responses",
        {
            "and": [
                {"regex_match": [{"var": "origin"}, "^bot-echo-svc$"]},
                {"regex_match": [{"var": "label"}, "^service:echo-response$"]},
                {"semver_match": [">=1.0.0", {"var": "semver"}]},
            ]
        },
        scope="global",
        deliver="message_only",
    )
    # Subscribe to math service responses
    bot.register_label_subscription(
        "math-responses",
        {
            "and": [
                {"regex_match": [{"var": "origin"}, "^bot-math-svc$"]},
                {"regex_match": [{"var": "label"}, "^service:math-response$"]},
                {"semver_match": [">=1.0.0", {"var": "semver"}]},
            ]
        },
        scope="global",
        deliver="message_only",
    )
    bot.connect()
