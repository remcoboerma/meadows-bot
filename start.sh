#!/bin/bash
MEADOWS_JWT_TOKEN=$(cd ../meadows-server && uv run invoke bot-jwt --name=todo --expiry=1y) uv run python -m meadows.bot.examples.todo_bot
