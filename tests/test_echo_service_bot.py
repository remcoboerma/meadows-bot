"""Tests for EchoServiceBot — the minimal RPC service example.

BUSINESS RULE (MEADOWS-labeling-intent §2.10): tests verify that
the service bot correctly handles RPC_REQUEST messages and sends
RPC_RESPONSE with the correct request_id for correlation.
"""

from __future__ import annotations

from meadows.bot.examples.echo_service_bot import EchoServiceBot
from meadows.protocol import EventName, MessageType


class TestEchoServiceBotConstruction:
    def test_bot_name(self, make_bot):
        bot, _ = make_bot(EchoServiceBot)
        assert bot.BOT_NAME == "echo-svc"

    def test_initial_state(self, make_bot):
        bot, _ = make_bot(EchoServiceBot)
        assert bot.requests_handled == 0


class TestEchoServiceBotCommands:
    def test_should_handle_help(self, make_bot):
        bot, _ = make_bot(EchoServiceBot)
        assert bot.should_handle("help", []) is True

    def test_should_reject_unknown(self, make_bot):
        bot, _ = make_bot(EchoServiceBot)
        assert bot.should_handle("echo", []) is False

    def test_help_returns_formatted(self, make_bot):
        bot, _ = make_bot(EchoServiceBot)
        result = bot.handle("help", [], [], {}, [])
        assert "Echo-svc Bot Commands:" in result


class TestEchoServiceBotRPC:
    def test_rpc_request_produces_response(self, make_bot):
        """BUSINESS RULE (§2.10): service bot receives RPC_REQUEST
        and sends RPC_RESPONSE with matching request_id.
        """
        bot, fake = make_bot(EchoServiceBot)
        bot._on_rpc_request({
            "type": MessageType.RPC_REQUEST.value,
            "content": "hello world",
            "labels": [["bot-caller", "service:echo", "1.0.0", {"request_id": "req-123"}]],
            "user_id": "bot-caller",
            "group_id": "general",
        })

        emits = fake.emits_for(EventName.MESSAGE)
        assert len(emits) == 1
        msg = emits[0]
        assert msg["type"] == MessageType.RPC_RESPONSE.value
        assert msg["content"] == "Echo: hello world"
        assert msg["labels"][0][3]["request_id"] == "req-123"

    def test_rpc_request_without_request_id_ignored(self, make_bot):
        """Missing request_id → silently ignored."""
        bot, fake = make_bot(EchoServiceBot)
        bot._on_rpc_request({
            "type": MessageType.RPC_REQUEST.value,
            "content": "hello",
            "labels": [["bot-caller", "service:echo", "1.0.0"]],
            "user_id": "bot-caller",
            "group_id": "general",
        })
        assert fake.emits_for(EventName.MESSAGE) == []

    def test_non_rpc_message_ignored(self, make_bot):
        """Regular messages are not processed as RPC."""
        bot, fake = make_bot(EchoServiceBot)
        bot._on_rpc_request({
            "type": MessageType.USER.value,
            "content": "hello",
            "user_id": "user-alice",
            "group_id": "general",
        })
        assert fake.emits_for(EventName.MESSAGE) == []

    def test_increments_counter(self, make_bot):
        bot, _ = make_bot(EchoServiceBot)
        bot._on_rpc_request({
            "type": MessageType.RPC_REQUEST.value,
            "content": "test",
            "labels": [["bot-caller", "service:echo", "1.0.0", {"request_id": "r1"}]],
            "user_id": "bot-caller",
            "group_id": "general",
        })
        bot._on_rpc_request({
            "type": MessageType.RPC_REQUEST.value,
            "content": "test2",
            "labels": [["bot-caller", "service:echo", "1.0.0", {"request_id": "r2"}]],
            "user_id": "bot-caller",
            "group_id": "general",
        })
        assert bot.requests_handled == 2

    def test_subscription_registered(self, make_bot):
        bot, _ = make_bot(EchoServiceBot)
        bot.register_label_subscription(
            "echo-service",
            {"regex_match": [{"var": "label"}, "^service:echo$"]},
            scope="global",
            deliver="message_only",
        )
        assert len(bot._registered_label_subscriptions) == 1
        assert bot._registered_label_subscriptions[0]["deliver"] == "message_only"
