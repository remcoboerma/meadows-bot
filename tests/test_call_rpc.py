"""Tests for call_rpc — the async RPC author surface.

BUSINESS RULE (§2.10): call_rpc lives on MeadowClient and is
delegated to from BaseBot.  These tests pin the contract using
FakeMeadowClient without a real server.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest

from meadows.bot import BaseBot
from meadows.protocol import EventName, MessageType


class _CallerBot(BaseBot):
    """A bot that calls call_rpc and records the result."""

    BOT_NAME = "caller"
    BOT_DESCRIPTION = "test caller"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = []

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.results: list[str] = []
        self.errors: list[BaseException] = []

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return False

    def handle(self, command, args, raw_args, message, thread_context) -> str | None:  # noqa: ARG002
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_rpc_resolves_on_response(make_bot):
    """call_rpc should return the response content when the future is resolved."""
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    async def do_call():
        return await bot.call_rpc("service:echo", "hello", timeout=5.0)

    task = asyncio.create_task(do_call())
    await asyncio.sleep(0.05)

    # Find the request_id from the emitted RPC_REQUEST
    emits = fake.emits_for(EventName.MESSAGE)
    assert len(emits) == 1
    request_msg = emits[0]
    assert request_msg["type"] == MessageType.RPC_REQUEST.value

    request_id = request_msg["labels"][0][3]["request_id"]

    # Resolve the future via the fake's helper
    fake.resolve_rpc(request_id, "Echo: hello")

    result = await task
    assert result == "Echo: hello"


@pytest.mark.asyncio
async def test_call_rpc_timeout(make_bot):
    """call_rpc should raise asyncio.TimeoutError if no response arrives."""
    bot, _fake = make_bot(_CallerBot)
    bot.authenticated = True

    with pytest.raises(asyncio.TimeoutError):
        await bot.call_rpc("service:echo", "hello", timeout=0.1)


@pytest.mark.asyncio
async def test_call_rpc_ignores_unrelated_responses(make_bot):
    """call_rpc should not resolve from a response with a different request_id."""
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    async def do_call():
        return await bot.call_rpc("service:echo", "hello", timeout=5.0)

    task = asyncio.create_task(do_call())
    await asyncio.sleep(0.05)

    emits = fake.emits_for(EventName.MESSAGE)
    request_id = emits[0]["labels"][0][3]["request_id"]

    # Resolve a DIFFERENT request_id — should be ignored
    fake.resolve_rpc("wrong-id", "not for you")
    assert not task.done()

    # Now resolve the correct one
    fake.resolve_rpc(request_id, "correct answer")

    result = await task
    assert result == "correct answer"


@pytest.mark.asyncio
async def test_call_rpc_fires_callback_too(make_bot):
    """call_rpc should also fire on_rpc_response callbacks."""
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    callback_data: list[dict] = []

    async def do_call():
        return await bot.call_rpc("service:echo", "hello", timeout=5.0)

    task = asyncio.create_task(do_call())
    await asyncio.sleep(0.05)

    emits = fake.emits_for(EventName.MESSAGE)
    request_id = emits[0]["labels"][0][3]["request_id"]

    @bot.on_rpc_response(request_id)
    def _cb(data):
        callback_data.append(data)

    # Trigger the MESSAGE handler (fires callback) AND resolve the future
    fake.trigger(EventName.MESSAGE, {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "Echo: hello",
        "labels": [["bot-echo-svc", "service:echo-response", "1.0.0", {"request_id": request_id}]],
    })
    fake.resolve_rpc(request_id, "Echo: hello")

    result = await task
    assert result == "Echo: hello"
    assert len(callback_data) == 1
    assert callback_data[0]["content"] == "Echo: hello"


@pytest.mark.asyncio
async def test_call_rpc_cleans_up_on_timeout(make_bot):
    """After timeout, the pending future should be removed."""
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    with pytest.raises(asyncio.TimeoutError):
        await bot.call_rpc("service:echo", "hello", timeout=0.1)

    assert len(fake._pending_rpc_futures) == 0


@pytest.mark.asyncio
async def test_call_rpc_concurrent_requests_dont_block(make_bot):
    """Multiple in-flight call_rpc requests resolve independently.

    BUSINESS RULE: a slow RPC service (5s delay) must not block the
    bot from making other RPC calls.  call_rpc is async — each call
    creates its own Future and awaits it independently.
    """
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    async def slow_call():
        return await bot.call_rpc("service:math", "slow", timeout=10.0)

    async def fast_call():
        return await bot.call_rpc("service:math", "fast", timeout=10.0)

    task_slow = asyncio.create_task(slow_call())
    task_fast = asyncio.create_task(fast_call())

    await asyncio.sleep(0.05)

    emits = fake.emits_for(EventName.MESSAGE)
    assert len(emits) == 2

    slow_req_id = emits[0]["labels"][0][3]["request_id"]
    fast_req_id = emits[1]["labels"][0][3]["request_id"]

    # Resolve the fast call first
    fake.resolve_rpc(fast_req_id, "fast-result")

    fast_result = await task_fast
    assert fast_result == "fast-result"
    assert not task_slow.done()

    # Then resolve the slow call
    fake.resolve_rpc(slow_req_id, "slow-result")

    slow_result = await task_slow
    assert slow_result == "slow-result"


@pytest.mark.asyncio
async def test_call_rpc_resolves_correctly_when_out_of_order(make_bot):
    """Responses arriving out of order are correlated by request_id."""
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    async def call_a():
        return await bot.call_rpc("service:math", "first", timeout=10.0)

    async def call_b():
        return await bot.call_rpc("service:math", "second", timeout=10.0)

    task_a = asyncio.create_task(call_a())
    task_b = asyncio.create_task(call_b())
    await asyncio.sleep(0.05)

    emits = fake.emits_for(EventName.MESSAGE)
    req_id_a = emits[0]["labels"][0][3]["request_id"]
    req_id_b = emits[1]["labels"][0][3]["request_id"]

    # Resolve B first (out of order)
    fake.resolve_rpc(req_id_b, "result-b")

    result_b = await task_b
    assert result_b == "result-b"
    assert not task_a.done()

    # Then resolve A
    fake.resolve_rpc(req_id_a, "result-a")

    result_a = await task_a
    assert result_a == "result-a"
