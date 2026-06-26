from __future__ import annotations

from invoke import Context, task

try:
    from edwh import tasks as edwh_tasks
    from edwh import task as edwh_task
except ImportError:  # pragma: no cover - edwh optional in dev without setup
    edwh_tasks = None
    edwh_task = task


def _check_env(key: str, default: str = "", comment: str = "") -> str:
    if edwh_tasks is not None:
        return edwh_tasks.check_env(key, default=default, comment=comment)
    # Fallback when edwh isn't installed (e.g. CI without edwh)
    import os

    val = os.environ.get(key, default)
    print(f"[check_env fallback] {key}={val!r}  # {comment}")
    return val


@task
def setup(c: Context) -> None:
    """Configure environment for meadows-bot."""
    if hasattr(c, "sudo"):
        c.sudo("chmod +x captain-hooks/*.sh")

    _check_env(
        "MEADOWS_SERVER_URL",
        default="http://localhost:8080",
        comment="URL of the meadows-server hub this bot connects to",
    )
    _check_env(
        "MEADOWS_JWT_SECRET",
        default="./shared_keys/jwt.key",
        comment="Path to the JWT secret shared with meadows-server",
    )
    _check_env(
        "BOT_AUTH_ERROR_DISCONNECT_DELAY",
        default="5",
        comment="Seconds to wait before disconnecting after an auth error (avoids reconnect loops)",
    )


@task
def test(c: Context) -> None:
    """Run pytest."""
    c.run("uv run pytest -q")


@task
def lint(c: Context) -> None:
    """Run ruff."""
    c.run("uv run ruff check src tests")


@task
def fmt(c: Context) -> None:
    """Format with ruff."""
    c.run("uv run ruff format src tests")
    c.run("uv run ruff check --fix src tests")


__all__ = ["setup", "test", "lint", "fmt"]
