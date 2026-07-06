# meadows-bot

> MEADOWS bot SDK: `BaseBot`, `LLMBot`, and ready-to-use bots. Bot-author-facing package with a fast quick-start.
> Depends on `meadows-client` (transport) and `meadows-protocol` (shapes). Never imports from `meadows-server`.

## What this package contains

- `base.py` — `BaseBot`: the SDK core. Auth, reconnect, registration, routing are hidden.
- `llm.py` — `LLMBot`: minimal abstract LLM bot (no provider specifics in the PoC).
- `examples/echo_bot.py` — the canonical example bot.
- Ready-to-use bots (lazy-loaded via `from meadows.bot import HelpBot`, etc.):
  - `help_bot.py` — static help text (`help`, `bots`, `commands`, `groups`, `guide`)
  - `stats_bot.py` — passive monitoring dashboard (`@stats`, `@stats reset`)
  - `chat_bot.py` — LLM conversational assistant via Ollama
  - `fetch_bot.py` — fetches URLs and converts to Markdown
  - `export_bot.py` — exports a thread to a Markdown file
  - `rag_bot.py` — video/audio fragment search via RAG API
  - `slo_bot.py` — Dutch SLO curriculum learning outcome search

## Quick start

A working bot is `BOT_NAME` + `should_handle` + `handle` + `connect()`. That's the whole contract.

Set the `MEADOWS_JWT_TOKEN` env var (generate with `cd meadows-server && inv bot-jwt --name=mybot --expiry=1y`), then:

```python
from meadows.bot import BaseBot


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
```

## Install

```bash
# Minimal (BaseBot + LLMBot)
uv pip install -e .

# With extra bots that need HTTP dependencies
uv pip install -e ".[examples,dependency-heavy,llm]"
```

## Test

```bash
uv run pytest -q
```

## Included bots

| Bot | Commands | Deps | Description |
|-----|----------|------|-------------|
| `HelpBot` | `help`, `bots`, `commands`, `groups`, `guide` | none | Static help text |
| `StatsBot` | `@stats`, `@stats reset`, `@stats groups`, `@stats top`, `@stats help` | none | Passive monitoring dashboard; observes all traffic |
| `ChatBot` | `chat`, `ask`, `vraag`, `praat` | `[llm]` | LLM assistant via Ollama (requires `OLLAMA_URL`) |
| `FetchBot` | `fetch`, `haal` | `[dependency-heavy]` | Fetches URLs → Markdown |
| `ExportBot` | `export`, `exporteer` | none | Exports a thread to a Markdown file |
| `RagBot` | `rag`, `zoek` | none | Video/audio fragment search via RAG API |
| `SLOBot` | `slo`, `leerdoel` | none | Dutch SLO curriculum learning outcome search |

All bots are lazy-loaded: `from meadows.bot import HelpBot`.

## The protocol boundary

> The system contracts what it itself must understand. What only bots and humans need to understand stays opaque.

This package imports from `meadows.client` (transport) and `meadows.protocol` (shapes), never from `meadows.server`. Server and bot meet only via the protocol declaration. If you find yourself wanting an import from `meadows.server`, something has gone wrong — that belongs in `meadows.protocol` or nowhere.

## Bot-author surface

| What | How |
|---|---|
| Identity | `BOT_NAME`, `BOT_DESCRIPTION`, `BOT_COMMANDS`, `BOT_CONTEXT_LIMIT` (class attrs) |
| Decide | `should_handle(command, args) -> bool` (abstract) |
| Respond | `handle(command, args, raw_args, message, thread_context) -> str \| None` (abstract) |
| Start | `connect()` — waits 3s for the server, then connects and blocks |
| Helpers | `log()`, `get_sender_info()`, `format_help_response()`, `extract_quoted_string()` |
| Patterns | `register_pattern()`, `unregister_pattern()`, `on_pattern_matched()` (decorator) |
| History | `fetch_messages()` |
| Lifecycle hooks | `on_connect()`, `on_disconnect()` (passthrough to client) |

## Defaults and errors are pedagogy

The target user is not a standard Python developer — it's a Dutch teacher (groep 6) working with an AI during a hackathon. Defaults that "just work" and errors in human language matter more than elegance. A bot that fails silently teaches nothing.
