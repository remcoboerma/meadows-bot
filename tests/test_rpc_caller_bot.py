"""Tests for RPCCallerBot — demonstrates calling RPC services."""

from __future__ import annotations

from meadows.bot.examples.rpc_caller_bot import RPCCallerBot
from meadows.protocol import EventName, MessageType


class TestRPCCallerBotConstruction:
    def test_bot_name(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        assert bot.BOT_NAME == "caller"

    def test_initial_state(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        assert bot.rpc_calls == 0
        assert bot.rpc_responses == 0
        assert bot.rpc_errors == 0


class TestRPCCallerBotCommands:
    def test_should_handle_known(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        assert bot.should_handle("echo", []) is True
        assert bot.should_handle("math", []) is True
        assert bot.should_handle("help", []) is True
        assert bot.should_handle("stats", []) is True

    def test_should_reject_unknown(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        assert bot.should_handle("ping", []) is False

    def test_echo_no_args_returns_usage(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        result = bot.handle("echo", [], [], {}, [])
        assert "Usage:" in result

    def test_math_no_args_returns_usage(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        result = bot.handle("math", [], [], {}, [])
        assert "Usage:" in result

    def test_stats_returns_counts(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        bot.rpc_calls = 3
        bot.rpc_responses = 2
        result = bot.handle("stats", [], [], {}, [])
        assert "Calls sent: 3" in result
        assert "Responses received: 2" in result


class TestRPCCallerBotRPC:
    def test_echo_sends_rpc_request(self, make_bot):
        """BUSINESS RULE (§2.10): caller sends RPC_REQUEST with labels."""
        bot, fake = make_bot(RPCCallerBot)
        result = bot.handle("echo", ["hello", "world"], [], {}, [])
        assert result is None  # async response

        emits = fake.emits_for(EventName.MESSAGE)
        assert len(emits) == 1
        msg = emits[0]
        assert msg["type"] == MessageType.RPC_REQUEST.value
        assert msg["content"] == "hello world"
        assert msg["labels"][0][1] == "service:echo"
        assert msg["labels"][0][3]["request_id"]  # auto-generated

    def test_math_sends_rpc_request(self, make_bot):
        bot, fake = make_bot(RPCCallerBot)
        result = bot.handle("math", ["add", "2", "3"], [], {}, [])
        assert result is None

        emits = fake.emits_for(EventName.MESSAGE)
        assert len(emits) == 1
        msg = emits[0]
        assert msg["type"] == MessageType.RPC_REQUEST.value
        assert msg["content"] == "add 2 3"
        assert msg["labels"][0][1] == "service:math"

    def test_rpc_response_dispatched(self, make_bot):
        """RPC_RESPONSE messages are dispatched to the handler."""
        bot, _ = make_bot(RPCCallerBot)
        bot._on_rpc_response({
            "type": MessageType.RPC_RESPONSE.value,
            "content": "Echo: hello",
            "labels": [["bot-echo-svc", "service:echo-response", "1.0.0", {"request_id": "req-1"}]],
        })
        assert bot.rpc_responses == 1

    def test_rpc_error_counted(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        bot._on_rpc_response({
            "type": MessageType.RPC_RESPONSE.value,
            "content": "Error: division by zero",
            "labels": [["bot-math-svc", "service:math-response", "1.0.0", {"request_id": "req-2"}]],
        })
        assert bot.rpc_responses == 1
        assert bot.rpc_errors == 1

    def test_non_rpc_ignored(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        bot._on_rpc_response({
            "type": MessageType.USER.value,
            "content": "hello",
        })
        assert bot.rpc_responses == 0

    def test_increments_call_counter(self, make_bot):
        bot, _ = make_bot(RPCCallerBot)
        bot.handle("echo", ["test"], [], {}, [])
        bot.handle("math", ["add", "1", "2"], [], {}, [])
        assert bot.rpc_calls == 2
