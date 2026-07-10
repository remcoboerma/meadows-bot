"""Tests for BaseBot — the SDK core.

BUSINESS RULE (MEADOWS §5 line 130): these tests pin the quick-start
contract. A bot author who writes BOT_NAME + should_handle + handle +
connect() gets a working bot; the SDK does the routing, registration,
and envelope construction invisibly.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from meadows.bot import BaseBot
from meadows.bot.base import BOT_AUTH_ERROR_DISCONNECT_DELAY
from meadows.protocol import EventName, MessageType


# ---------------------------------------------------------------------------
# Minimal concrete bot for testing abstract methods
# ---------------------------------------------------------------------------


class _RecorderBot(BaseBot):
    """A bot that records what it was asked to handle and returns a canned response.

    BUSINESS RULE (MEADOWS §5 line 130): BaseBot is abstract; tests need
    a concrete subclass. This one records calls so tests can assert on
    the routing without coupling to a real bot's behavior.
    """

    BOT_NAME = "recorder"
    BOT_DESCRIPTION = "test bot"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "greet", "description": "say hi"},
        {"name": "ping", "description": "pong"},
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.should_handle_calls: list[tuple[str, list[str]]] = []
        self.handle_calls: list[tuple[str, list[str]]] = []
        self._should_return = True
        self._handle_return: str | None = "canned-response"

    def should_handle(self, command: str, args: list[str]) -> bool:
        self.should_handle_calls.append((command, args))
        return self._should_return

    def handle(
        self,
        command: str,
        args: list[str],
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],  # noqa: ARG002
        thread_context: list[dict[str, Any]],  # noqa: ARG002
    ) -> str | None:
        self.handle_calls.append((command, args))
        return self._handle_return


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestBaseBotConstruction:
    def test_construction_stores_config(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 132): defaults that just work.

        A bot constructed with only a jwt secret path should have
        server_url, claims, and client all set to sensible defaults.
        """
        bot, _ = make_bot(_RecorderBot)

        assert bot.server_url == "http://localhost:8080"
        assert bot.BOT_NAME == "recorder"
        # BUSINESS RULE (MEADOWS §2 line 41): identity is in the claims,
        # built via the protocol's build_claims. Sub-prefix enforced.
        assert bot.claims.sub == "bot-recorder"
        assert bot.claims.bot_name == "recorder"
        # BUSINESS RULE (MEADOWS §5 line 130): the client is constructed
        # internally — the author never touches socketio.
        assert bot.client is not None

    def test_construction_accepts_token(self, make_bot, bot_token):
        """BUSINESS RULE (auth): the bot receives a pre-signed JWT,
        not the signing key. Only the server can mint tokens.
        """
        bot, _ = make_bot(_RecorderBot)
        assert bot.token == bot_token

    def test_construction_initializes_empty_state(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 130): the author doesn't
        initialize groups/patterns. The SDK does.
        """
        bot, _ = make_bot(_RecorderBot)
        assert bot.groups == set()
        assert bot.authenticated is False
        assert bot._registered_patterns == []
        assert bot._pattern_matched_handlers == {}

    def test_basebot_is_abstract(self):
        """BUSINESS RULE (MEADOWS §5 line 130): BaseBot is abstract —
        you can't run a bot without writing should_handle and handle.
        """
        with pytest.raises(TypeError):
            BaseBot()  # type: ignore[abstract]

    def test_auth_error_disconnect_delay_default(self):
        """BUSINESS RULE (MEADOWS §5 line 132): the auth-error delay
        default is 5s (behavioral heritage from monolith base.py:11).
        """
        assert BOT_AUTH_ERROR_DISCONNECT_DELAY == 5


# ---------------------------------------------------------------------------
# Command routing
# ---------------------------------------------------------------------------


class TestOnBotCommand:
    def _make_command_data(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "command": "greet",
            "args": ["world"],
            "raw_args": ["world"],
            "message": {
                "id": "msg-1",
                "user_id": "user-alice",
                "username": "alice",
                "email": "alice@example.com",
                "content": "@recorder greet world",
                "group_id": "general",
                "timestamp": "2026-01-01T00:00:00.000000",
            },
            "thread_context": [],
        }
        data.update(overrides)
        return data

    async def test_should_handle_is_called_with_command_and_args(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 130): the SDK calls
        should_handle; the author decides. The call must carry the
        command and the parsed args.
        """
        bot, _ = make_bot(_RecorderBot)
        await bot.on_bot_command(self._make_command_data())
        assert bot.should_handle_calls == [("greet", ["world"])]

    async def test_when_should_handle_true_handle_is_called(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 130): should_handle True ->
        handle is called with the full envelope.
        """
        bot, _ = make_bot(_RecorderBot)
        await bot.on_bot_command(self._make_command_data())
        assert bot.handle_calls == [("greet", ["world"])]

    async def test_when_should_handle_true_and_handle_returns_response_message_emitted(self, make_bot):
        """BUSINESS RULE (MEADOWS §2 line 41 + §7 line 152): the
        response is emitted as a protocol Message (message event with
        bot auth), not a hand-built dict. quoted_message carries the
        triggering user message for reply context.
        """
        bot, fake = make_bot(_RecorderBot)
        await bot.on_bot_command(self._make_command_data())

        responses = [e for e in fake.emits_for(EventName.MESSAGE) if e.get("type") == "bot"]
        assert len(responses) == 1
        data = responses[0]
        # BUSINESS RULE: the response is a Message envelope.
        assert data["type"] == MessageType.BOT
        assert data["bot_name"] == "recorder"
        assert data["content"] == "canned-response"
        assert data["group_id"] == "general"
        # BUSINESS RULE (monolith base.py:219-229): the triggering
        # message is attached as quoted_message for reply context.
        assert data["quoted_message"]["id"] == "msg-1"
        assert data["quoted_message"]["author"] == "alice"

    async def test_when_should_handle_false_no_emit(self, make_bot):
        """BUSINESS RULE (MEADOWS §7 line 152): behavior heritage — a
        bot that doesn't handle a command stays silent. No emit.
        """
        bot, fake = make_bot(_RecorderBot)
        bot._should_return = False
        await bot.on_bot_command(self._make_command_data())
        assert [e for e in fake.emits_for(EventName.MESSAGE) if e.get("type") == "bot"] == []

    async def test_when_handle_returns_none_no_emit(self, make_bot):
        """BUSINESS RULE: handle() returning None means "I chose not to
        respond." No message is emitted.
        """
        bot, fake = make_bot(_RecorderBot)
        bot._handle_return = None
        await bot.on_bot_command(self._make_command_data())
        assert [e for e in fake.emits_for(EventName.MESSAGE) if e.get("type") == "bot"] == []

    async def test_original_command_included_in_response(self, make_bot):
        """BUSINESS RULE (monolith base.py:234): the original_command
        field reconstructs the @<bot> <command> <args> string so the
        UI can show what the user typed.
        """
        bot, fake = make_bot(_RecorderBot)
        await bot.on_bot_command(self._make_command_data())
        data = next(e for e in fake.emits_for(EventName.MESSAGE) if e.get("type") == "bot")
        assert data["original_command"] == "@recorder greet world"


# ---------------------------------------------------------------------------
# Auth + registration
# ---------------------------------------------------------------------------


class TestOnBotAuthenticated:
    async def test_sets_groups_and_authenticated_flag(self, make_bot):
        """BUSINESS RULE (monolith base.py:163-165): on auth, the
        server sends the bot's groups; the bot stores them.
        """
        bot, _ = make_bot(_RecorderBot)
        await bot.on_bot_authenticated({"groups": ["general", "team-a"]})
        assert bot.authenticated is True
        assert bot.groups == {"general", "team-a"}

    async def test_emits_register_bot_with_manifest(self, make_bot):
        """BUSINESS RULE (MEADOWS §3.3): the bot advertises its command
        manifest via register_bot so the server can route commands and
        list the bot in discovery.
        """
        bot, fake = make_bot(_RecorderBot)
        await bot.on_bot_authenticated({"groups": ["general"]})

        registrations = fake.emits_for(EventName.REGISTER_BOT)
        assert len(registrations) == 1
        data = registrations[0]
        assert data["description"] == "test bot"
        assert data["commands"] == _RecorderBot.BOT_COMMANDS
        assert data["context_limit"] == _RecorderBot.BOT_CONTEXT_LIMIT

    async def test_reregisters_patterns_after_reconnect(self, make_bot):
        """BUSINESS RULE (monolith base.py:179-182): after a reconnect,
        patterns must be re-registered because the server's pattern
        registry is per-session. The bot keeps its own list and replays.
        """
        bot, fake = make_bot(_RecorderBot)
        # Queue a pattern before auth (it won't emit because not authenticated).
        bot.register_pattern(name="escalation", pattern="urgent", scope="global")
        assert fake.emits_for(EventName.REGISTER_PATTERN) == []

        # On auth, the queued pattern is replayed.
        await bot.on_bot_authenticated({"groups": []})
        pattern_emits = fake.emits_for(EventName.REGISTER_PATTERN)
        assert len(pattern_emits) == 1
        assert pattern_emits[0]["name"] == "escalation"


# ---------------------------------------------------------------------------
# Pattern registration surface
# ---------------------------------------------------------------------------


class TestPatternRegistration:
    def test_register_pattern_stores_pattern(self, make_bot):
        """BUSINESS RULE (monolith base.py:480): the bot keeps its own
        list of registered patterns so it can replay them on reconnect.
        """
        bot, _ = make_bot(_RecorderBot)
        bot.register_pattern(name="alert", pattern="down", scope="room", group_id="ops")
        assert len(bot._registered_patterns) == 1
        stored = bot._registered_patterns[0]
        assert stored["name"] == "alert"
        assert stored["pattern"] == "down"
        assert stored["scope"] == "room"
        assert stored["group_id"] == "ops"

    def test_register_pattern_emits_when_authenticated(self, make_bot):
        """BUSINESS RULE (monolith base.py:481-483): if already
        authenticated, register immediately; otherwise queue.
        """
        bot, fake = make_bot(_RecorderBot)
        bot.authenticated = True
        bot.register_pattern(name="alert", pattern="down", scope="global")
        emits = fake.emits_for(EventName.REGISTER_PATTERN)
        assert len(emits) == 1
        assert emits[0]["name"] == "alert"

    def test_unregister_pattern_removes_from_list_and_emits(self, make_bot):
        """BUSINESS RULE (monolith base.py:487-498): unregister emits
        unregister_pattern and removes from the local list.
        """
        bot, fake = make_bot(_RecorderBot)
        bot.register_pattern(name="alert", pattern="down", scope="global")
        bot.unregister_pattern("alert")
        assert bot._registered_patterns == []
        emits = fake.emits_for(EventName.UNREGISTER_PATTERN)
        assert len(emits) == 1
        assert emits[0]["name"] == "alert"

    def test_on_pattern_matched_decorator_registers_handler(self, make_bot):
        """BUSINESS RULE (MEADOWS §5 line 130): the decorator form is
        the copy-pasteable quick-start shape for pattern callbacks.
        """
        bot, _ = make_bot(_RecorderBot)
        received: list[tuple] = []

        @bot.on_pattern_matched("alert")
        def _handle(name, text, _msg_id, sender, _group_id, _timestamp):
            received.append((name, text, sender))

        bot._on_pattern_matched_event(
            {
                "pattern_name": "alert",
                "matched_text": "system down",
                "original_message_id": "m1",
                "sender": "alice",
                "group_id": "ops",
                "timestamp": "2026-01-01",
            }
        )
        assert received == [("alert", "system down", "alice")]

    def test_pattern_matched_handler_error_is_logged_not_raised(self, make_bot, capfd):
        """BUSINESS RULE (MEADOWS §5 line 132): a bad handler is logged,
        not raised. One bad callback must not kill the bot.
        """
        bot, _ = make_bot(_RecorderBot)

        @bot.on_pattern_matched("bad")
        def _handle(_name, _text, _msg_id, _sender, _group_id, _timestamp):
            raise RuntimeError("boom")

        # Should not raise.
        bot._on_pattern_matched_event({"pattern_name": "bad", "matched_text": "x", "sender": "y"})
        out = capfd.readouterr().out
        assert "Error in pattern_matched handler" in out


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


class TestUtilityHelpers:
    def test_log_produces_output(self, make_bot, capfd):
        """BUSINESS RULE (MEADOWS §5 line 132): a bot that fails silently
        teaches nothing. log() must produce visible output with the bot
        name and level.
        """
        bot, _ = make_bot(_RecorderBot)
        bot.log("something happened", "DEBUG")
        out = capfd.readouterr().out
        assert "[DEBUG]" in out
        assert "[recorder]" in out
        assert "something happened" in out

    def test_get_sender_info_extracts_fields(self, make_bot):
        """BUSINESS RULE (monolith base.py:294-312): get_sender_info
        normalizes the message shape so authors don't have to know it.
        display_name is the local part of the email.
        """
        bot, _ = make_bot(_RecorderBot)
        info = bot.get_sender_info({"user_id": "user-42", "email": "alice@example.com"})
        assert info["user_id"] == "user-42"
        assert info["email"] == "alice@example.com"
        assert info["display_name"] == "alice"

    def test_get_sender_info_falls_back_to_user_id(self, make_bot):
        """BUSINESS RULE: no email -> display_name is the user_id."""
        bot, _ = make_bot(_RecorderBot)
        info = bot.get_sender_info({"user_id": "user-42"})
        assert info["display_name"] == "user-42"
        assert info["email"] == ""

    def test_format_help_response_uses_bot_commands(self, make_bot):
        """BUSINESS RULE (monolith base.py:314-321): format_help_response
        generates help text from BOT_COMMANDS — the one-liner for the
        most common bot feature.
        """
        bot, _ = make_bot(_RecorderBot)
        help_text = bot.format_help_response()
        assert "Recorder Bot Commands:" in help_text
        assert "@recorder greet - say hi" in help_text
        assert "@recorder ping - pong" in help_text

    def test_extract_quoted_string_joins_args(self, make_bot):
        """BUSINESS RULE (monolith base.py:323-333): extract_quoted_string
        joins args into a phrase for echo-style bots.
        """
        bot, _ = make_bot(_RecorderBot)
        assert bot.extract_quoted_string(["hello", "world"]) == "hello world"

    def test_extract_quoted_string_returns_none_for_empty(self, make_bot):
        """BUSINESS RULE: empty args -> None (so handle() can return a
        usage message).
        """
        bot, _ = make_bot(_RecorderBot)
        assert bot.extract_quoted_string([]) is None


# ---------------------------------------------------------------------------
# Fetch messages
# ---------------------------------------------------------------------------


class TestFetchMessages:
    def test_fetch_messages_emits_with_request_id(self, make_bot):
        """BUSINESS RULE (monolith base.py:433-450): fetch_messages emits
        a fetch_messages event with a request_id so the reply can be
        routed back to the callback.
        """
        bot, fake = make_bot(_RecorderBot)
        bot.fetch_messages(["m1", "m2"], group_id="general")
        emits = fake.emits_for(EventName.FETCH_MESSAGES)
        assert len(emits) == 1
        data = emits[0]
        assert data["message_ids"] == ["m1", "m2"]
        assert data["group_id"] == "general"
        assert "request_id" in data

    def test_fetch_messages_result_routes_to_callback(self, make_bot):
        """BUSINESS RULE (monolith base.py:452-461): the reply is routed
        to the callback registered under the request_id.
        """
        bot, fake = make_bot(_RecorderBot)
        received: list[list] = []
        bot.fetch_messages(["m1"], group_id="general", callback=received.append)

        # Find the request_id the bot generated.
        data = fake.emits_for(EventName.FETCH_MESSAGES)[0]
        request_id = data["request_id"]

        # Simulate the server reply.
        bot._on_fetch_messages_result({"request_id": request_id, "messages": [{"id": "m1", "content": "hi"}]})
        assert received == [[{"id": "m1", "content": "hi"}]]

    def test_fetch_messages_callback_error_is_logged(self, make_bot, capfd):
        """BUSINESS RULE (MEADOWS §5 line 132): a bad callback is logged,
        not raised.
        """
        bot, fake = make_bot(_RecorderBot)

        def bad_cb(_messages):
            raise RuntimeError("boom")

        bot.fetch_messages(["m1"], group_id="general", callback=bad_cb)
        request_id = fake.emits_for(EventName.FETCH_MESSAGES)[0]["request_id"]
        bot._on_fetch_messages_result({"request_id": request_id, "messages": []})
        out = capfd.readouterr().out
        assert "Error in fetch_messages callback" in out


# ---------------------------------------------------------------------------
# Label subscriptions (MEADOWS-labeling-intent §2.4)
# ---------------------------------------------------------------------------


class TestLabelSubscriptions:
    def test_register_label_subscription_queues_before_auth(self, make_bot):
        """BUSINESS RULE (§2.4): subscriptions queued before auth,
        replayed on connect — same pattern as patterns.
        """
        bot, _ = make_bot(_RecorderBot)
        bot.register_label_subscription("sentiment", {"regex_match": [{"var": "label"}, "^sentiment$"]})
        assert len(bot._registered_label_subscriptions) == 1
        assert bot._registered_label_subscriptions[0]["name"] == "sentiment"

    def test_register_label_subscription_emits_after_auth(self, make_bot):
        """Already authenticated -> emit immediately."""
        bot, fake = make_bot(_RecorderBot)
        bot.authenticated = True
        bot.register_label_subscription("s1", {}, scope="global")
        emits = fake.emits_for(EventName.REGISTER_LABEL_SUBSCRIPTION)
        assert len(emits) == 1
        assert emits[0]["name"] == "s1"

    def test_unregister_label_subscription_removes_and_emits(self, make_bot):
        bot, fake = make_bot(_RecorderBot)
        bot.register_label_subscription("s1", {})
        bot.unregister_label_subscription("s1")
        assert bot._registered_label_subscriptions == []
        emits = fake.emits_for(EventName.UNREGISTER_LABEL_SUBSCRIPTION)
        assert len(emits) == 1
        assert emits[0]["name"] == "s1"

    def test_on_label_assigned_decorator_registers_handler(self, make_bot):
        bot, _ = make_bot(_RecorderBot)
        received: list[dict] = []

        @bot.on_label_assigned("sentiment")
        def _handle(data):
            received.append(data)

        bot._on_label_assigned_event({"subscription_name": "sentiment", "labels": []})
        assert len(received) == 1

    def test_label_assigned_no_match_ignored(self, make_bot):
        """No matching handler -> silent, no error."""
        bot, _ = make_bot(_RecorderBot)
        bot._on_label_assigned_event({"subscription_name": "unknown", "labels": []})

    def test_label_assigned_handler_error_is_logged(self, make_bot, capfd):
        """BUSINESS RULE (§5 line 132): errors logged, not raised."""
        bot, _ = make_bot(_RecorderBot)

        @bot.on_label_assigned("bad")
        def _handle(_data):
            raise RuntimeError("boom")

        bot._on_label_assigned_event({"subscription_name": "bad", "labels": []})
        out = capfd.readouterr().out
        assert "Error in label_assigned handler" in out

    def test_emit_label_emits_label_assigned(self, make_bot):
        bot, fake = make_bot(_RecorderBot)
        bot.emit_label("msg-1", [("bot-sentiment", "sentiment", "1.0.0", {"score": 0.9})])
        emits = fake.emits_for(EventName.LABEL_ASSIGNED)
        assert len(emits) == 1
        data = emits[0]
        assert data["target_msg_id"] == "msg-1"
        assert data["labels"] == [["bot-sentiment", "sentiment", "1.0.0", {"score": 0.9}]]
        assert data["applied_by"] == "bot-recorder"

    async def test_label_subscriptions_replayed_on_reconnect(self, make_bot):
        """BUSINESS RULE (§2.4): subscriptions replayed after reconnect."""
        bot, fake = make_bot(_RecorderBot)
        bot.register_label_subscription("s1", {"test": True})
        assert fake.emits_for(EventName.REGISTER_LABEL_SUBSCRIPTION) == []

        await bot.on_bot_authenticated({"groups": []})
        sub_emits = fake.emits_for(EventName.REGISTER_LABEL_SUBSCRIPTION)
        assert len(sub_emits) == 1
        assert sub_emits[0]["name"] == "s1"

    def test_empty_predicate_normalizes_to_empty_dict(self, make_bot):
        """BUSINESS RULE (§2.3): None predicate = {} = match all."""
        bot, _ = make_bot(_RecorderBot)
        bot.register_label_subscription("s1", None)
        assert bot._registered_label_subscriptions[0]["predicate"] == {}


# ---------------------------------------------------------------------------
# send_form (MEADOWS-forms-intent §2.1, §2.3, §2.6)
# ---------------------------------------------------------------------------


class TestSendForm:
    def test_send_form_emits_message_with_interactive_form_label(self, make_bot):
        """BUSINESS RULE (§2.3): the form message carries the interactive-form label."""
        bot, fake = make_bot(_RecorderBot)
        bot.send_form(
            content="Hoe was je dag?",
            answer_label=("bot-recorder", "checkin-resp", "1.0.0"),
            form_html="<form><input name='mood'></form>",
        )

        emits = fake.emits_for(EventName.MESSAGE)
        assert len(emits) == 1
        data = emits[0]
        assert data["type"] == "bot"
        assert data["content"] == "Hoe was je dag?"

        # Must have interactive-form label AND answer_label
        labels = data["labels"]
        assert len(labels) == 2
        # Label NamedTuple serializes with metadata=None as trailing element
        assert labels[0][:3] == ("meadows", "interactive-form", "1.0.0")
        assert labels[1][:3] == ("bot-recorder", "checkin-resp", "1.0.0")

    def test_send_form_places_answer_label_in_metadata(self, make_bot):
        """BUSINESS RULE (§2.6): answer_label in metadata['meadows']['form_handling']."""
        bot, fake = make_bot(_RecorderBot)
        bot.send_form(
            content="check-in",
            answer_label=("bot-recorder", "resp", "1.0.0"),
        )

        data = fake.emits_for(EventName.MESSAGE)[0]
        fh = data["metadata"]["meadows"]["form_handling"]
        assert fh["answer_label"] == ["bot-recorder", "resp", "1.0.0"]

    def test_send_form_places_form_html_in_metadata(self, make_bot):
        """BUSINESS RULE (§2.3): form HTML is in metadata, not content."""
        bot, fake = make_bot(_RecorderBot)
        bot.send_form(
            content="fill this out",
            answer_label=("a", "b", "1.0.0"),
            form_html="<form id='f1'><input name='x'></form>",
        )

        data = fake.emits_for(EventName.MESSAGE)[0]
        fh = data["metadata"]["meadows"]["form_handling"]
        assert fh["form"] == "<form id='f1'><input name='x'></form>"

    def test_send_form_without_html_omits_form_key(self, make_bot):
        """No form_html → no 'form' key in form_handling metadata."""
        bot, fake = make_bot(_RecorderBot)
        bot.send_form(
            content="just a description",
            answer_label=("a", "b", "1.0.0"),
        )

        data = fake.emits_for(EventName.MESSAGE)[0]
        fh = data["metadata"]["meadows"]["form_handling"]
        assert "form" not in fh
        assert fh["answer_label"] == ["a", "b", "1.0.0"]

    def test_send_form_uses_group_id(self, make_bot):
        """group_id is passed through to the message."""
        bot, fake = make_bot(_RecorderBot)
        bot.send_form(
            content="form",
            answer_label=("a", "b", "1.0.0"),
            group_id="team-a",
        )

        data = fake.emits_for(EventName.MESSAGE)[0]
        assert data["group_id"] == "team-a"

    def test_send_form_message_type_is_bot(self, make_bot):
        """BUSINESS RULE (§2.1): form is a BOT message, not FORM_SUBMISSION."""
        bot, fake = make_bot(_RecorderBot)
        bot.send_form(
            content="form",
            answer_label=("a", "b", "1.0.0"),
        )

        data = fake.emits_for(EventName.MESSAGE)[0]
        assert data["type"] == MessageType.BOT.value
