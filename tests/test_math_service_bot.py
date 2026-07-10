"""Tests for MathServiceBot — RPC calculation service."""

from __future__ import annotations

from meadows.bot.examples.math_service_bot import MathServiceBot
from meadows.protocol import EventName, MessageType


class TestMathServiceBotConstruction:
    def test_bot_name(self, make_bot):
        bot, _ = make_bot(MathServiceBot)
        assert bot.BOT_NAME == "math-svc"

    def test_initial_state(self, make_bot):
        bot, _ = make_bot(MathServiceBot)
        assert bot.calculations == 0
        assert bot.errors == 0


class TestMathServiceBotCommands:
    def test_should_handle_known(self, make_bot):
        bot, _ = make_bot(MathServiceBot)
        assert bot.should_handle("help", []) is True
        assert bot.should_handle("stats", []) is True

    def test_stats_shows_counts(self, make_bot):
        bot, _ = make_bot(MathServiceBot)
        bot.calculations = 5
        bot.errors = 1
        result = bot.handle("stats", [], [], {}, [])
        assert "Calculations: 5" in result
        assert "Errors: 1" in result


def _make_rpc_request(content: str, request_id: str = "req-1") -> dict:
    return {
        "type": MessageType.RPC_REQUEST.value,
        "content": content,
        "labels": [["bot-caller", "service:math", "1.0.0", {"request_id": request_id}]],
        "user_id": "bot-caller",
        "group_id": "general",
    }


class TestMathServiceBotRPC:
    def test_add(self, make_bot):
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("add 2 3"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["content"] == "5"
        assert msg["type"] == MessageType.RPC_RESPONSE.value

    def test_subtract(self, make_bot):
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("subtract 10 3"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["content"] == "7"

    def test_multiply(self, make_bot):
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("multiply 4 5"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["content"] == "20"

    def test_divide(self, make_bot):
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("divide 10 2"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["content"] == "5"

    def test_divide_fraction(self, make_bot):
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("divide 7 2"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["content"] == "3.5"

    def test_power(self, make_bot):
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("power 2 8"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["content"] == "256"

    def test_divide_by_zero(self, make_bot):
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("divide 1 0"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["content"].startswith("Error:")
        assert bot.errors == 1

    def test_invalid_operation(self, make_bot):
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("foobar"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["content"].startswith("Error:")
        assert bot.errors == 1

    def test_request_id_correlation(self, make_bot):
        """BUSINESS RULE (§2.10): response carries same request_id."""
        bot, fake = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("add 1 1", request_id="my-req-42"))
        msg = fake.emits_for(EventName.MESSAGE)[0]
        assert msg["labels"][0][3]["request_id"] == "my-req-42"

    def test_increments_counters(self, make_bot):
        bot, _ = make_bot(MathServiceBot)
        bot._on_rpc_request(_make_rpc_request("add 1 2"))
        bot._on_rpc_request(_make_rpc_request("bad input"))
        assert bot.calculations == 1
        assert bot.errors == 1
