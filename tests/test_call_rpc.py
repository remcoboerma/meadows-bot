"""Tests for BaseBot.call_rpc — the async RPC author surface.

BUSINESS RULE (§2.10): call_rpc lets bot authors await a remote
service response as if it were a local call.  These tests pin
that contract without a real server.
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
    """call_rpc should return the response content when an RPC_RESPONSE arrives."""
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    # Start call_rpc in the background
    async def do_call():
        return await bot.call_rpc("service:echo", "hello", timeout=5.0)

    task = asyncio.create_task(do_call())
    await asyncio.sleep(0.05)  # let the task start

    # Simulate the RPC_RESPONSE arriving
    # Find the request_id from the emitted RPC_REQUEST
    emits = fake.emits_for(EventName.MESSAGE)
    assert len(emits) == 1
    request_msg = emits[0]
    assert request_msg["type"] == MessageType.RPC_REQUEST.value

    request_id = None
    for lbl in request_msg.get("labels", []):
        if isinstance(lbl, (list, tuple)) and len(lbl) > 3 and isinstance(lbl[3], dict):
            request_id = lbl[3].get("request_id")
            break
    assert request_id is not None

    # Trigger the MESSAGE handler with an RPC_RESPONSE
    response_data = {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "Echo: hello",
        "labels": [["bot-echo-svc", "service:echo-response", "1.0.0", {"request_id": request_id}]],
    }
    fake.trigger(EventName.MESSAGE, response_data)

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

    # Send a response with a DIFFERENT request_id — should be ignored
    unrelated_response = {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "not for you",
        "labels": [["bot-echo-svc", "service:echo-response", "1.0.0", {"request_id": "wrong-id"}]],
    }
    fake.trigger(EventName.MESSAGE, unrelated_response)

    # Now send the correct response
    emits = fake.emits_for(EventName.MESSAGE)
    request_msg = emits[0]
    request_id = None
    for lbl in request_msg.get("labels", []):
        if isinstance(lbl, (list, tuple)) and len(lbl) > 3 and isinstance(lbl[3], dict):
            request_id = lbl[3].get("request_id")
            break

    correct_response = {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "correct answer",
        "labels": [["bot-echo-svc", "service:echo-response", "1.0.0", {"request_id": request_id}]],
    }
    fake.trigger(EventName.MESSAGE, correct_response)

    result = await task
    assert result == "correct answer"


@pytest.mark.asyncio
async def test_call_rpc_fires_callback_too(make_bot):
    """call_rpc should also fire on_rpc_response callbacks."""
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    # Register a callback via on_rpc_response decorator
    callback_data: list[dict] = []

    # We need the request_id before we can register the callback.
    # Start call_rpc, get the request_id from the emit, then register.
    async def do_call():
        return await bot.call_rpc("service:echo", "hello", timeout=5.0)

    task = asyncio.create_task(do_call())
    await asyncio.sleep(0.05)

    emits = fake.emits_for(EventName.MESSAGE)
    request_msg = emits[0]
    request_id = None
    for lbl in request_msg.get("labels", []):
        if isinstance(lbl, (list, tuple)) and len(lbl) > 3 and isinstance(lbl[3], dict):
            request_id = lbl[3].get("request_id")
            break

    @bot.on_rpc_response(request_id)
    def _cb(data):
        callback_data.append(data)

    response_data = {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "Echo: hello",
        "labels": [["bot-echo-svc", "service:echo-response", "1.0.0", {"request_id": request_id}]],
    }
    fake.trigger(EventName.MESSAGE, response_data)

    result = await task
    assert result == "Echo: hello"
    assert len(callback_data) == 1
    assert callback_data[0]["content"] == "Echo: hello"


@pytest.mark.asyncio
async def test_call_rpc_cleans_up_on_timeout(make_bot):
    """After timeout, the pending future should be removed."""
    bot, _fake = make_bot(_CallerBot)
    bot.authenticated = True

    with pytest.raises(asyncio.TimeoutError):
        await bot.call_rpc("service:echo", "hello", timeout=0.1)

    assert len(bot._pending_rpc_futures) == 0


@pytest.mark.asyncio
async def test_call_rpc_concurrent_requests_dont_block(make_bot):
    """Multiple in-flight call_rpc requests resolve independently.

    BUSINESS RULE: a slow RPC service (5s delay) must not block the
    bot from making other RPC calls.  call_rpc is async — each call
    creates its own Future and awaits it independently.
    """
    bot, fake = make_bot(_CallerBot)
    bot.authenticated = True

    # Start two concurrent call_rpc calls
    async def slow_call():
        return await bot.call_rpc("service:math", "slow", timeout=10.0)

    async def fast_call():
        return await bot.call_rpc("service:math", "fast", timeout=10.0)

    task_slow = asyncio.create_task(slow_call())
    task_fast = asyncio.create_task(fast_call())

    await asyncio.sleep(0.05)  # let both tasks start

    # Both should have emitted RPC_REQUEST
    emits = fake.emits_for(EventName.MESSAGE)
    assert len(emits) == 2

    # Extract request_ids — first emit is slow, second is fast
    slow_req_id = None
    fast_req_id = None
    for i, msg in enumerate(emits):
        for lbl in msg.get("labels", []):
            if isinstance(lbl, (list, tuple)) and len(lbl) > 3 and isinstance(lbl[3], dict):
                rid = lbl[3].get("request_id")
                if rid:
                    if i == 0:
                        slow_req_id = rid
                    else:
                        fast_req_id = rid
    assert slow_req_id is not None
    assert fast_req_id is not None

    # Respond to the FAST call first (simulating quick service)
    fast_response = {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "fast-result",
        "labels": [["bot-math-svc", "service:math-response", "1.0.0", {"request_id": fast_req_id}]],
    }
    fake.trigger(EventName.MESSAGE, fast_response)

    # Fast should resolve immediately, slow should still be pending
    fast_result = await task_fast
    assert fast_result == "fast-result"
    assert not task_slow.done()

    # Now respond to the slow call (simulating 5s delay)
    slow_response = {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "slow-result",
        "labels": [["bot-math-svc", "service:math-response", "1.0.0", {"request_id": slow_req_id}]],
    }
    fake.trigger(EventName.MESSAGE, slow_response)

    slow_result = await task_slow
    assert slow_result == "slow-result"


@pytest.mark.asyncio
async def test_call_rpc_resolves_correctly_when_out_of_order(make_bot):
    """Responses arriving out of order are correlated by request_id.

    The second call's response arrives before the first — each must
    resolve its own Future, not the other's.
    """
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
    req_id_a = None
    req_id_b = None
    for i, msg in enumerate(emits):
        for lbl in msg.get("labels", []):
            if isinstance(lbl, (list, tuple)) and len(lbl) > 3 and isinstance(lbl[3], dict):
                rid = lbl[3].get("request_id")
                if rid:
                    if i == 0:
                        req_id_a = rid
                    else:
                        req_id_b = rid

    # Respond to B first (out of order)
    fake.trigger(EventName.MESSAGE, {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "result-b",
        "labels": [["svc", "resp", "1.0.0", {"request_id": req_id_b}]],
    })

    result_b = await task_b
    assert result_b == "result-b"
    assert not task_a.done()

    # Then respond to A
    fake.trigger(EventName.MESSAGE, {
        "type": MessageType.RPC_RESPONSE.value,
        "content": "result-a",
        "labels": [["svc", "resp", "1.0.0", {"request_id": req_id_a}]],
    })

    result_a = await task_a
    assert result_a == "result-a"
