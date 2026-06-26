"""Shared test fixtures for meadows-bot.

BUSINESS RULE (MEADOWS §5 line 130): the SDK hides transport. Tests
prove the routing/registration logic works without a real server by
injecting a FakeMeadowClient that records emits and lets us trigger
handlers manually — same pattern meadows-client uses (FakeAsyncClient).
"""

from __future__ import annotations

import pathlib
import secrets
from typing import Any

import pytest

from meadows.bot import BaseBot
from meadows.protocol import EventName


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


def _make_bot(
    bot_cls: type[BaseBot],
    jwt_secret_file: pathlib.Path,
    **bot_kwargs: Any,
) -> tuple[BaseBot, FakeMeadowClient]:
    """Construct a bot with a FakeMeadowClient swapped in.

    BUSINESS RULE (MEADOWS §5 line 130): the SDK owns transport
    construction, so tests reach in after __init__ and replace
    self.client with a fake. This is the seam that makes the bot
    testable without a server.
    """
    bot = bot_cls(jwt_secret_path=str(jwt_secret_file), **bot_kwargs)
    fake = FakeMeadowClient()
    # Re-wire handlers against the fake (the real __init__ wired them
    # against the real MeadowClient; we replay _setup_handlers).
    bot.client = fake
    bot._setup_handlers()  # type: ignore[attr-defined]
    return bot, fake


@pytest.fixture()
def jwt_secret_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a throwaway JWT secret so BaseBot.__init__ can read it.

    BUSINESS RULE (MEADOWS §5 line 132): BaseBot reads the secret from
    a path. Tests shouldn't depend on /shared_keys existing.
    """
    key = tmp_path / "jwt.key"
    # BUSINESS RULE: the secret just needs to be bytes. A random 48-byte
    # key is plenty for tests (and avoids reusing a real secret).
    key.write_bytes(secrets.token_bytes(48))
    return key


@pytest.fixture()
def make_bot(jwt_secret_file: pathlib.Path):
    """Fixture returning a factory that builds a bot with a fake client.

    Usage: bot, fake = make_bot(MyBot)
    """

    def _factory(
        bot_cls: type[BaseBot],
        **bot_kwargs: Any,
    ) -> tuple[BaseBot, FakeMeadowClient]:
        return _make_bot(bot_cls, jwt_secret_file, **bot_kwargs)

    return _factory
