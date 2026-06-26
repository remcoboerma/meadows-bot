"""LLMBot — minimal abstract LLM bot.

BUSINESS RULE (MEADOWS §3.3 line 78): provider specifics (Ollama,
OpenRouter, Scaleway) are non-core and stay out of the PoC. This class
gives bot authors a single seam to fill — `query_llm` — and a default
`handle()` that wires it into the conversation context.

BUSINESS RULE (MEADOWS §5 line 130): an LLM bot author writes
`query_llm` (and BOT_NAME/BOT_COMMANDS). Everything else — the context
assembly, the response emission — is inherited. That's the quick-start
contract for LLM bots.

BUSINESS RULE (MEADOWS §2 line 41): this class extends BaseBot and
imports nothing from meadows.server. The LLM call is opaque to the
system (§3.2 line 65: "de body van een gewoon chatbericht is opaak
Markdown").
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar

from meadows.bot.base import BaseBot


class LLMBot(BaseBot):
    """Abstract LLM bot: fill in `query_llm`, inherit the rest.

    BUSINESS RULE (MEADOWS §3.3 line 78): no provider specifics here.
    A subclass implements `query_llm(prompt) -> str` against whatever
    backend it chooses (Ollama, Scaleway, OpenRouter, a mock). The
    system never sees the provider — only the resulting string.

    BUSINESS RULE (MEADOWS §5 line 130): the author surface for an LLM
    bot is BOT_NAME + BOT_COMMANDS + query_llm. The default handle()
    assembles the thread context into a prompt and returns the LLM's
    response.
    """

    BOT_NAME = "llmbot"
    BOT_DESCRIPTION = "Base LLM bot class"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = []

    @abstractmethod
    def query_llm(self, prompt: str) -> str:
        """Query the LLM with a prompt and return its response.

        BUSINESS RULE (MEADOWS §3.3 line 78): this is the single seam
        a provider-specific subclass fills. The PoC ships no
        implementation; a real bot overrides this with an Ollama,
        Scaleway, or OpenRouter call.

        Args:
            prompt: The assembled conversation prompt.

        Returns:
            The LLM's response string.
        """

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        """Handle any command this bot advertises in BOT_COMMANDS.

        BUSINESS RULE (MEADOWS §5 line 130): an LLM bot author who
        just wants "the bot responds to everything it advertises"
        shouldn't have to write this. The default is: handle if the
        command is in the manifest. Override for custom routing.
        """
        advertised = {cmd["name"] for cmd in self.BOT_COMMANDS if "name" in cmd}
        return command in advertised

    def handle(
        self,
        command: str,
        args: list[str],
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],
    ) -> str | None:
        """Default handle: assemble a prompt from the context and query the LLM.

        BUSINESS RULE (MEADOWS §5 line 130): this is the inherited
        behavior an LLM bot author gets for free. The prompt is the
        thread context (as "sender: content" lines) plus the current
        command and args. The LLM's response is returned as the bot
        response.

        BUSINESS RULE (MEADOWS §3.2 line 65): the prompt assembly is
        opaque to the system — it's just Markdown the bot sends to its
        backend. The system doesn't know an LLM is involved.
        """
        prompt = self._build_prompt(command, args, message, thread_context)
        return self.query_llm(prompt)

    def _build_prompt(
        self,
        command: str,
        args: list[str],
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],
    ) -> str:
        """Assemble a conversation prompt from the thread context and current command.

        BUSINESS RULE (MEADOWS §5 line 130): this is the default
        prompt shape. An author who wants a different shape overrides
        handle() entirely; an author who wants this shape but a
        different backend only overrides query_llm(). That's the
        minimal-surface contract.
        """
        # BUSINESS RULE: thread context is "sender: content" lines, most
        # recent last. This is the shape an LLM expects for a chat
        # transcript. The system passes thread_context opaquely (§3.2).
        lines: list[str] = []
        for msg in thread_context:
            sender = msg.get("username") or msg.get("user_id") or msg.get("bot_name") or "unknown"
            content = msg.get("content", "")
            lines.append(f"{sender}: {content}")

        # BUSINESS RULE: the current command is the user's latest turn.
        user = message.get("username") or message.get("user_id") or "user"
        current = f"{command} {' '.join(args)}".strip()
        lines.append(f"{user}: {current}")

        return "\n".join(lines)


__all__ = ["LLMBot"]
