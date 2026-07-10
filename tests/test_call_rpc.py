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
