#!/usr/bin/env python3
"""Label Listener Bot — subscribes to labels and reacts to sentiment.

BUSINESS RULE (MEADOWS-labeling-intent §2.5): this bot demonstrates
the *consumer* side of the label cascade.  It subscribes to labels
produced by the sentiment_bot and reacts when it detects high-anger
messages.

BUSINESS RULE (MEADOWS-labeling-intent §2.1): labels are how messages
reach subscribers.  This bot never sees raw messages — it receives
``LABEL_ASSIGNED`` events from the server because its predicate
matches the sentiment labels the sentiment_bot produces.

The cascade:
  1. User sends a message
  2. sentiment_bot receives it (via label subscription, message_only)
  3. sentiment_bot emits ``LABEL_ASSIGNED`` with sentiment metadata
  4. Server evaluates this bot's subscription predicate against the label
  5. Predicate matches → server delivers ``LABEL_ASSIGNED`` to this bot
  6. This bot reacts to high-anger scores

Usage:
    MEADOWS_JWT_TOKEN=<token> python -m meadows.bot.examples.label_listener_bot
"""

from __future__ import annotations

from typing import Any, ClassVar

from meadows.bot import BaseBot


class LabelListenerBot(BaseBot):
    """Subscribes to sentiment labels and reacts to high-anger messages.

    BUSINESS RULE (MEADOWS-labeling-intent §2.3): the predicate uses
    JSON Logic to match labels from ``bot-sentiment`` with
    ``semver >=1.0.0``.  Only matching labels are delivered.

    Commands:
        @listener help    - Show available commands
        @listener stats   - Show how many alerts were triggered
    """

    BOT_NAME = "listener"
    BOT_DESCRIPTION = "Listens for angry sentiment labels and alerts"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "help", "description": "Show available commands"},
        {"name": "stats", "description": "Show alert statistics"},
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.alerts_triggered = 0
        self.labels_received = 0

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return command in {"help", "stats"}

    def handle(
        self,
        command: str,
        args: list[str],  # noqa: ARG002
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],  # noqa: ARG002
        thread_context: list[dict[str, Any]],  # noqa: ARG002
    ) -> str | None:
        if command == "help":
            return self.format_help_response()
        if command == "stats":
            lines = [
                "Label Listener Stats:",
                f"  Labels received: {self.labels_received}",
                f"  Alerts triggered: {self.alerts_triggered}",
            ]
            return "\n".join(lines)
        return None

    def _on_angry_sentiment(self, data: dict[str, Any]) -> None:
        """React to angry sentiment labels.

        BUSINESS RULE (MEADOWS-labeling-intent §2.5): the callback
        receives the full ``LABEL_ASSIGNED`` payload.  The ``labels``
        list contains the matched label dicts with metadata.
        """
        labels = data.get("labels", [])
        target_msg_id = data.get("target_msg_id", "")

        self.log(f"RECEIVED LABEL_ASSIGNED: {len(labels)} labels for msg {target_msg_id}")

        for lbl in labels:
            self.labels_received += 1
            metadata = lbl.get("metadata", {})
            score = metadata.get("score", 0)
            tone = metadata.get("tone", "unknown")

            # Only alert on high anger (score < -0.3)
            if tone == "angry" and score < -0.3:
                self.alerts_triggered += 1
                self.log(
                    f"ANGER ALERT on msg {target_msg_id}: "
                    f"score={score}, tone={tone} — "
                    f"total alerts: {self.alerts_triggered}"
                )

    def _on_all_sentiment(self, data: dict[str, Any]) -> None:
        """Track all sentiment labels (logging only)."""
        labels = data.get("labels", [])
        for lbl in labels:
            self.labels_received += 1
            metadata = lbl.get("metadata", {})
            self.log(f"Sentiment label: {metadata}")


if __name__ == "__main__":
    bot = LabelListenerBot()

    # BUSINESS RULE (§2.3): subscribe to bot-sentiment labels with
    # semver >=1.0.0.  The JSON Logic predicate filters on the label
    # fields (origin, label, semver) — only matching labels arrive.
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

    # Register callback for the subscription
    bot.on_label_assigned("sentiment_alerts")(bot._on_angry_sentiment)

    bot.connect()
