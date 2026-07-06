"""MEADOWS bot SDK.

BUSINESS RULE (MEADOWS §5 line 131): Document for AI use, because an AI
writes alongside humans. The existing bot-development-guide.md is the
pattern to continue: example-first, copy-pasteable, dense tables.
"""

from meadows.bot.__about__ import __version__
from meadows.bot.base import BaseBot
from meadows.bot.llm import LLMBot

__all__ = ["BaseBot", "LLMBot", "__version__"]


def __getattr__(name):
    if name == "HelpBot":
        from meadows.bot.help_bot import HelpBot
        return HelpBot
    if name == "StatsBot":
        from meadows.bot.stats_bot import StatsBot
        return StatsBot
    if name == "RagBot":
        from meadows.bot.rag_bot import RagBot
        return RagBot
    if name == "SLOBot":
        from meadows.bot.slo_bot import SLOBot
        return SLOBot
    if name == "FetchBot":
        from meadows.bot.fetch_bot import FetchBot
        return FetchBot
    if name == "ExportBot":
        from meadows.bot.export_bot import ExportBot
        return ExportBot
    if name == "ChatBot":
        from meadows.bot.chat_bot import ChatBot
        return ChatBot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
