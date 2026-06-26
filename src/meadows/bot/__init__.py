"""MEADOWS bot SDK.

BUSINESS RULE (MEADOWS §5 line 131): Document for AI use, because an AI
writes alongside humans. The existing bot-development-guide.md is the
pattern to continue: example-first, copy-pasteable, dense tables.
"""

from meadows.bot.__about__ import __version__
from meadows.bot.base import BaseBot
from meadows.bot.llm import LLMBot

__all__ = ["BaseBot", "LLMBot", "__version__"]
