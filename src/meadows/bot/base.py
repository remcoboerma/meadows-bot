"""BaseBot — the MEADOWS bot SDK core.

BUSINESS RULE (MEADOWS §5 line 130): The quick-start must be truly quick.
A working bot is BOT_NAME + should_handle + handle + connect().
Everything below that (auth, reconnect, registration, routing) is hidden.

BUSINESS RULE (MEADOWS §5 line 128): The target user is NOT a standard
Python developer — it's a Dutch teacher (groep 6) working with an AI
during a hackathon. Defaults that "just work" and errors in human
language are more important than elegance.

BUSINESS RULE (MEADOWS §2 line 41): server and bot never touch each other
directly. They meet only via the protocol declaration. This bot imports
from meadows.client (transport) and meadows.protocol (shapes), never
from meadows.server.

BUSINESS RULE (MEADOWS §7 line 152): "Het gedrag is heilig, de oude
structuur niet." The monolith's BaseBot (bots/base.py) is the behavior
reference; the sys.path hacks and direct socketio.Client() are not.
"""

from __future__ import annotations

import os
import pathlib
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar

from meadows.client import MeadowClient
from meadows.protocol import EventName, JWTRole, Message, MessageType, build_claims
from meadows.protocol.envelope import QuotedMessage, generate_message_id, now_iso

# BUSINESS RULE (MEADOWS §5 line 132): "Foutmeldingen en defaults zijn
# pedagogie." Configurable via env so a stuck reconnect loop doesn't
# hammer the server — but the default just works.
BOT_AUTH_ERROR_DISCONNECT_DELAY = int(os.environ.get("BOT_AUTH_ERROR_DISCONNECT_DELAY", "5"))

# BUSINESS RULE (MEADOWS §5 line 130): the 3-second wait is behavioral
# heritage from the monolith (bots/base.py:134-138). It ensures the
# server is up before the bot tries to connect; without it, a bot
# started alongside the server spews connection errors that teach a
# groep-6 docent nothing.
CONNECT_DELAY_SECONDS = 3


class BaseBot(ABC):
    """
    Base class for all MEADOWS bots.

    BUSINESS RULE (MEADOWS §5 line 130): The quick-start must be truly quick.
    A working bot is `BOT_NAME` + `should_handle` + `handle` + `connect()`.
    Everything below that (auth, reconnect, registration, routing) is hidden.

    BUSINESS RULE (MEADOWS §5 line 128): The target user is NOT a standard
    Python developer — it's a Dutch teacher (groep 6) working with an AI
    during a hackathon. Defaults that "just work" and errors in human
    language are more important than elegance.

    BUSINESS RULE (MEADOWS §2 line 41): server and bot never touch each other
    directly. They meet only via the protocol declaration. This bot imports
    from meadows.client (transport) and meadows.protocol (shapes), never
    from meadows.server.

    Example:
        class MyBot(BaseBot):
            BOT_NAME = "mybot"
            BOT_DESCRIPTION = "My custom bot"
            BOT_COMMANDS = [{"name": "greet", "description": "Say hello"}]

            def should_handle(self, command, args):
                return command == "greet"

            def handle(self, command, args, raw_args, message, thread_context):
                return f"Hello {args[0] if args else 'user'}!"

        if __name__ == "__main__":
            MyBot().connect()
    """

    # --- Identity (class attrs a bot author overrides) ---
    BOT_NAME: str = "basebot"
    BOT_DESCRIPTION: str = "Base bot class"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = []
    # BUSINESS RULE: thread context window the server sends with each
    # bot_command. Behavioral heritage from monolith bots/base.py:42.
    BOT_CONTEXT_LIMIT: int = 30

    def __init__(self, jwt_secret_path: str | None = None) -> None:
        """Load the JWT secret and construct the internal MeadowClient.

        BUSINESS RULE (MEADOWS §5 line 130): the bot author should not
        have to think about transport. A MeadowClient is constructed
        internally with the bot's identity baked into the JWT claims.

        BUSINESS RULE (MEADOWS §5 line 132): defaults that "just work."
        The JWT secret path and server URL fall back to env vars and
        sensible defaults so a bot author who does nothing special
        still gets a working bot.
        """
        # BUSINESS RULE (MEADOWS §5 line 132): env-driven defaults so
        # deployment is consistent across the five repos. Same env keys
        # as meadows-client (MEADOWS_SERVER_URL, MEADOWS_JWT_SECRET).
        self.jwt_secret_path = jwt_secret_path or os.environ.get("MEADOWS_JWT_SECRET", "/shared_keys/jwt.key")
        self.jwt_secret = pathlib.Path(self.jwt_secret_path).read_bytes()
        self.server_url = os.environ.get("MEADOWS_SERVER_URL", "http://localhost:8080")

        # BUSINESS RULE (MEADOWS §2 line 41): identity lives in the
        # protocol, not in ad-hoc dicts. build_claims() enforces the
        # sub-prefix convention (bot-<name>) so the server's auth
        # always sees a well-formed identity.
        self.claims = build_claims(name=self.BOT_NAME, role=JWTRole.BOT)

        # BUSINESS RULE (MEADOWS §2 line 41): the bot never touches
        # socketio directly. MeadowClient owns the transport (connect,
        # reconnect, JWT handshake). This is the "client makes the
        # second implementation cheap" invariant from §2 line 42.
        self.client = MeadowClient(
            server_url=self.server_url,
            claims=self.claims,
            jwt_secret=self.jwt_secret,
        )

        self.groups: set[str] = set()
        self.authenticated = False

        # Pattern-matching surface (forms are postponed to iteration 4
        # per the migration plan; patterns are core per §3.3 line 74).
        self._registered_patterns: list[dict[str, Any]] = []
        self._pattern_matched_handlers: dict[str, Callable] = {}

        # Fetch-messages callbacks (request_id -> callback).
        self._pending_fetch_requests: dict[str, Callable] = {}

        # BUSINESS RULE (MEADOWS §2 line 42): fire-and-forget emit tasks
        # are tracked here so the GC doesn't cancel them mid-flight.
        self._background_tasks: set[Any] = set()

        self._setup_handlers()

    # ------------------------------------------------------------------
    # Handler wiring
    # ------------------------------------------------------------------

    def _setup_handlers(self) -> None:
        """Register this bot's handlers on the internal MeadowClient.

        BUSINESS RULE (MEADOWS §5 line 130): the bot author never writes
        this wiring. It is the SDK's job to route the events the server
        emits (bot_command, bot_authenticated, pattern_matched, ...) to
        the methods the author does write (should_handle/handle).
        """
        # BUSINESS RULE (MEADOWS §3.3 line 74): patterns are core —
        # the server evaluates registered regexes and emits
        # pattern_matched. The bot must listen for it.
        self.client.on(EventName.BOT_COMMAND, self.on_bot_command)
        self.client.on(EventName.BOT_AUTHENTICATED, self.on_bot_authenticated)
        self.client.on(EventName.PATTERN_MATCHED, self._on_pattern_matched_event)
        self.client.on(EventName.FETCH_MESSAGES_RESULT, self._on_fetch_messages_result)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _fire_and_forget(self, event: EventName | str, data: Any) -> None:
        """Emit via the client without blocking the caller.

        BUSINESS RULE (MEADOWS §5 line 130): author-facing helpers
        (register_pattern, fetch_messages, ...) are called from sync
        bot code. MeadowClient.emit is async (the transport is async).
        This helper bridges the gap: if a loop is running (production,
        inside an async handler), schedule the coroutine as a task; if
        not (tests calling helpers directly), run it to completion.
        This preserves the sync author surface that the quick-start
        contract demands.
        """
        import asyncio

        coro = self.client.emit(event, data)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (e.g. a test calling the helper directly).
            # Run the coroutine to completion so the emit is recorded.
            asyncio.run(coro)
            return
        # BUSINESS RULE: keep a reference so the task isn't GC'd mid-flight.
        # Stored on the instance; cleared tasks are pruned opportunistically.
        task = loop.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def connect(self) -> None:
        """Connect to the server and block.

        BUSINESS RULE (MEADOWS §5 line 130, monolith base.py:134-138):
        wait 3 seconds before connecting so the server has time to come
        up. Without this, a bot started alongside the server spews
        connection errors that teach a groep-6 docent nothing.

        BUSINESS RULE (MEADOWS §5 line 128): this method is the *only*
        thing a bot author calls to start their bot. Everything below
        (JWT handshake, registration, reconnect) is delegated to
        MeadowClient and the handlers wired in _setup_handlers.
        """
        print(f"Bot {self.BOT_NAME} waiting {CONNECT_DELAY_SECONDS}s for the server to come online...")
        time.sleep(CONNECT_DELAY_SECONDS)

        print(f"Connecting bot {self.BOT_NAME} to {self.server_url}")
        # MeadowClient.connect is async; a bot author's main script is
        # sync (echo_bot.py: `EchoBot().connect()`). We bridge with
        # asyncio.run so the quick-start stays sync and copy-pasteable.
        import asyncio

        asyncio.run(self._connect_and_wait())

    async def _connect_and_wait(self) -> None:
        """Async inner: connect the client, then block on wait().

        BUSINESS RULE (MEADOWS §5 line 130): the bot author never sees
        this. It exists so connect() can stay sync (the quick-start
        contract) while MeadowClient is async.
        """
        await self.client.connect()
        await self.client.wait()

    def on_connect(self, handler: Callable) -> None:
        """Register a handler fired when the bot connects (post-auth).

        Passthrough to MeadowClient.on_connect. A bot author who needs
        a "I'm ready" hook uses this.
        """
        self.client.on_connect(handler)

    def on_disconnect(self, handler: Callable) -> None:
        """Register a handler fired when the bot disconnects.

        Passthrough to MeadowClient.on_disconnect.
        """
        self.client.on_disconnect(handler)

    # ------------------------------------------------------------------
    # Auth + registration
    # ------------------------------------------------------------------

    async def on_bot_authenticated(self, data: dict[str, Any]) -> None:
        """Handle bot_authenticated: store groups, register metadata, re-register patterns.

        BUSINESS RULE (MEADOWS §2 line 41): the server validates the JWT
        (handled by MeadowClient) and replies with bot_authenticated
        carrying the groups the bot is in. The bot then emits
        register_bot with its manifest so the server can route
        @<bot_name> <command> and advertise the bot in discovery.

        BUSINESS RULE (monolith base.py:156-182): after a reconnect,
        patterns must be re-registered because the server has lost
        them. This is behavioral heritage — the bot keeps its own
        list of registered patterns and replays them on auth.

        BUSINESS RULE (MEADOWS §2 line 42): MeadowClient is async
        (built on socketio.AsyncClient), so this handler awaits the
        client's emit. The author-facing surface (should_handle/handle)
        stays sync; the SDK's own routing is async because the
        transport is.
        """
        self.authenticated = True
        self.groups = set(data.get("groups", []))
        print(f"Bot {self.BOT_NAME} authenticated, groups: {self.groups}")

        # BUSINESS RULE (MEADOWS §3.3): the bot advertises its command
        # manifest so the server can route @<bot> <command> and list
        # it in discovery. This is the bot-author-facing surface
        # (BOT_COMMANDS) crossing into the protocol (register_bot).
        await self.client.emit(
            EventName.REGISTER_BOT,
            {
                "description": self.BOT_DESCRIPTION,
                "commands": self.BOT_COMMANDS,
                "context_limit": self.BOT_CONTEXT_LIMIT,
            },
        )
        print(f"Bot {self.BOT_NAME} emitted register_bot")

        # BUSINESS RULE (monolith base.py:179-182): replay patterns
        # after reconnect. The server's pattern registry is per-session.
        for pattern_data in self._registered_patterns:
            await self.client.emit(EventName.REGISTER_PATTERN, pattern_data)
            self.log(f"Re-registered pattern '{pattern_data['name']}' after reconnect")

    # ------------------------------------------------------------------
    # Command routing
    # ------------------------------------------------------------------

    async def on_bot_command(self, data: dict[str, Any]) -> None:
        """Receive a bot_command, route it through should_handle/handle, emit bot_response.

        BUSINESS RULE (MEADOWS §5 line 130): this is the routing the
        bot author never writes. should_handle decides, handle responds,
        and this method emits the bot_response via the protocol
        envelope — no hand-built dicts (monolith base.py:231-243 is the
        behavior reference; the structure is replaced by Message).

        BUSINESS RULE (MEADOWS §7 line 152): the behavior is sacred —
        if should_handle is False, no emit. If handle returns None, no
        emit. Otherwise emit a Message with the response as content and
        the triggering user's message as quoted_message for reply context.

        BUSINESS RULE (MEADOWS §2 line 42): MeadowClient is async, so
        this handler awaits the client's emit. should_handle and handle
        (the author surface) stay sync — the SDK bridges the gap.
        """
        command = data.get("command", "")
        args = data.get("args", [])
        raw_args = data.get("raw_args", [])
        message = data.get("message", {})
        thread_context = data.get("thread_context", [])
        group_id = message.get("group_id", "general")

        if not self.should_handle(command, args):
            # BUSINESS RULE (MEADOWS §7 line 152): behavior heritage —
            # a bot that doesn't handle a command stays silent. No emit.
            return

        response = self.handle(command, args, raw_args, message, thread_context)
        if response is None:
            # BUSINESS RULE: handle() returning None means "I chose not
            # to respond." Don't emit an empty bot_response.
            return

        # BUSINESS RULE (MEADOWS §7 line 152 + monolith base.py:219-243):
        # include the user's message as quoted_message so the bot's
        # response shows reply context in the UI. The shape is now the
        # protocol's QuotedMessage, not a hand-built dict.
        quoted_msg = None
        if message:
            quoted_msg = QuotedMessage(
                id=message.get("id", ""),
                author=message.get("username") or message.get("user_id") or "unknown",
                user_id=message.get("user_id"),
                username=message.get("username"),
                content=message.get("content", ""),
                timestamp=message.get("timestamp", ""),
            )

        # BUSINESS RULE (MEADOWS §2 line 41 + §3.4 line 89): the bot
        # emits through the protocol envelope. The Message is the
        # contracted frame; original_command and quoted_message are
        # opaque pass-through fields the system doesn't parse.
        bot_response = Message(
            id=generate_message_id(),
            type=MessageType.BOT,
            user_id=self.claims.sub,
            bot_name=self.BOT_NAME,
            group_id=group_id,
            content=response,
            original_command=f"@{self.BOT_NAME} {command} {' '.join(args)}".strip(),
            quoted_message=quoted_msg,
            timestamp=now_iso(),
        )

        await self.client.emit(EventName.BOT_RESPONSE, bot_response.model_dump(exclude_none=True))

    # ------------------------------------------------------------------
    # Abstract surface — the bot author implements these
    # ------------------------------------------------------------------

    @abstractmethod
    def should_handle(self, command: str, args: list[str]) -> bool:
        """Decide whether this bot handles the given command.

        BUSINESS RULE (MEADOWS §5 line 130): this is one of the two
        things a bot author writes. The SDK calls it; the author
        decides. Keeping this separate from handle() lets multiple bots
        coexist without each having to know about the others.

        Args:
            command: The bot command (e.g. "echo", "ping", "help").
            args: Parsed arguments after the command.

        Returns:
            True if this bot handles the command, False otherwise.
        """

    @abstractmethod
    def handle(
        self,
        command: str,
        args: list[str],
        raw_args: list[str],
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],
    ) -> str | None:
        """Process the command and return a response (or None to stay silent).

        BUSINESS RULE (MEADOWS §5 line 130): this is the second thing a
        bot author writes. Returning a string emits a bot_response;
        returning None means "I chose not to respond."

        Args:
            command: The bot command to execute.
            args: Parsed arguments (space-separated, shell-quoted).
            raw_args: Raw unparsed arguments.
            message: The original user message object.
            thread_context: Previous messages in the conversation.

        Returns:
            Response string, or None to skip the response.
        """

    # ------------------------------------------------------------------
    # Utility helpers — reduce boilerplate for bot authors
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "INFO") -> None:
        """Log a message with the bot name prefix.

        BUSINESS RULE (MEADOWS §5 line 132): "Foutmeldingen en defaults
        zijn pedagogie." A bot that fails silently teaches a groep-6
        docent nothing. This helper gives authors one obvious way to
        make noise, with the bot's identity attached.
        """
        print(f"[{level}] [{self.BOT_NAME}] {message}")

    def get_sender_info(self, message: dict[str, Any]) -> dict[str, str]:
        """Extract sender info (user_id, email, display_name) from a message.

        BUSINESS RULE (MEADOWS §5 line 128): a bot author who wants to
        address a user by name shouldn't have to know the message
        shape. This helper normalizes it. Behavioral heritage from
        monolith base.py:294-312.
        """
        user_id = message.get("user_id", "unknown")
        email = message.get("email", "")
        # BUSINESS RULE: display_name is the local part of the email if
        # present, else the user_id. This is the monolith's convention.
        display_name = email.split("@")[0] if email else user_id
        return {
            "user_id": user_id,
            "email": email,
            "display_name": display_name,
        }

    def format_help_response(self) -> str:
        """Generate a formatted help message from BOT_COMMANDS.

        BUSINESS RULE (MEADOWS §5 line 130): a help command is the
        single most common bot feature. Giving authors a one-liner for
        it removes a piece of boilerplate they'd otherwise copy-paste
        wrong. Behavioral heritage from monolith base.py:314-321.
        """
        lines = [f"{self.BOT_NAME.capitalize()} Bot Commands:\n"]
        for cmd in self.BOT_COMMANDS:
            name = cmd.get("name", "")
            desc = cmd.get("description", "")
            lines.append(f"  @{self.BOT_NAME} {name} - {desc}")
        return "\n".join(lines)

    def extract_quoted_string(self, args: list[str]) -> str | None:
        """Join args into a single string (for phrases with spaces).

        BUSINESS RULE (MEADOWS §5 line 130): echo-style bots need this
        constantly. Without a helper, every author rewrites " ".join().
        Behavioral heritage from monolith base.py:323-333.
        """
        return " ".join(args) if args else None

    # ------------------------------------------------------------------
    # Pattern matching (core per §3.3 line 74; forms postponed to iter 4)
    # ------------------------------------------------------------------

    def register_pattern(
        self,
        name: str,
        pattern: str,
        scope: str = "room",
        group_id: str | None = None,
    ) -> None:
        """Register a regex pattern with the server for event-driven notifications.

        BUSINESS RULE (MEADOWS §3.3 line 74): patterns are core. The
        server evaluates registered regexes on every message and emits
        pattern_matched to the registrant. This is generic routing
        machinery, not a domain feature.

        BUSINESS RULE (MEADOWS §5 line 130): this is an author-facing
        helper called from sync bot code (handle/on_pattern_matched).
        The underlying client.emit is async (MeadowClient is async),
        so we fire-and-forget the coroutine on the running loop —
        matching the monolith's sync sio.emit semantics. Behavioral
        heritage from monolith base.py:463-485: the bot keeps its own
        list so it can replay on reconnect.
        """
        data: dict[str, Any] = {"name": name, "pattern": pattern, "scope": scope}
        if scope == "room" and group_id:
            data["group_id"] = group_id

        self._registered_patterns.append(data)
        if self.authenticated:
            self._fire_and_forget(EventName.REGISTER_PATTERN, data)
            self.log(f"Registered pattern '{name}' ({pattern}) scope={scope}")
        else:
            self.log(f"Queued pattern '{name}' for registration after connect")

    def unregister_pattern(self, name: str) -> None:
        """Unregister a previously registered pattern by name.

        BUSINESS RULE (MEADOWS §3.3 line 74): patterns are core, so the
        inverse operation is part of the surface. Behavioral heritage
        from monolith base.py:487-498. Fire-and-forget emit (see
        register_pattern).
        """
        self._fire_and_forget(EventName.UNREGISTER_PATTERN, {"name": name})
        self._registered_patterns = [p for p in self._registered_patterns if p["name"] != name]
        self.log(f"Unregistered pattern '{name}'")

    def on_pattern_matched(self, pattern_name: str) -> Callable[[Callable], Callable]:
        """Decorator: register a callback for a specific pattern match.

        BUSINESS RULE (MEADOWS §5 line 130): the decorator form is the
        copy-pasteable quick-start shape. Behavioral heritage from
        monolith base.py:500-522.

        The callback receives:
            pattern_name, matched_text, original_message_id, sender, group_id, timestamp
        """

        def decorator(func: Callable) -> Callable:
            self._pattern_matched_handlers[pattern_name] = func
            return func

        return decorator

    def _on_pattern_matched_event(self, data: dict[str, Any]) -> None:
        """Internal: dispatch a pattern_matched event to the registered handler.

        BUSINESS RULE (MEADOWS §5 line 130): the bot author writes the
        handler via the decorator; the SDK does the dispatch. Errors in
        the handler are logged, not raised, so one bad handler doesn't
        kill the bot. Behavioral heritage from monolith base.py:524-538.
        """
        pattern_name = data.get("pattern_name")
        handler = self._pattern_matched_handlers.get(pattern_name) if pattern_name else None
        if handler is None:
            return
        try:
            handler(
                pattern_name,
                data.get("matched_text", ""),
                data.get("original_message_id", ""),
                data.get("sender", "unknown"),
                data.get("group_id", "general"),
                data.get("timestamp", ""),
            )
        except Exception as e:
            # BUSINESS RULE (MEADOWS §5 line 132): log in human language,
            # don't crash. A bot that dies on one bad pattern match
            # teaches a docent nothing.
            self.log(f"Error in pattern_matched handler for '{pattern_name}': {e}", "ERROR")

    # ------------------------------------------------------------------
    # Message history (fetch)
    # ------------------------------------------------------------------

    def fetch_messages(
        self,
        message_ids: list[str],
        group_id: str,
        callback: Callable | None = None,
    ) -> None:
        """Fetch messages by ID from the server.

        BUSINESS RULE (MEADOWS §5 line 130): this is an author-facing
        helper, not internal plumbing. A bot that needs context (e.g.
        an LLM bot assembling a prompt) calls this. Fire-and-forget
        emit (see register_pattern). Behavioral heritage from monolith
        base.py:433-450.
        """
        request_id = uuid.uuid4().hex[:8]
        if callback:
            self._pending_fetch_requests[request_id] = callback

        self._fire_and_forget(
            EventName.FETCH_MESSAGES,
            {"message_ids": message_ids, "group_id": group_id, "request_id": request_id},
        )

    def _on_fetch_messages_result(self, data: dict[str, Any]) -> None:
        """Internal: dispatch a fetch_messages_result to the waiting callback.

        BUSINESS RULE (MEADOWS §5 line 130): the author passed a
        callback to fetch_messages(); the SDK routes the reply back to
        it. Behavioral heritage from monolith base.py:452-461.
        """
        request_id = data.get("request_id")
        if not request_id or request_id not in self._pending_fetch_requests:
            return
        callback = self._pending_fetch_requests.pop(request_id)
        messages = data.get("messages", [])
        try:
            callback(messages)
        except Exception as e:
            self.log(f"Error in fetch_messages callback: {e}", "ERROR")


__all__ = ["BOT_AUTH_ERROR_DISCONNECT_DELAY", "BaseBot"]
