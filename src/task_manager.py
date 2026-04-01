from __future__ import annotations
"""
task_manager.py
───────────────
Orchestration: embed building, daily digest, weekly summary, reminders.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, Tuple, List

import discord
import pytz

from config import TIMEZONE
from database import Database
from calendar_fetcher import fetch_tasks, Task

log = logging.getLogger("TaskManager")

_SOURCE_EMOJI = {"google": "📅", "notion": "📝"}


def _progress_bar(done: int, total: int, width: int = 10) -> str:
    if total == 0:
        return f"[{'░' * width}] —"
    pct = int(done / total * 100)
    filled = round(done / total * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct}%"


class TaskManager:
    def __init__(self, db: Database):
        self.db = db

    # ── Validation ────────────────────────────────────────────────────────────

    async def validate_source(self, source, calendar_id, notion_token) -> Tuple[bool, str]:
        ok, err, _ = await fetch_tasks(source, calendar_id, notion_token, target_date=date.today())
        return ok, err

    # ── Task Embed ────────────────────────────────────────────────────────────

    async def build_task_embed(
        self,
        member: discord.User | discord.Member,
        user_row: dict,
        target_date: date,
    ) -> discord.Embed:
        source = user_row["source"]
        emoji = _SOURCE_EMOJI.get(source, "📆")
        title = f"{emoji}  {member.display_name}'s Tasks — {target_date.strftime('%A, %B %-d')}"

        ok, err, cal_tasks = await fetch_tasks(
            source, user_row["calendar_id"], user_row.get("notion_token"), target_date
        )

        color = 0x5865F2 if ok else 0xED4245
        embed = discord.Embed(title=title, color=color)
        embed.set_thumbnail(url=member.display_avatar.url)

        if not ok:
            embed.description = f"⚠️ Could not fetch calendar tasks: `{err}`"

        # Manual tasks for this date
        manual_tasks = self.db.get_manual_tasks(member.id, target_date=target_date)

        # Completed names (lowercased) for cross-referencing
        completed_today = self.db.get_completed_today(member.id)
        completed_lower = [c.lower() for c in completed_today]

        def _is_done(name: str) -> bool:
            nl = name.lower()
            return any(nl in c or c in nl for c in completed_lower)

        today = date.today()

        def _task_line(name: str, due: Optional[date], desc: str, url: Optional[str], status_emoji: str) -> str:
            line = f"{status_emoji} **{name}**"
            if due:
                line += f"  `{due.strftime('%b %-d')}`"
            if desc:
                snippet = desc[:80] + ("…" if len(desc) > 80 else "")
                line += f"\n   ↳ {snippet}"
            if url:
                line += f"\n   🔗 [Open]({url})"
            return line

        # Categorise calendar tasks
        cal_pending, cal_done, cal_overdue = [], [], []
        if ok:
            for t in cal_tasks:
                done = _is_done(t["name"])
                overdue = t["due"] and t["due"] < today and not done
                if done:
                    cal_done.append(t)
                elif overdue:
                    cal_overdue.append(t)
                else:
                    cal_pending.append(t)

        # Categorise manual tasks
        man_pending, man_done = [], []
        for m in manual_tasks:
            if m["done"] or _is_done(m["name"]):
                man_done.append(m)
            else:
                man_pending.append(m)

        # Totals for progress bar
        total_tasks = len(cal_tasks) + len(manual_tasks) if ok else len(manual_tasks)
        total_done = len(cal_done) + len(man_done)

        # Build fields
        if cal_overdue:
            embed.add_field(
                name="🔴 Overdue",
                value="\n\n".join(_task_line(t["name"], t["due"], t["description"], t["url"], "🔴") for t in cal_overdue),
                inline=False,
            )

        pending_lines = []
        for t in cal_pending:
            pending_lines.append(_task_line(t["name"], t["due"], t["description"], t["url"], "🔲"))
        for m in man_pending:
            pending_lines.append(_task_line(m["name"], m.get("due_date"), m.get("description", ""), None, "🔲"))

        if pending_lines:
            embed.add_field(
                name=f"🔲 Pending ({len(pending_lines)})",
                value="\n\n".join(pending_lines),
                inline=False,
            )

        done_lines = []
        for t in cal_done:
            done_lines.append(_task_line(t["name"], t["due"], t["description"], t["url"], "✅"))
        for m in man_done:
            done_lines.append(_task_line(m["name"], m.get("due_date"), m.get("description", ""), None, "✅"))

        if done_lines:
            embed.add_field(
                name=f"✅ Completed ({len(done_lines)})",
                value="\n\n".join(done_lines),
                inline=False,
            )

        if not pending_lines and not done_lines and not cal_overdue:
            embed.description = (embed.description or "") + "\n\n🎉 No tasks scheduled for this day!"

        bar = _progress_bar(total_done, total_tasks)
        embed.set_footer(text=f"Progress: {bar}  •  {source.title()} + Manual")
        return embed

    # ── Weekly Summary ────────────────────────────────────────────────────────

    async def build_weekly_embed(
        self,
        member: discord.User | discord.Member,
        user_row: dict,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"📊  Weekly Summary — {member.display_name}",
            color=0xEB459E,
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        weekly = self.db.get_weekly_completions(member.id)
        streak = self.db.get_completion_streak(member.id)
        total_all_time = self.db.get_total_completed(member.id)

        # Build a mini bar chart per day
        today = date.today()
        day_map = {}
        for row in weekly:
            day_map[row["day"]] = row["count"]

        chart_lines = []
        total_week = 0
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            key = d.isoformat()
            count = day_map.get(key, 0)
            total_week += count
            bar = "█" * min(count, 10) + ("+" if count > 10 else "")
            label = "Today" if i == 0 else d.strftime("%a %-d")
            chart_lines.append(f"`{label:<8}` {bar or '·'}  ({count})")

        embed.add_field(
            name="📅 Tasks completed this week",
            value="\n".join(chart_lines),
            inline=False,
        )

        # Stats row
        embed.add_field(name="📦 This week", value=str(total_week), inline=True)
        embed.add_field(name="🔥 Streak", value=f"{streak} day{'s' if streak != 1 else ''}", inline=True)
        embed.add_field(name="🏆 All time", value=str(total_all_time), inline=True)

        # Upcoming tasks (next 7 days from calendar)
        source = user_row["source"]
        try:
            upcoming: List[Task] = []
            for days_ahead in range(1, 8):
                future_date = today + timedelta(days=days_ahead)
                ok, _, tasks = await fetch_tasks(
                    source, user_row["calendar_id"], user_row.get("notion_token"), future_date
                )
                if ok:
                    upcoming.extend(tasks)
            if upcoming:
                upcoming_lines = []
                for t in upcoming[:8]:
                    due_str = t["due"].strftime("%a %-d") if t["due"] else "—"
                    upcoming_lines.append(f"• **{t['name']}**  `{due_str}`")
                embed.add_field(
                    name="🗓️ Coming up (next 7 days)",
                    value="\n".join(upcoming_lines),
                    inline=False,
                )
        except Exception as exc:
            log.warning(f"Could not fetch upcoming tasks for weekly summary: {exc}")

        # Manual tasks pending
        pending_manual = self.db.get_manual_tasks(member.id, include_done=False)
        if pending_manual:
            lines = []
            for m in pending_manual[:5]:
                due = m["due_date"].strftime("%b %-d") if m.get("due_date") else "no date"
                lines.append(f"• **{m['name']}**  `{due}`")
            if len(pending_manual) > 5:
                lines.append(f"_…and {len(pending_manual) - 5} more_")
            embed.add_field(
                name="📝 Pending Manual Tasks",
                value="\n".join(lines),
                inline=False,
            )

        embed.set_footer(text=f"Week ending {today.strftime('%B %-d, %Y')}")
        return embed

    # ── Daily Digest ──────────────────────────────────────────────────────────

    async def post_daily_digest(self, bot: discord.Client, sent_today: Optional[set] = None):
        """Post the daily task digest for every registered user.

        ``sent_today`` is an optional in-memory set of user_ids that have
        already received today's digest (populated by the caller).  Users in
        the set are skipped to prevent duplicate sends on retry.  Newly
        successful deliveries are added to the set by this method.

        Raises ``RuntimeError`` if one or more deliveries failed so the caller
        can avoid marking the digest as complete and retry next minute.
        """
        users = self.db.get_all_users()
        tz = pytz.timezone(TIMEZONE)
        today = datetime.now(tz).date()
        log.info(f"Daily digest: found {len(users)} registered user(s).")

        failed_uids: List[int] = []

        for user_row in users:
            uid = user_row["user_id"]

            # Skip users whose digest was already delivered (retry-safe).
            if sent_today is not None and uid in sent_today:
                log.info(f"Digest: user {uid} already received today's digest — skipping.")
                continue

            try:
                # get_channel() only hits the local cache; fall back to an API
                # call so the digest isn't silently dropped for uncached channels.
                channel = bot.get_channel(user_row["channel_id"])
                if not channel:
                    log.warning(
                        f"Digest: channel {user_row['channel_id']} not in cache for user "
                        f"{uid} — attempting fetch_channel()."
                    )
                    try:
                        channel = await bot.fetch_channel(user_row["channel_id"])
                    except Exception as exc:
                        log.error(
                            f"Digest: could not fetch channel {user_row['channel_id']} "
                            f"for user {uid}: {exc}"
                        )
                        failed_uids.append(uid)
                        continue

                member = channel.guild.get_member(uid)
                if not member:
                    log.warning(
                        f"Digest: member {uid} not in cache for guild "
                        f"{channel.guild.id} — attempting fetch_member()."
                    )
                    try:
                        member = await channel.guild.fetch_member(uid)
                    except Exception as exc:
                        log.error(
                            f"Digest: could not fetch member {uid} in guild "
                            f"{channel.guild.id}: {exc}"
                        )
                        failed_uids.append(uid)
                        continue

                embed = await self.build_task_embed(member, user_row, today)
                await channel.send(
                    content=f"🌅 Good morning {member.mention}! Here are your tasks for today:",
                    embed=embed,
                )
                if sent_today is not None:
                    sent_today.add(uid)
                log.info(f"Posted digest for user {uid} in channel {channel.id}.")
            except Exception as exc:
                log.error(f"Digest error for user {uid}: {exc}", exc_info=True)
                failed_uids.append(uid)

        if failed_uids:
            raise RuntimeError(
                f"Daily digest delivery failed for {len(failed_uids)} user(s) "
                f"(user_ids: {failed_uids}). Will retry next minute."
            )

    # ── End-of-Day Daily Reminder ─────────────────────────────────────────────

    async def post_eod_reminder(self, bot: discord.Client, hour: int, minute: int):
        """Fire the end-of-day check-in for every user whose reminder is due now."""
        users = self.db.get_users_due_daily_reminder(hour, minute)
        today = date.today()

        for user_row in users:
            try:
                channel = bot.get_channel(user_row["channel_id"])
                if not channel:
                    continue
                member = channel.guild.get_member(user_row["user_id"])
                if not member:
                    try:
                        member = await channel.guild.fetch_member(user_row["user_id"])
                    except Exception:
                        continue

                # ── Fetch today's calendar tasks ──────────────────────────────
                ok, _, cal_tasks = await fetch_tasks(
                    user_row["source"],
                    user_row["calendar_id"],
                    user_row.get("notion_token"),
                    today,
                )

                completed_today = self.db.get_completed_today(user_row["user_id"])
                completed_lower = [c.lower() for c in completed_today]

                def _is_done(name: str) -> bool:
                    nl = name.lower()
                    return any(nl in c or c in nl for c in completed_lower)

                # ── Build pending list ────────────────────────────────────────
                pending_lines: list = []

                if ok:
                    for t in cal_tasks:
                        if not _is_done(t["name"]):
                            line = f"🔲 **{t['name']}**"
                            if t.get("description"):
                                snippet = t["description"][:60]
                                line += f"\n   ↳ {snippet}{'…' if len(t['description']) > 60 else ''}"
                            pending_lines.append(line)

                for m in self.db.get_manual_tasks(user_row["user_id"], include_done=False):
                    if not _is_done(m["name"]):
                        due = (
                            f"  `{m['due_date'].strftime('%b %-d')}`"
                            if m.get("due_date") else ""
                        )
                        line = f"🔲 **{m['name']}**{due}"
                        if m.get("description"):
                            snippet = m["description"][:60]
                            line += f"\n   ↳ {snippet}{'…' if len(m['description']) > 60 else ''}"
                        pending_lines.append(line)

                # ── Build embed ───────────────────────────────────────────────
                if not pending_lines:
                    embed = discord.Embed(
                        title="🌙 End-of-Day Check-in",
                        description=(
                            f"🎉 Great work today, {member.display_name}! "
                            "You've completed **all** your tasks for today."
                        ),
                        color=0x57F287,
                    )
                else:
                    embed = discord.Embed(
                        title="🌙 End-of-Day Check-in",
                        description=(
                            f"Hey {member.display_name}, have you completed all your tasks for today?\n"
                            "Here are the tasks still not marked as complete:"
                        ),
                        color=0xFEE75C,
                    )
                    # Discord embed field value is capped at 1024 chars — show up to 15 tasks
                    shown = pending_lines[:15]
                    overflow = len(pending_lines) - len(shown)
                    field_value = "\n\n".join(shown)
                    if overflow:
                        field_value += f"\n\n_…and {overflow} more — use `/tasks` to see all._"
                    embed.add_field(
                        name=f"📋 Pending ({len(pending_lines)})",
                        value=field_value,
                        inline=False,
                    )
                    embed.add_field(
                        name="Quick actions",
                        value="`/complete <task>` — mark a task done\n`/tasks` — view full task list",
                        inline=False,
                    )

                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text="Use /dailyreminder to adjust or disable this check-in.")
                await channel.send(content=member.mention, embed=embed)
                log.info(f"Fired EOD daily reminder for user {user_row['user_id']}")

            except Exception as exc:
                log.error(
                    f"EOD reminder error for user {user_row['user_id']}: {exc}",
                    exc_info=True,
                )

    # ── Reminder Firing ───────────────────────────────────────────────────────

    async def fire_due_reminders(self, bot: discord.Client):
        due = self.db.get_due_reminders()
        for reminder in due:
            try:
                user_row = self.db.get_user(reminder["user_id"])
                if not user_row:
                    self.db.mark_reminder_fired(reminder["id"])
                    continue
                channel = bot.get_channel(user_row["channel_id"])
                if not channel:
                    self.db.mark_reminder_fired(reminder["id"])
                    continue
                member = channel.guild.get_member(reminder["user_id"])
                if not member:
                    try:
                        member = await channel.guild.fetch_member(reminder["user_id"])
                    except Exception:
                        self.db.mark_reminder_fired(reminder["id"])
                        continue

                # Build reminder embed with snooze hint
                embed = discord.Embed(
                    title="⏰ Task Reminder",
                    description=f"Don't forget: **{reminder['task_name']}**",
                    color=0xFEE75C,
                )
                embed.set_footer(
                    text="Use /complete to mark it done • /snooze to delay by 30 min"
                )
                snoozed = reminder.get("snoozed", 0)
                if snoozed:
                    embed.add_field(name="💤 Snoozed", value=f"{snoozed}×", inline=True)

                await channel.send(content=f"{member.mention}", embed=embed)
                self.db.mark_reminder_fired(reminder["id"])
                log.info(f"Fired reminder {reminder['id']} for user {reminder['user_id']}")
            except Exception as exc:
                log.error(f"Reminder error {reminder['id']}: {exc}", exc_info=True)
