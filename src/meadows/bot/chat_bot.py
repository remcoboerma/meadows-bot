#!/usr/bin/env python3
"""Chat Bot — Intelligent conversational assistant using LLM.

BUSINESS RULE (MEADOWS §5 line 130): this bot proves that LLMBot's
abstract `query_llm` seam is correct. It implements the single method
a bot author fills in and gets the full conversation flow for free.

BUSINESS RULE (MEADOWS §3.3 line 78): provider specifics stay in the
bot, not in the SDK. ChatBot implements query_llm against an Ollama
API endpoint, configurable via environment variables.

Usage:
    @bot <message>                - Chat with the AI
    @bot <message> --all          - Use all thread context
    @bot <message> -50            - Use last 50 messages

Environment Variables:
    OLLAMA_CHAT_MODEL: Model name (default: gpt-oss:20b)
    OLLAMA_RELAY_HOST: Ollama host (default: localhost)
    OLLAMA_PORT: Ollama port (default: 11434)
    OLLAMA_MAX_TOKENS: Max tokens (default: 512)
    OLLAMA_TEMPERATURE: Temperature (default: 0.3)
"""

from __future__ import annotations

import os
import re
from typing import Any, ClassVar

import httpx

from meadows.bot.llm import LLMBot


class ChatBot(LLMBot):
    """Intelligent conversational bot using an LLM via Ollama.

    Implements query_llm by making HTTP POST requests to an Ollama
    API endpoint. The prompt is assembled from the thread context
    and the current user message, with a Dutch system prompt.
    """

    BOT_NAME = "bot"
    BOT_DESCRIPTION = "Chat met AI - @bot [bericht] voor een intelligent antwoord"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = []
    LLM_TIMEOUT = 120.0

    def __init__(self, token: str | None = None) -> None:
        super().__init__(token=token)
        self.model = os.environ.get("OLLAMA_CHAT_MODEL", "gpt-oss:20b").strip()
        self.host = os.environ.get("OLLAMA_RELAY_HOST", "localhost").strip()
        self.port = int(os.environ.get("OLLAMA_PORT", "11434"))
        self.base_url = f"http://{self.host}:{self.port}"
        self.max_tokens = int(os.environ.get("OLLAMA_MAX_TOKENS", "512"))
        self.temperature = float(os.environ.get("OLLAMA_TEMPERATURE", "0.3"))

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return True

    def handle(
        self,
        command: str,  # noqa: ARG002
        args: list[str],  # noqa: ARG002
        raw_args: list[str],
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],
    ) -> str | None:
        if not raw_args:
            return ""

        user_message = " ".join(raw_args).strip()
        if not user_message:
            return ""

        context_window = self._parse_context_flags(raw_args)

        user_message_clean = re.sub(r"(-{1,2}all|-{1,2}full|-\d+)\s*", "", user_message).strip()
        if not user_message_clean:
            return ""

        full_content = message.get("full_content", "")
        if full_content and "@bot" in full_content.lower():
            mention_pos = full_content.lower().find("@bot")
            before_context = full_content[:mention_pos].strip()
            if before_context:
                user_message_clean = f"{before_context} {user_message_clean}".strip()

        _ = self._detect_language(user_message_clean)

        if context_window is None:
            filtered_context = thread_context
        else:
            filtered_context = thread_context[-context_window:] if thread_context else []

        current_message_id = message.get("id")
        filtered_context = [msg for msg in filtered_context if msg.get("id") != current_message_id]

        current_user = message.get("username") or message.get("user_id", "User")

        context_section = ""
        if filtered_context:
            context_section = "[CONVERSATION CONTEXT - FOR REFERENCE ONLY]\n"
            for msg in filtered_context:
                sender = msg.get("bot_name") or msg.get("username", msg.get("user_id", "Unknown"))
                content = msg.get("content", "")
                context_section += f"- {sender}: {content}\n"
            context_section += "[END CONTEXT]\n\n"

        task_section = f"[YOUR TASK - RESPOND TO THIS ONLY]:\n{current_user}: {user_message_clean}"
        prompt = f"{context_section}{task_section}"

        system_prompt = """Je bent een Nederlandse gespreksassistent in een groepschat.

JIJ BENT DEGENE DIE ANTWOORDT:
- Je bent NIET de vraagsteller
- JIJ GEEFT HET ANTWOORD
- Geef je mening, je reactie, je antwoord DIRECT

ABSOLUTE REGELS:
1. Antwoord ALTIJD en ALLEEN in het Nederlands - geen Engels, geen menging
2. Reageer ALLEEN op het bericht in [YOUR TASK - RESPOND TO THIS ONLY]
3. NIET vragen wat je moet doen, NIET om verduidelijking vragen
4. NIET reageren op berichten in [CONVERSATION CONTEXT]
5. Gewoon JEZELF antwoorden - direct, duidelijk, Nederlands

JE TAAK:
- Lees: [YOUR TASK - RESPOND TO THIS ONLY]
- GEEF HET ANTWOORD
- Zeg wat JIJ denkt/weet/berenderneert

ANTWOORDRICHTLIJNEN:
- Antwoord beknopt maar volledig
- Antwoord natuurlijk, zoals een echte Nederlander in een chat zou doen
- Gebruik markdown voor leesbare antwoorden"""

        full_prompt = f"{system_prompt}\n\n{prompt}"
        return self.query_llm(full_prompt)

    def query_llm(self, prompt: str) -> str:
        """Query Ollama API and return the response.

        Makes an HTTP POST to the Ollama generate endpoint. The
        prompt includes system instructions and the conversation
        context assembled by handle().
        """
        if not self.model:
            return "[LLM niet geconfigureerd - stel OLLAMA_CHAT_MODEL in]"

        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "num_predict": self.max_tokens,
                "temperature": self.temperature,
            }

            response = httpx.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.LLM_TIMEOUT,
            )

            if response.status_code >= 400:
                return f"[Ollama fout: HTTP {response.status_code}]"

            result = response.json()
            return result.get("response", "").strip()

        except httpx.ConnectError:
            return f"[Kan geen verbinding maken met Ollama op {self.base_url}]"
        except httpx.TimeoutException:
            return "[Ollama verzoek time-out - model laadt mogelijk nog]"
        except Exception as e:
            return f"[Ollama fout: {str(e)[:100]}]"

    def _parse_context_flags(self, raw_args: list[str]) -> int | None:
        raw_string = " ".join(raw_args)
        if re.search(r"(-{1,2}all|-{1,2}full)\b", raw_string):
            return None
        match = re.search(r"-(\d+)(?:\s|$)", raw_string)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return 30
        return 30

    def _detect_language(self, text: str) -> str:
        dutch_words = {
            "je", "jij", "dat", "dit", "wat", "wie", "hoe", "waarom",
            "kunt", "kan", "ben", "zijn", "is", "het", "een", "van",
            "met", "ook", "niet", "meer", "over", "voor", "naar", "als",
            "kun", "mag", "wil", "zal", "zou", "heeft", "hebben",
        }
        words = text.lower().split()
        dutch_count = sum(1 for word in words if word.strip(".,!?;:") in dutch_words)
        return "Dutch" if dutch_count > len(words) * 0.15 else "English"


if __name__ == "__main__":
    ChatBot().connect()
