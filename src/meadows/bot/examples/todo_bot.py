#!/usr/bin/env python3
"""Todo Bot — CRUD demo using MEADOWS forms.

Demonstrates the new forms system (MEADOWS-forms-intent):
- Sending interactive forms via ``send_form()`` with answer_label in metadata
- Receiving form submissions via label subscriptions
- Response data in ``metadata['meadows']['form_handling']['response']``
- data-action buttons for list/toggle/delete (user messages, not forms)

Commands:
    @todo /add            - Show form to add a new todo
    @todo /list           - Show all todos with action buttons
    @todo /edit <id>      - Edit a todo's title (via form)
    @todo /toggle <id>    - Toggle done/undone state
    @todo /delete <id>    - Delete a todo
    @todo /help           - Show available commands

Usage:
    MEADOWS_JWT_TOKEN=<token> python -m meadows.bot.examples.todo_bot
"""

from __future__ import annotations

from typing import Any, ClassVar

from meadows.bot import BaseBot
from meadows.protocol import EventName, MessageType


class TodoBot(BaseBot):
    """Todo management bot with CRUD form interface.

    BUSINESS RULE (MEADOWS-forms-intent §2.1): this bot demonstrates
    message-based form routing. It sends forms with an answer_label
    in metadata, and receives submissions via label subscriptions.
    Multiple bots could subscribe to the same answer_label — the
    todo bot is just one consumer.
    """

    BOT_NAME = "todo"
    BOT_DESCRIPTION = "Manage todos via interactive forms (Create, Read, Update, Delete)"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "add", "description": "Add a new todo"},
        {"name": "list", "description": "List all todos"},
        {"name": "edit", "description": "Edit a todo by ID (opens form)"},
        {"name": "toggle", "description": "Toggle done/undone state"},
        {"name": "delete", "description": "Delete a todo"},
        {"name": "help", "description": "Show available commands"},
    ]
    BOT_CONTEXT_LIMIT = 30

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.todos: dict[str, list[dict[str, Any]]] = {}

        # Listen for form submissions via label subscription.
        # BUSINESS RULE (MEADOWS-forms-intent §2.8): form submissions
        # arrive as MESSAGE events with type=FORM_SUBMISSION. The label
        # subscription delivers them; we filter on type in the handler.
        self.client.on(EventName.MESSAGE, self._on_message)

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return command in {"add", "list", "edit", "toggle", "delete", "help"}

    def handle(
        self,
        command: str,
        args: list[str],
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],  # noqa: ARG002
    ) -> str | None:
        group_id = message.get("group_id", "general")

        if command == "add":
            self._send_add_form(group_id)
            return None

        if command == "list":
            self._send_todo_list(group_id)
            return None

        if command == "edit":
            if not args:
                return "Usage: @todo /edit <todo_id>"
            self._send_edit_form(group_id, args[0])
            return None

        if command == "toggle":
            if not args:
                return "Usage: @todo /toggle <todo_id>"
            return self._toggle_todo(group_id, args[0])

        if command == "delete":
            if not args:
                return "Usage: @todo /delete <todo_id>"
            return self._delete_todo(group_id, args[0])

        if command == "help":
            return self.format_help_response()

        return None

    # ------------------------------------------------------------------
    # Form sending
    # ------------------------------------------------------------------

    def _send_add_form(self, group_id: str) -> None:
        """Send a form for adding a new todo.

        BUSINESS RULE (MEADOWS-forms-intent §2.3): content is human-readable,
        form HTML is in metadata. The answer_label determines where responses
        are routed.
        """
        form_html = (
            '<label>Title: <input type="text" name="title" '
            'placeholder="What needs to be done?" required></label>'
            '<button type="submit">Add Todo</button>'
        )
        self.send_form(
            content="Add a new todo:",
            answer_label=(f"bot-{self.BOT_NAME}", "todo-add-response", "1.0.0"),
            form_html=form_html,
            group_id=group_id,
        )

    def _send_edit_form(self, group_id: str, todo_id: str) -> None:
        """Send a prepopulated form for editing a todo."""
        todos = self.todos.get(group_id, [])
        todo = next((t for t in todos if t["id"] == todo_id), None)
        if not todo:
            self._send_text(group_id, f"Todo `{todo_id}` not found.")
            return
        form_html = (
            f'<input type="hidden" name="todo_id" value="{todo_id}">'
            f'<label>New title: <input type="text" name="title" '
            f'value="{self._escape_attr(todo["title"])}" required></label>'
            '<button type="submit">Save</button>'
        )
        self.send_form(
            content=f"Edit todo `{todo_id}`:",
            answer_label=(f"bot-{self.BOT_NAME}", "todo-edit-response", "1.0.0"),
            form_html=form_html,
            group_id=group_id,
        )

    # ------------------------------------------------------------------
    # Form submission handling
    # ------------------------------------------------------------------

    def _on_message(self, data: dict[str, Any]) -> None:
        """Handle incoming messages — filter for form submissions.

        BUSINESS RULE (MEADOWS-forms-intent §2.8): form submissions arrive
        as MESSAGE events with type=FORM_SUBMISSION. We check the type and
        extract response data from metadata['meadows']['form_handling'].
        """
        if data.get("type") != MessageType.FORM_SUBMISSION.value:
            return

        # Skip our own messages
        if data.get("bot_name") == self.BOT_NAME:
            return

        group_id = data.get("group_id", "general")
        labels = data.get("labels", [])
        metadata = data.get("metadata") or {}
        meadows_meta = metadata.get("meadows", {})
        form_handling = meadows_meta.get("form_handling", {})
        response = form_handling.get("response", {})

        # Determine which form was submitted by checking the answer_label
        answer_label_name = None
        for lbl in labels:
            if isinstance(lbl, (list, tuple)) and len(lbl) >= 2 and lbl[0] == f"bot-{self.BOT_NAME}":
                answer_label_name = lbl[1]
                break

        if answer_label_name == "todo-add-response":
            self._handle_add_submission(group_id, response)
        elif answer_label_name == "todo-edit-response":
            self._handle_edit_submission(group_id, response)

    def _handle_add_submission(self, group_id: str, response: dict[str, Any]) -> None:
        """Process a todo-add form submission."""
        title = str(response.get("title", "")).strip()
        if not title:
            self._send_text(group_id, "Todo title cannot be empty.")
            return
        todos = self.todos.setdefault(group_id, [])
        todo_id = f"todo_{len(todos) + 1}"
        todos.append({"id": todo_id, "title": title, "done": False})
        self._send_text(group_id, f"Added todo: **{title}**")
        self._send_todo_list(group_id)

    def _handle_edit_submission(self, group_id: str, response: dict[str, Any]) -> None:
        """Process a todo-edit form submission."""
        todo_id = str(response.get("todo_id", ""))
        new_title = str(response.get("title", "")).strip()
        if not new_title:
            self._send_text(group_id, "Todo title cannot be empty.")
            return
        todos = self.todos.get(group_id, [])
        for todo in todos:
            if todo["id"] == todo_id:
                old_title = todo["title"]
                todo["title"] = new_title
                self._send_text(group_id, f"Renamed: **{old_title}** -> **{new_title}**")
                self._send_todo_list(group_id)
                return
        self._send_text(group_id, f"Todo `{todo_id}` not found.")

    # ------------------------------------------------------------------
    # List rendering
    # ------------------------------------------------------------------

    def _send_todo_list(self, group_id: str) -> None:
        """Send the todo list as an interactive form with action buttons.

        BUSINESS RULE: data-action buttons send commands as user messages.
        This is NOT a form submission — it's the existing convention for
        interactive elements that trigger bot commands.
        """
        todos = self.todos.get(group_id, [])
        if not todos:
            self._send_text(group_id, "No todos yet. Use `@todo /add` to create one.")
            return

        rows = []
        for todo in todos:
            check = "\u2611" if todo["done"] else "\u2610"
            title = f"<s>{self._escape_html(todo['title'])}</s>" if todo["done"] else self._escape_html(todo["title"])
            action_style = ' style="opacity:0.5"' if todo["done"] else ""
            tid = todo["id"]
            rows.append(
                f"<tr{action_style}>"
                f"<td>{check}</td>"
                f"<td>{title}</td>"
                f"<td>"
                f'<button type="button" data-action="@todo /edit {tid}">\u270f\ufe0f Edit</button> '
                f'<button type="button" data-action="@todo /toggle {tid}">'
                f'{"\u2611 Done" if not todo["done"] else "\u21a9 Undo"}</button> '
                f'<button type="button" data-action="@todo /delete {tid}">\U0001f5d1\ufe0f</button>'
                f"</td></tr>"
            )

        form_html = (
            '<table style="border-collapse:collapse;width:100%">'
            "<thead><tr><th></th><th>Todo</th><th>Actions</th></tr></thead>"
            "<tbody>" + "".join(rows) + "</tbody></table>"
        )
        self.send_form(
            content=f"Todos ({len(todos)}):",
            answer_label=(f"bot-{self.BOT_NAME}", "todo-list", "1.0.0"),
            form_html=form_html,
            group_id=group_id,
        )

    # ------------------------------------------------------------------
    # Toggle / delete (plain commands, not forms)
    # ------------------------------------------------------------------

    def _toggle_todo(self, group_id: str, todo_id: str) -> str | None:
        todos = self.todos.get(group_id, [])
        for todo in todos:
            if todo["id"] == todo_id:
                todo["done"] = not todo["done"]
                status = "done" if todo["done"] else "undone"
                self._send_text(group_id, f"Marked **{todo['title']}** as {status}")
                self._send_todo_list(group_id)
                return None
        return f"Todo `{todo_id}` not found."

    def _delete_todo(self, group_id: str, todo_id: str) -> str | None:
        todos = self.todos.get(group_id, [])
        for i, todo in enumerate(todos):
            if todo["id"] == todo_id:
                removed = todos.pop(i)
                self._send_text(group_id, f"Deleted: **{removed['title']}**")
                self._send_todo_list(group_id)
                return None
        return f"Todo `{todo_id}` not found."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_text(self, group_id: str, content: str) -> None:
        """Send a plain text message to a group."""
        from meadows.protocol.envelope import Message, generate_message_id, now_iso

        msg = Message(
            id=generate_message_id(),
            type=MessageType.BOT,
            user_id=self.claims.sub,
            bot_name=self.BOT_NAME,
            group_id=group_id,
            content=content,
            timestamp=now_iso(),
        )
        self._fire_and_forget(EventName.MESSAGE, msg.model_dump(exclude_none=True))

    @staticmethod
    def _escape_html(text: str) -> str:
        """Minimal HTML escaping for safe inline rendering."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _escape_attr(text: str) -> str:
        """Escape for HTML attribute values."""
        return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


if __name__ == "__main__":
    bot = TodoBot()
    # BUSINESS RULE (MEADOWS-forms-intent §2.7): subscribe to our own
    # answer_label so we receive form submissions. deliver="message_only"
    # so we get the full MESSAGE event with metadata.
    bot.register_label_subscription(
        name="todo-forms",
        predicate={
            "and": [
                {"==": [{"var": "origin"}, f"bot-{TodoBot.BOT_NAME}"]},
                {"regex_match": [{"var": "label"}, "^todo-(add|edit)-response$"]},
                {"semver_match": ["^1.0.0", {"var": "semver"}]},
            ]
        },
        scope="global",
        deliver="message_only",
    )
    bot.connect()
