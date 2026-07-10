#!/usr/bin/env python3
"""Stats Bot — Passive chat monitoring with markdown statistics dashboard.

BUSINESS RULE (MEADOWS §5 line 130): this bot proves that pattern
registration works through the SDK. It registers a catch-all pattern
".*" globally so every message triggers pattern_matched, then builds
a dashboard on demand.

BUSINESS RULE (MEADOWS §3.3 line 74): patterns are core. If
pattern-routing doesn't work, this bot fails — and we discover it here.

Commands:
    @stats              - Full statistics dashboard
    @stats /group <name>  - Stats for a specific group
    @stats /top <n>    - Top N most active users (default: 10)
    @stats /reset       - Reset all statistics
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, ClassVar

from meadows.bot import BaseBot


class StatsBot(BaseBot):
    """Passive chat monitoring bot with on-demand statistics dashboard.

    Registers a catch-all pattern to see every message, then builds a
    markdown dashboard when @stats is called.
    """

    BOT_NAME = "stats"
    BOT_DESCRIPTION = "Monitor chat activity and generate statistics dashboards"
    BOT_COMMANDS: ClassVar[list[dict[str, str]]] = [
        {"name": "stats", "description": "Show full statistics dashboard"},
        {"name": "group", "description": "Stats for a specific group"},
        {"name": "top", "description": "Most active users"},
        {"name": "reset", "description": "Reset all statistics"},
    ]
    BOT_CONTEXT_LIMIT = 30

    def __init__(self, token: str | None = None) -> None:
        super().__init__(token=token)

        self.stats: dict[str, Any] = {
            "total_messages": 0,
            "total_users": set(),  # type: ignore[assignment]
            "total_bots": set(),  # type: ignore[assignment]
            "messages_by_group": defaultdict(int),
            "messages_by_user": defaultdict(int),
            "messages_by_bot": defaultdict(int),
            "messages_by_type": defaultdict(int),
            "messages_by_hour": defaultdict(int),
            "pattern_matches": 0,
            "pattern_matches_by_name": defaultdict(int),
            "first_message_at": None,
            "last_message_at": None,
            "messages_removed": 0,
        }

        @self.on_pattern_matched("all_msgs")
        def on_all_messages(
            name: str,  # noqa: ARG001
            matched_text: str,  # noqa: ARG001
            msg_id: str,  # noqa: ARG001
            sender: str,
            group_id: str,
            timestamp: str,
        ) -> None:
            self.stats["total_messages"] += 1
            self.stats["messages_by_group"][group_id] += 1

            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    hour_key = dt.strftime("%H:00")
                    self.stats["messages_by_hour"][hour_key] += 1
                    if self.stats["first_message_at"] is None:
                        self.stats["first_message_at"] = timestamp
                    self.stats["last_message_at"] = timestamp
                except (ValueError, TypeError):
                    pass

            if sender.startswith("bot:"):
                bot_name = sender[4:]
                self.stats["total_bots"].add(bot_name)  # type: ignore[attr-defined]
                self.stats["messages_by_bot"][bot_name] += 1
                self.stats["messages_by_type"]["bot"] += 1
            elif sender.startswith("user:"):
                self.stats["total_users"].add(sender)  # type: ignore[attr-defined]
                self.stats["messages_by_user"][sender] += 1
                self.stats["messages_by_type"]["user"] += 1
            else:
                self.stats["messages_by_type"]["other"] += 1

        @self.on_pattern_matched("escalation")
        def on_escalation(
            name: str,  # noqa: ARG001
            matched_text: str,
            msg_id: str,  # noqa: ARG001
            sender: str,
            group_id: str,
            timestamp: str,  # noqa: ARG001
        ) -> None:
            self.stats["pattern_matches"] += 1
            self.stats["pattern_matches_by_name"]["escalation"] += 1
            self.log(f"Escalation detected: '{matched_text}' from {sender} in {group_id}")

    def should_handle(self, command: str, args: list[str]) -> bool:  # noqa: ARG002
        return command in {"", "stats", "group", "top", "reset", "help"}

    def handle(
        self,
        command: str,
        args: list[str],
        raw_args: list[str],  # noqa: ARG002
        message: dict[str, Any],
        thread_context: list[dict[str, Any]],  # noqa: ARG002
    ) -> str | None:
        group_id = message.get("group_id", "general")

        if command in ("", "stats"):
            return self._build_dashboard(group_id)
        if command == "group":
            if not args:
                groups = sorted(self.stats["messages_by_group"].items(), key=lambda x: -x[1])
                lines = ["**Groups by activity:**\n"]
                for gid, count in groups[:20]:
                    lines.append(f"- **{gid}**: {count} messages")
                return "\n".join(lines)
            return self._build_group_stats(args[0])
        if command == "top":
            n = int(args[0]) if args and args[0].isdigit() else 10
            return self._build_top_users(n)
        if command == "reset":
            self._reset_stats()
            return "Statistics have been reset."
        if command == "help":
            return self.format_help_response()
        return None

    def _build_dashboard(self, group_id: str | None = None) -> str:  # noqa: C901
        lines: list[str] = []
        lines.append("## Chat Statistics Dashboard")
        if group_id:
            lines.append(f"*Filtered to group: **{group_id}***")
        lines.append("")

        s = self.stats
        total = s["total_messages"]
        users = len(s["total_users"])
        bots = len(s["total_bots"])
        groups = len(s["messages_by_group"])

        lines.append("### Overview")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Total messages | {total} |")
        lines.append(f"| Unique users | {users} |")
        lines.append(f"| Active bots | {bots} |")
        lines.append(f"| Groups | {groups} |")
        lines.append(f"| Pattern matches | {s['pattern_matches']} |")
        lines.append(f"| Removed messages | {s['messages_removed']} |")
        if s["first_message_at"]:
            first = s["first_message_at"][:19].replace("T", " ")
            last = s["last_message_at"][:19].replace("T", " ")
            lines.append(f"| First message | {first} |")
            lines.append(f"| Last message | {last} |")
        lines.append("")

        lines.append("### Messages by Type")
        for t, count in sorted(s["messages_by_type"].items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total else 0
            bar = "#" * int(pct / 2)
            lines.append(f"- **{t}**: {count} ({pct:.0f}%) {bar}")
        lines.append("")

        lines.append("### Messages by Group")
        by_group = sorted(s["messages_by_group"].items(), key=lambda x: -x[1])
        for gid, count in by_group[:15]:
            pct = (count / total * 100) if total else 0
            bar = "#" * int(pct / 2)
            lines.append(f"- **{gid}**: {count} ({pct:.0f}%) {bar}")
        lines.append("")

        lines.append("### Top Users")
        by_user = sorted(s["messages_by_user"].items(), key=lambda x: -x[1])
        for uid, count in by_user[:10]:
            pct = (count / total * 100) if total else 0
            bar = "#" * int(pct / 2)
            lines.append(f"- {uid}: {count} ({pct:.0f}%) {bar}")
        lines.append("")

        lines.append("### Bot Activity")
        by_bot = sorted(s["messages_by_bot"].items(), key=lambda x: -x[1])
        for bname, count in by_bot:
            pct = (count / total * 100) if total else 0
            bar = "#" * int(pct / 2)
            lines.append(f"- **@{bname}**: {count} messages ({pct:.0f}%) {bar}")
        if not by_bot:
            lines.append("- No bot activity recorded")
        lines.append("")

        if s.get("bot_commands_used"):
            by_cmd = sorted(s["bot_commands_used"].items(), key=lambda x: -x[1])
            lines.append("### Bot Commands Used")
            for cmd, count in by_cmd[:15]:
                lines.append(f"- `{cmd}`: {count}")
            lines.append("")

        if s["pattern_matches"]:
            lines.append("### Pattern Matches")
            by_pname = sorted(s["pattern_matches_by_name"].items(), key=lambda x: -x[1])
            for pname, count in by_pname:
                lines.append(f"- `{pname}`: {count}")
            lines.append("")

        lines.append("### Activity by Hour (UTC)")
        for hour in sorted(s["messages_by_hour"].keys()):
            count = s["messages_by_hour"][hour]
            bar = "#" * min(count, 50)
            lines.append(f"- `{hour}`: {count} {bar}")

        return "\n".join(lines)

    def _build_group_stats(self, group_id: str) -> str:
        count = self.stats["messages_by_group"].get(group_id, 0)
        if count == 0:
            return f"No messages recorded for group `{group_id}`."

        lines = [f"## Stats for **{group_id}**", ""]
        lines.append(f"- Total messages: {count}")

        user_msgs = {u: c for u, c in self.stats["messages_by_user"].items() if c > 0}
        bot_msgs = {b: c for b, c in self.stats["messages_by_bot"].items() if c > 0}

        if user_msgs:
            top_users = sorted(user_msgs.items(), key=lambda x: -x[1])[:5]
            lines.append("")
            lines.append("**Top users:**")
            for uid, c in top_users:
                lines.append(f"- {uid}: {c}")

        if bot_msgs:
            lines.append("")
            lines.append("**Bot messages:**")
            for bname, c in sorted(bot_msgs.items(), key=lambda x: -x[1]):
                lines.append(f"- @{bname}: {c}")

        return "\n".join(lines)

    def _build_top_users(self, n: int) -> str:
        by_user = sorted(self.stats["messages_by_user"].items(), key=lambda x: -x[1])[:n]
        total = self.stats["total_messages"]
        lines = [f"## Top {n} Most Active Users", ""]
        lines.append("| Rank | User | Messages | Share |")
        lines.append("|---|---|---|---|")
        for i, (uid, count) in enumerate(by_user, 1):
            pct = (count / total * 100) if total else 0
            lines.append(f"| {i} | {uid} | {count} | {pct:.1f}% |")
        return "\n".join(lines)

    def _reset_stats(self) -> None:
        self.stats["total_messages"] = 0
        self.stats["total_users"] = set()  # type: ignore[assignment]
        self.stats["total_bots"] = set()  # type: ignore[assignment]
        self.stats["messages_by_group"] = defaultdict(int)
        self.stats["messages_by_user"] = defaultdict(int)
        self.stats["messages_by_bot"] = defaultdict(int)
        self.stats["messages_by_type"] = defaultdict(int)
        self.stats["messages_by_hour"] = defaultdict(int)
        self.stats["pattern_matches"] = 0
        self.stats["pattern_matches_by_name"] = defaultdict(int)
        self.stats["first_message_at"] = None
        self.stats["last_message_at"] = None
        self.stats["messages_removed"] = 0


if __name__ == "__main__":
    bot = StatsBot()
    # BUSINESS RULE (MEADOWS-labeling-intent §2.3): empty predicate
    # matches everything — the label-subscription equivalent of ".*".
    # deliver="message_only" ensures stats_bot receives the full MESSAGE
    # event, not just LABEL_ASSIGNED.
    bot.register_label_subscription("all_msgs", {}, scope="global", deliver="message_only")
    bot.register_pattern("escalation", "urgent|critical|emergency", scope="global")
    bot.connect()
