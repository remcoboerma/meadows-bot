FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /build

# Build context is the repo root (docker-compose.yml: build.context: ..), because
# pyproject.toml resolves meadows-protocol and meadows-client through
# [tool.uv.sources] as ../meadows-protocol and ../meadows-client. Those siblings
# must exist at exactly those relative paths next to meadows-bot/, so they are
# copied in first and installed on their own for layer caching.
COPY meadows-protocol/ meadows-protocol/
COPY meadows-client/pyproject.toml meadows-client/README.md meadows-client/
COPY meadows-client/src/ meadows-client/src/
COPY meadows-bot/pyproject.toml meadows-bot/README.md meadows-bot/
COPY meadows-bot/src/ meadows-bot/src/

RUN cd /build/meadows-protocol && uv pip install --system --no-cache . && \
    cd /build/meadows-client && uv pip install --system --no-cache . && \
    cd /build/meadows-bot && uv pip install --system --no-cache .

CMD ["python", "-c", "import meadows.bot; print('meadows-bot', meadows.bot.__version__)"]
