"""Tests for LabelListenerBot — the label-consuming example bot.

BUSINESS RULE (MEADOWS-labeling-intent §2.5): this bot demonstrates
how bots subscribe to labels produced by other bots. Tests verify
subscription setup and reaction to label events without a real server.
"""

from __future__ import annotations

from meadows.bot.examples.label_listener_bot import LabelListenerBot


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestLabelListenerBotConstruction:
    def test_bot_name(self, make_bot):
        bot, _ = make_bot(LabelListenerBot)
        assert bot.BOT_NAME == "listener"

    def test_initial_state(self, make_bot):
        bot, _ = make_bot(LabelListenerBot)
        assert bot.alerts_triggered == 0
        assert bot.labels_received == 0


# ---------------------------------------------------------------------------
# Command handling
# ---------------------------------------------------------------------------


class TestLabelListenerBotCommands:
    def test_should_handle_known_commands(self, make_bot):
        bot, _ = make_bot(LabelListenerBot)
        assert bot.should_handle("help", []) is True
        assert bot.should_handle("stats", []) is True

    def test_should_reject_unknown(self, make_bot):
        bot, _ = make_bot(LabelListenerBot)
        assert bot.should_handle("echo", []) is False

    def test_stats_returns_counts(self, make_bot):
        bot, _ = make_bot(LabelListenerBot)
        bot.labels_received = 10
        bot.alerts_triggered = 3
        result = bot.handle("stats", [], [], {}, [])
        assert "Labels received: 10" in result
        assert "Alerts triggered: 3" in result


# ---------------------------------------------------------------------------
# Label reaction
# ---------------------------------------------------------------------------


class TestLabelListenerBotReaction:
    def test_angry_label_triggers_alert(self, make_bot):
        """BUSINESS RULE (§2.5): callback fires on matching label."""
        bot, _ = make_bot(LabelListenerBot)
        bot._on_angry_sentiment({
            "labels": [
                {"origin": "bot-sentiment", "label": "sentiment", "semver": "1.0.0",
                 "metadata": {"score": -0.8, "tone": "angry"}},
            ],
            "target_msg_id": "msg-42",
            "applied_by": "bot-sentiment",
            "subscription_name": "sentiment_alerts",
        })
        assert bot.labels_received == 1
        assert bot.alerts_triggered == 1

    def test_happy_label_no_alert(self, make_bot):
        """Happy messages should not trigger alerts."""
        bot, _ = make_bot(LabelListenerBot)
        bot._on_angry_sentiment({
            "labels": [
                {"origin": "bot-sentiment", "label": "sentiment", "semver": "1.0.0",
                 "metadata": {"score": 0.9, "tone": "happy"}},
            ],
            "target_msg_id": "msg-43",
            "applied_by": "bot-sentiment",
            "subscription_name": "sentiment_alerts",
        })
        assert bot.labels_received == 1
        assert bot.alerts_triggered == 0

    def test_mild_anger_no_alert(self, make_bot):
        """Score > -0.3 should not trigger alert (threshold)."""
        bot, _ = make_bot(LabelListenerBot)
        bot._on_angry_sentiment({
            "labels": [
                {"origin": "bot-sentiment", "label": "sentiment", "semver": "1.0.0",
                 "metadata": {"score": -0.1, "tone": "angry"}},
            ],
            "target_msg_id": "msg-44",
            "applied_by": "bot-sentiment",
            "subscription_name": "sentiment_alerts",
        })
        assert bot.labels_received == 1
        assert bot.alerts_triggered == 0

    def test_multiple_labels_in_event(self, make_bot):
        """Multiple labels in one event — each evaluated."""
        bot, _ = make_bot(LabelListenerBot)
        bot._on_angry_sentiment({
            "labels": [
                {"origin": "bot-sentiment", "label": "sentiment", "semver": "1.0.0",
                 "metadata": {"score": -0.9, "tone": "angry"}},
                {"origin": "bot-sentiment", "label": "sentiment", "semver": "1.0.0",
                 "metadata": {"score": 0.5, "tone": "happy"}},
            ],
            "target_msg_id": "msg-45",
            "applied_by": "bot-sentiment",
            "subscription_name": "sentiment_alerts",
        })
        assert bot.labels_received == 2
        assert bot.alerts_triggered == 1  # only the angry one


# ---------------------------------------------------------------------------
# Subscription setup
# ---------------------------------------------------------------------------


class TestLabelListenerBotSubscription:
    def test_subscription_registered(self, make_bot):
        """BUSINESS RULE (§2.3): subscription with predicate stored."""
        bot, _ = make_bot(LabelListenerBot)
        bot.register_label_subscription(
            "sentiment_alerts",
            {
                "and": [
                    {"regex_match": [{"var": "origin"}, "^bot-sentiment$"]},
                    {"regex_match": [{"var": "label"}, "^sentiment$"]},
                    {"semver_match": [">=1.0.0", {"var": "semver"}]},
                ]
            },
            scope="global",
            deliver="label_only",
        )
        assert len(bot._registered_label_subscriptions) == 1
        sub = bot._registered_label_subscriptions[0]
        assert sub["name"] == "sentiment_alerts"
        assert sub["scope"] == "global"
        assert sub["deliver"] == "label_only"
        assert "and" in sub["predicate"]

    def test_handler_registered_via_decorator(self, make_bot):
        bot, _ = make_bot(LabelListenerBot)
        bot.on_label_assigned("sentiment_alerts")(bot._on_angry_sentiment)
        assert "sentiment_alerts" in bot._label_assigned_handlers
