#!/usr/bin/env python3
"""Sentiment Bot — produces sentiment labels on messages.

BUSINESS RULE (MEADOWS-labeling-intent §2.5): bots can produce labels
server-side.  This bot subscribes to ALL messages (empty predicate with
``deliver="message_only"``), runs simple keyword-based sentiment
analysis, and emits a ``("bot-sentiment", "sentiment", "1.0.0")``
label on each message with a score and tone in metadata.

BUSINESS RULE (MEADOWS-labeling-intent §2.1): this bot demonstrates
the label-routing pipeline.  Other bots subscribe to its labels and
react to specific sentiment scores — the cascade described in §2.5.

This is an example bot — real sentiment analysis would use an LLM or
NLP library.  The keyword approach here is deliberately simple so the
labeling mechanism is the focus, not the NLP.

Usage:
    MEADOWS_JWT_TOKEN=<token> python -m meadows.bot.examples.sentiment_bot
"""

from __future__ import annotations

from typing import Any, ClassVar

from meadows.bot import BaseBot
from meadows.protocol import Label


# Simple keyword lists for demo sentiment analysis.
_ANGRY_WORDS = {"angry", "furious", "hate", "terrible", "awful", "worst", "horrible", "disgusting", "rage", "livid"}
_SAD_WORDS = {"sad", "unhappy", "depressed", "miserable", "heartbroken", "grief", "sorrow", "melancholy", "gloomy"}
_HAPPY_WORDS = {
    "happy", "joy", "wonderful", "great", "love", "amazing", "fantastic", "excellent", "brilliant", "awesome",
}


def _analyze_sentiment(text: str) -> dict[str, Any]:
    """Simple keyword-based sentiment analysis for demo purposes.

    Returns a dict with ``score`` (-1.0 to 1.0) and ``tone`` (dominant emotion).
    """
    words = set(text.lower().split())
    angry = len(words & _ANGRY_WORDS)
    sad = len(words & _SAD_WORDS)
    happy = len(words & _HAPPY_WORDS)

    total = angry + sad + happy
    if total == 0:
        return {"score": 0.0, "tone": "neutral"}

    # Score: -1.0 (all angry) to +1.0 (all happy)
    score = (happy - angry) / max(total, 1)

    # Dominant tone
    if angry >= sad and angry >= happy:
        tone = "angry"
    elif sad >= happy:
        tone = "sad"
    else:
        tone = "happy"

    return {"score": round(score, 2), "tone": tone}


class SentimentBot(BaseBot):
    """Produces sentiment labels on every message it sees.

    BUSINESS RULE (MEADOWS-labeling-intent §2.5): this bot is a label
    *producer*.  It subscribes to all messages (empty predicate,
    ``deliver="message_only"``) and emits a sentiment label on each one.
    Other bots subscribe to ``bot-sentiment`` labels to react.

    The label: ``("bot-sentiment", "sentiment", "1.0.0", {"score": ..., "tone": ...})``

    Commands:
        @sentiment help   - Show available commands
        @sentiment stats  - Show sentiment analysis stats
    """

    BOT_NAME = "sentiment"
    BOT_DESCRIPTION = "Analyzes message sentiment and produces labels"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "help", "description": "Show available commands"},
        {"name": "stats", "description": "Show sentiment analysis statistics"},
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.analyzed_count = 0
        self.tally: dict[str, int] = {"angry": 0, "sad": 0, "happy": 0, "neutral": 0}
        self._seen_msg_ids: set[str] = set()
        # Register for MESSAGE events so we can analyze content.
        # BUSINESS RULE (§2.5): deliver="message_only" on our label
        # subscription makes the server emit MESSAGE events to us.
        from meadows.protocol import EventName
        self.client.on(EventName.MESSAGE, self._on_message)

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
                "Sentiment Analysis Stats:",
                f"  Messages analyzed: {self.analyzed_count}",
                f"  Angry:   {self.tally['angry']}",
                f"  Sad:     {self.tally['sad']}",
                f"  Happy:   {self.tally['happy']}",
                f"  Neutral: {self.tally['neutral']}",
            ]
            return "\n".join(lines)
        return None

    def _on_message(self, data: dict[str, Any]) -> None:
        """Analyze every message and produce a sentiment label.

        BUSINESS RULE (MEADOWS-labeling-intent §2.5): the bot produces
        labels on messages it receives.  The server deduplicates via
        the (origin, label, semver, message_id) key.
        """
        content = data.get("content", "")
        msg_id = data.get("id", "")
        sender = data.get("bot_name") or data.get("user_id", "unknown")

        # Skip bot's own messages
        if data.get("bot_name") == self.BOT_NAME:
            return

        # Skip non-content messages (reactions, system, etc.)
        if not content:
            return

        # Deduplicate: room broadcast + label subscription may deliver twice
        if msg_id in self._seen_msg_ids:
            return
        self._seen_msg_ids.add(msg_id)

        self.log(f"Analyzing msg {msg_id} from {sender}: {content[:50]}...")

        sentiment = _analyze_sentiment(content)
        self.analyzed_count += 1
        tone = sentiment["tone"]
        self.tally[tone] = self.tally.get(tone, 0) + 1

        # Emit a label with the sentiment metadata
        lbl = Label("bot-sentiment", "sentiment", "1.0.0", sentiment)
        self.emit_label(msg_id, [lbl])
        self.log(f"Produced label: sentiment={sentiment}")


if __name__ == "__main__":
    bot = SentimentBot()
    # BUSINESS RULE (§2.3): empty predicate = match all messages.
    # deliver="message_only" so we get the MESSAGE event with content.
    bot.register_label_subscription("all_msgs", {}, scope="global", deliver="message_only")
    bot.connect()
