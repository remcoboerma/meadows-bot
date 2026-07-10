#!/usr/bin/env python3
"""Echo Service Bot — minimal RPC service example.

BUSINESS RULE (MEADOWS-labeling-intent §2.10): this bot demonstrates
the service side of bot-to-bot RPC.  It subscribes to its service
label ``("bot-echo-svc", "service:echo", "1.0.0")`` and responds to
RPC_REQUEST messages by echoing the content back as RPC_RESPONSE.

The flow:
  1. Caller sends RPC_REQUEST with label "service:echo"
  2. Server routes via label subscription to this bot
  3. This bot receives the MESSAGE (type=rpc_request)
  4. This bot sends RPC_RESPONSE with the same request_id
  5. Server routes the response back to the caller

Usage:
    MEADOWS_JWT_TOKEN=<token> python -m meadows.bot.examples.echo_service_bot
"""

from __future__ import annotations

from typing import Any, ClassVar

from meadows.bot import BaseBot
from meadows.protocol import EventName, MessageType


class EchoServiceBot(BaseBot):
    """RPC service that echoes back any request.

    Subscribes to "service:echo" labels with deliver=message_only.
    When it receives an RPC_REQUEST, it sends back an RPC_RESPONSE
    with the same content and request_id.
    """

    BOT_NAME = "echo-svc"
    BOT_DESCRIPTION = "RPC echo service — echoes back any request"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "help", "description": "Show available commands"},
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.requests_handled = 0
        # Listen for incoming RPC_REQUEST messages via label subscription
        self.client.on(EventName.MESSAGE, self._on_rpc_request)

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return command in {"help"}

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
        return None

    def _on_rpc_request(self, data: dict[str, Any]) -> None:
        """Handle incoming RPC_REQUEST messages.

        BUSINESS RULE (§2.10): the service bot receives RPC_REQUEST
        via label subscription (deliver=message_only).  It extracts
        the request_id from the label metadata and sends back an
        RPC_RESPONSE with the same request_id.
        """
        if data.get("type") != MessageType.RPC_REQUEST.value:
            return

        content = data.get("content", "")
        labels = data.get("labels", [])

        # Extract request_id from label metadata
        request_id = None
        for lbl in labels:
            if len(lbl) > 3 and isinstance(lbl[3], dict):
                request_id = lbl[3].get("request_id")
                if request_id:
                    break

        if not request_id:
            self.log(f"RPC_REQUEST without request_id, ignoring: {content[:50]}")
            return

        self.requests_handled += 1
        self.log(f"Echo request #{self.requests_handled}: {content[:50]}")

        # Send back the echoed response to the same group as the request
        self.emit_rpc_response(
            request_id=request_id,
            content=f"Echo: {content}",
            origin="bot-echo-svc",
            service_label="service:echo-response",
            group_id=data.get("group_id", "general"),
        )


if __name__ == "__main__":
    bot = EchoServiceBot()
    # Subscribe to our service label — RPC_REQUEST messages with this
    # label will be delivered to us via label routing.
    bot.register_label_subscription(
        "echo-service",
        {
            "and": [
                {"regex_match": [{"var": "origin"}, "^bot-echo-svc$"]},
                {"regex_match": [{"var": "label"}, "^service:echo$"]},
                {"semver_match": ["^1.0.0", {"var": "semver"}]},
            ]
        },
        scope="global",
        deliver="message_only",
    )
    bot.connect()
