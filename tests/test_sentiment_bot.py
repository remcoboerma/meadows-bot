"""Tests for SentimentBot — the label-producing example bot.

BUSINESS RULE (MEADOWS-labeling-intent §2.5): this bot demonstrates
how bots produce labels. Tests verify the analysis logic and the
LABEL_ASSIGNED emission without a real server.
"""

from __future__ import annotations

from meadows.bot.examples.sentiment_bot import SentimentBot, _analyze_sentiment
from meadows.protocol import EventName


# ---------------------------------------------------------------------------
# Sentiment analysis function
# ---------------------------------------------------------------------------


class TestAnalyzeSentiment:
    def test_neutral_for_empty_text(self):
        result = _analyze_sentiment("")
        assert result["score"] == 0.0
        assert result["tone"] == "neutral"

    def test_angry_detection(self):
        result = _analyze_sentiment("I am furious and angry about this terrible service")
        assert result["tone"] == "angry"
        assert result["score"] < 0

    def test_happy_detection(self):
        result = _analyze_sentiment("This is wonderful and amazing, I love it")
        assert result["tone"] == "happy"
        assert result["score"] > 0

    def test_sad_detection(self):
        result = _analyze_sentiment("I am so sad and miserable today")
        assert result["tone"] == "sad"
        # sad is negative on the angry side, but score depends on mix
        assert result["score"] <= 0

    def test_mixed_sentiment_angry_dominant(self):
        result = _analyze_sentiment("happy happy angry furious hate terrible")
        assert result["tone"] == "angry"
        assert result["score"] < 0

    def test_score_range(self):
        result = _analyze_sentiment("angry furious hate terrible worst")
        assert -1.0 <= result["score"] <= 1.0

    def test_neutral_for_no_keywords(self):
        result = _analyze_sentiment("the quick brown fox jumps over the lazy dog")
        assert result["tone"] == "neutral"
        assert result["score"] == 0.0


# ---------------------------------------------------------------------------
# SentimentBot construction
# ---------------------------------------------------------------------------


class TestSentimentBotConstruction:
    def test_bot_name(self, make_bot):
        bot, _ = make_bot(SentimentBot)
        assert bot.BOT_NAME == "sentiment"

    def test_initial_state(self, make_bot):
        bot, _ = make_bot(SentimentBot)
        assert bot.analyzed_count == 0
        assert bot.tally == {"angry": 0, "sad": 0, "happy": 0, "neutral": 0}


# ---------------------------------------------------------------------------
# Command handling
# ---------------------------------------------------------------------------


class TestSentimentBotCommands:
    def test_should_handle_known_commands(self, make_bot):
        bot, _ = make_bot(SentimentBot)
        assert bot.should_handle("help", []) is True
        assert bot.should_handle("stats", []) is True

    def test_should_reject_unknown(self, make_bot):
        bot, _ = make_bot(SentimentBot)
        assert bot.should_handle("echo", []) is False

    def test_help_returns_formatted(self, make_bot):
        bot, _ = make_bot(SentimentBot)
        result = bot.handle("help", [], [], {}, [])
        assert "Sentiment Bot Commands:" in result

    def test_stats_returns_tally(self, make_bot):
        bot, _ = make_bot(SentimentBot)
        bot.analyzed_count = 5
        bot.tally = {"angry": 2, "sad": 1, "happy": 1, "neutral": 1}
        result = bot.handle("stats", [], [], {}, [])
        assert "Messages analyzed: 5" in result
        assert "Angry:   2" in result


# ---------------------------------------------------------------------------
# Label production
# ---------------------------------------------------------------------------


class TestSentimentBotLabelProduction:
    def test_on_message_produces_label(self, make_bot):
        """BUSINESS RULE (§2.5): bot produces labels on messages."""
        bot, fake = make_bot(SentimentBot)
        bot._on_message({
            "id": "msg-1",
            "content": "I am furious about this",
            "user_id": "user-alice",
        })
        emits = fake.emits_for(EventName.LABEL_ASSIGNED)
        assert len(emits) == 1
        data = emits[0]
        assert data["target_msg_id"] == "msg-1"
        assert len(data["labels"]) == 1
        lbl = data["labels"][0]
        assert lbl[0] == "bot-sentiment"
        assert lbl[1] == "sentiment"
        assert lbl[2] == "1.0.0"
        metadata = lbl[3]
        assert metadata["tone"] == "angry"
        assert metadata["score"] < 0

    def test_on_message_skips_own_messages(self, make_bot):
        """Bot should not label its own messages."""
        bot, fake = make_bot(SentimentBot)
        bot._on_message({
            "id": "msg-2",
            "content": "I am angry",
            "bot_name": "sentiment",
        })
        assert fake.emits_for(EventName.LABEL_ASSIGNED) == []

    def test_on_message_increments_counter(self, make_bot):
        bot, _ = make_bot(SentimentBot)
        bot._on_message({"id": "m1", "content": "hello"})
        bot._on_message({"id": "m2", "content": "I am angry"})
        assert bot.analyzed_count == 2
        assert bot.tally["neutral"] == 1
        assert bot.tally["angry"] == 1

    def test_on_message_happy_produces_positive_label(self, make_bot):
        bot, fake = make_bot(SentimentBot)
        bot._on_message({"id": "msg-3", "content": "wonderful amazing love"})
        lbl = fake.emits_for(EventName.LABEL_ASSIGNED)[0]["labels"][0]
        assert lbl[3]["tone"] == "happy"
        assert lbl[3]["score"] > 0
