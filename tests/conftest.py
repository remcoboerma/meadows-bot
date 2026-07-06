"""Shared test fixtures for meadows-bot.

BUSINESS RULE (MEADOWS §5 line 130): the SDK hides transport. Tests
prove the routing/registration logic works without a real server by
injecting a FakeMeadowClient that records emits and lets us trigger
handlers manually — same pattern meadows-client uses (FakeAsyncClient).

BUSINESS RULE (auth): only the server knows the production signing key.
Tests use a throwaway secret to mint test JWTs — the bot never reads
the real signing key.
"""

from __future__ import annotations

from typing import Any

import jwt as pyjwt
import pytest

from meadows.bot import BaseBot
from meadows.protocol import EventName, JWTRole, build_claims, jwt as protocol_jwt


class FakeMeadowClient:
    """Stand-in for MeadowClient. Records emits, triggers handlers.

    BUSINESS RULE (MEADOWS §2 line 41): the bot talks to MeadowClient,
    not to socketio. So a fake client that mimics MeadowClient's
    author-facing surface (on, emit, connect, wait) is enough to test
    the bot's routing and registration logic without a server.
    """

    def __init__(self) -> None:
        self.emits: list[tuple[str, Any]] = []  # (event_name, data)
        self._handlers: dict[str, Any] = {}
        self.connected = False
        self.authenticated = False
        self.connect_called = False
        self.wait_called = False
        self._connect_handlers: list[Any] = []
        self._disconnect_handlers: list[Any] = []

    def on(self, event: EventName | str, handler: Any) -> None:
        name = event.value if isinstance(event, EventName) else str(event)
        self._handlers[name] = handler

    def on_connect(self, handler: Any) -> None:
        self._connect_handlers.append(handler)

    def on_disconnect(self, handler: Any) -> None:
        self._disconnect_handlers.append(handler)

    async def connect(self) -> None:
        self.connect_called = True
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def wait(self) -> None:
        self.wait_called = True

    async def emit(self, event: EventName | str, data: Any) -> None:
        name = event.value if isinstance(event, EventName) else str(event)
        self.emits.append((name, data))

    def trigger(self, event: EventName | str, data: Any) -> Any:
        """Fire a registered handler synchronously and return its result."""
        name = event.value if isinstance(event, EventName) else str(event)
        handler = self._handlers.get(name)
        if handler is None:
            return None
        return handler(data)

    def emits_for(self, event: EventName | str) -> list[Any]:
        """Return the data of all emits for a given event."""
        name = event.value if isinstance(event, EventName) else str(event)
        return [data for evt, data in self.emits if evt == name]


# Test-only signing secret — never used in production.
# The bot tests only need a valid JWT to verify the token flows through
# correctly; the real server validates signatures with its own secret.
_TEST_SECRET = b"test-secret-used-only-in-bot-tests-32bytes!"


def _make_bot(
    bot_cls: type[BaseBot],
    bot_token: str,
    **bot_kwargs: Any,
) -> tuple[BaseBot, FakeMeadowClient]:
    """Construct a bot with a FakeMeadowClient swapped in.

    BUSINESS RULE (MEADOWS §5 line 130): the SDK owns transport
    construction, so tests reach in after __init__ and replace
    self.client with a fake. This is the seam that makes the bot
    testable without a server.
    """
    bot = bot_cls(token=bot_token, **bot_kwargs)
    fake = FakeMeadowClient()
    # Re-wire handlers against the fake (the real __init__ wired them
    # against the real MeadowClient; we replay _setup_handlers).
    bot.client = fake
    bot._setup_handlers()  # type: ignore[attr-defined]
    return bot, fake


@pytest.fixture()
def bot_token() -> str:
    """Return a pre-signed test JWT for a bot named "recorder".

    BUSINESS RULE (auth): only the server knows the production signing
    key. This fixture uses a test-only secret to mint a JWT the bot
    can hold. The server-side tests use their own test secret — the
    two suites are independent.
    """
    claims = build_claims(name="recorder", role=JWTRole.BOT)
    return pyjwt.encode(
        claims.model_dump(exclude_none=True),
        _TEST_SECRET,
        algorithm=protocol_jwt.ALGORITHM,
    )


@pytest.fixture()
def make_bot(bot_token: str):
    """Fixture returning a factory that builds a bot with a fake client.

    Usage: bot, fake = make_bot(MyBot)
    """

    def _factory(
        bot_cls: type[BaseBot],
        **bot_kwargs: Any,
    ) -> tuple[BaseBot, FakeMeadowClient]:
        return _make_bot(bot_cls, bot_token, **bot_kwargs)

    return _factory
