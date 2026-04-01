from __future__ import annotations
from __future__ import annotations
"""
bot.py — Discord Task Bot entry point
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional, Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks
import pytz

from config import BOT_TOKEN, DAILY_POST_HOUR, DAILY_POST_MINUTE, TIMEZONE
from database import Database
from task_manager import TaskManager
from calendar_fetcher import fetch_tasks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("TaskBot")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
db = Database()
task_manager = TaskManager(db)


# ─── Events ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # Start background loops first — command syncing must never block or crash
    # before these start, otherwise the daily digest is silently lost.
    if not daily_digest.is_running():
        daily_digest.start()
    if not reminder_loop.is_running():
        reminder_loop.start()
    if not eod_reminder_loop.is_running():
        eod_reminder_loop.start()
    log.info(f"Daily digest scheduled for {DAILY_POST_HOUR:02d}:{DAILY_POST_MINUTE:02d} {TIMEZONE}")

    # Sync slash commands — wrapped so rate-limits or API errors don't crash
    # on_ready and leave the loops un-started.
    try:
        await bot.tree.sync()
        log.info("Slash commands synced globally.")
    except Exception as exc:
        log.warning(f"Global slash command sync failed: {exc}")

    # Also sync to every guild for instant availability (skips ~1h propagation).
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            log.info(f"Slash commands synced to guild: {guild.name} ({guild.id})")
        except Exception as exc:
            log.warning(f"Could not sync commands to guild {guild.id}: {exc}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Sync slash commands instantly when the bot is added to a new server."""
    import asyncio
    for attempt in range(1, 4):
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            log.info(f"Slash commands synced to new guild: {guild.name} ({guild.id})")
            return
        except discord.HTTPException as exc:
            if exc.status == 429:  # rate-limited — back off and retry
                retry_after = exc.retry_after if hasattr(exc, "retry_after") else attempt * 5
                log.warning(
                    f"Rate-limited syncing to guild {guild.id} (attempt {attempt}/3). "
                    f"Retrying in {retry_after:.1f}s."
                )
                await asyncio.sleep(retry_after)
            else:
                log.warning(f"Could not sync commands to guild {guild.id} (attempt {attempt}/3): {exc}")
                break
        except Exception as exc:
            log.warning(f"Could not sync commands to guild {guild.id} (attempt {attempt}/3): {exc}")
            break
    log.error(
        f"Failed to sync commands to guild {guild.name} ({guild.id}) after retries. "
        "Global commands will propagate within ~1 hour."
    )


# ─── Global App Command Error Handler ────────────────────────────────────────

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Catch-all handler so every interaction gets a response, preventing
    'The application did not respond' from appearing in Discord."""
    log.error(
        f"Unhandled app command error in /{interaction.command.name if interaction.command else '?'} "
        f"by {interaction.user} (guild {interaction.guild_id}): {error}",
        exc_info=error,
    )
    msg = "❌ An unexpected error occurred. Please try again in a moment."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass  # Nothing more we can do if Discord itself is unreachable


# ─── Background Tasks ─────────────────────────────────────────────────────────

# Track the last date the daily digest was successfully posted so that a late
# bot start or a skipped loop tick (reconnect, asyncio delay, etc.) doesn't
# silently drop the morning message.  The digest fires as soon as the clock
# reaches DAILY_POST_HOUR:DAILY_POST_MINUTE on any day it hasn't yet run.
_last_digest_date: Optional[date] = None
# Per-user send tracking: users whose digest was successfully delivered today.
# Cleared once per calendar day so retries skip already-delivered users and
# avoid duplicate sends.
_digest_sent_today: set[int] = set()
_digest_sent_date: Optional[date] = None


@tasks.loop(minutes=1)
async def daily_digest():
    global _last_digest_date, _digest_sent_today, _digest_sent_date
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    today = now.date()

    # Reset per-user tracking once per calendar day (not on every retry).
    if _digest_sent_date != today:
        _digest_sent_today = set()
        _digest_sent_date = today

    past_post_time = (now.hour, now.minute) >= (DAILY_POST_HOUR, DAILY_POST_MINUTE)
    if past_post_time and _last_digest_date != today:
        log.info("Running daily digest...")
        try:
            await task_manager.post_daily_digest(bot, _digest_sent_today)
            _last_digest_date = today  # Only mark sent after a successful run
        except Exception as exc:
            # Don't set _last_digest_date — the loop will retry next minute.
            # Users already in _digest_sent_today won't receive a duplicate.
            log.error(f"Daily digest failed, will retry next minute: {exc}", exc_info=True)


@tasks.loop(minutes=1)
async def reminder_loop():
    await task_manager.fire_due_reminders(bot)


@tasks.loop(minutes=1)
async def eod_reminder_loop():
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    await task_manager.post_eod_reminder(bot, now.hour, now.minute)


@daily_digest.before_loop
@reminder_loop.before_loop
@eod_reminder_loop.before_loop
async def before_loops():
    await bot.wait_until_ready()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if date_str is None:
        return datetime.now(pytz.timezone(TIMEZONE)).date()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_datetime(dt_str: str) -> Optional[datetime]:
    try:
        naive = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        return pytz.timezone(TIMEZONE).localize(naive)
    except ValueError:
        return None


def _require_setup(user_id: int) -> Optional[dict]:
    return db.get_user(user_id)


# ─── /setup ───────────────────────────────────────────────────────────────────

@bot.tree.command(name="setup", description="Link your Google Calendar or Notion database to the bot.")
@app_commands.describe(
    source="'google' or 'notion'",
    calendar_id="Google Calendar ID or Notion Database ID",
    channel="Channel where your daily digest will be posted",
    notion_token="Notion integration token (required for Notion only)",
)
async def setup(
    interaction: discord.Interaction,
    source: Literal["google", "notion"],
    calendar_id: str,
    channel: discord.TextChannel,
    notion_token: Optional[str] = None,
):
    await interaction.response.defer(ephemeral=True)
    try:
        # source is constrained to "google" | "notion" by the Literal type,
        # which Discord renders as a dropdown — no free-text validation needed.
        if source == "notion" and not notion_token:
            await interaction.followup.send("❌ `notion_token` is required for Notion.", ephemeral=True)
            return

        ok, msg = await task_manager.validate_source(source, calendar_id, notion_token)
        if not ok:
            await interaction.followup.send(f"❌ Could not connect: {msg}", ephemeral=True)
            return

        db.upsert_user(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            source=source,
            calendar_id=calendar_id,
            channel_id=channel.id,
            notion_token=notion_token,
        )
        await interaction.followup.send(
            f"✅ Setup complete! Your **{source.title()}** tasks will be posted to {channel.mention} daily at "
            f"`{DAILY_POST_HOUR:02d}:{DAILY_POST_MINUTE:02d} {TIMEZONE}`.",
            ephemeral=True,
        )
    except Exception as exc:
        log.error(f"Error in /setup for user {interaction.user.id}: {exc}", exc_info=True)
        await interaction.followup.send(
            "❌ An unexpected error occurred during setup. Please try again.",
            ephemeral=True,
        )


# ─── /tasks ───────────────────────────────────────────────────────────────────

@bot.tree.command(name="tasks", description="Show your tasks for today or a specific date.")
@app_commands.describe(date="Date in YYYY-MM-DD format (defaults to today)")
async def show_tasks(interaction: discord.Interaction, date: Optional[str] = None):
    await interaction.response.defer(ephemeral=True)
    user = _require_setup(interaction.user.id)
    if not user:
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return
    target = _parse_date(date)
    if target is None:
        await interaction.followup.send("❌ Invalid date — use `YYYY-MM-DD`.", ephemeral=True)
        return
    embed = await task_manager.build_task_embed(interaction.user, user, target)
    await interaction.followup.send(embed=embed, ephemeral=True)


# ─── /complete ────────────────────────────────────────────────────────────────

@bot.tree.command(name="complete", description="Mark a task as complete.")
@app_commands.describe(task_name="Name or part of the task name")
async def complete_task(interaction: discord.Interaction, task_name: str):
    await interaction.response.defer(ephemeral=True)
    if not _require_setup(interaction.user.id):
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return

    # Try manual task first, then calendar task
    result = db.complete_manual_task(interaction.user.id, task_name)
    source = "manual task"
    if not result:
        result = db.complete_calendar_task(interaction.user.id, task_name)
        source = "calendar task"

    if result:
        await interaction.followup.send(f"✅ Marked **{result}** as complete! _{source}_", ephemeral=True)
    else:
        await interaction.followup.send(
            f"⚠️ No active task matching `{task_name}` found.\nCheck `/tasks` for your task list.",
            ephemeral=True,
        )


# ─── /add ─────────────────────────────────────────────────────────────────────

@bot.tree.command(name="add", description="Add a manual task (not from your calendar).")
@app_commands.describe(
    name="Task name",
    due="Due date in YYYY-MM-DD format (optional)",
    description="Optional description or notes",
)
async def add_task(
    interaction: discord.Interaction,
    name: str,
    due: Optional[str] = None,
    description: str = "",
):
    await interaction.response.defer(ephemeral=True)
    if not _require_setup(interaction.user.id):
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return

    due_date = None
    if due:
        due_date = _parse_date(due)
        if due_date is None:
            await interaction.followup.send("❌ Invalid date — use `YYYY-MM-DD`.", ephemeral=True)
            return

    db.add_manual_task(interaction.user.id, name, description, due_date)
    due_str = f" due **{due_date.strftime('%B %-d')}**" if due_date else ""
    await interaction.followup.send(f"📝 Added task: **{name}**{due_str}", ephemeral=True)


# ─── /mytasks ─────────────────────────────────────────────────────────────────

@bot.tree.command(name="mytasks", description="List your manual tasks and today's calendar tasks.")
@app_commands.describe(show_done="Include completed tasks (default: false)")
async def my_tasks(interaction: discord.Interaction, show_done: bool = False):
    await interaction.response.defer(ephemeral=True)
    user = _require_setup(interaction.user.id)
    if not user:
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return

    today = datetime.now(pytz.timezone(TIMEZONE)).date()
    embed = discord.Embed(
        title=f"📋 Your Tasks — {today.strftime('%A, %B %-d')}",
        color=0x57F287,
    )

    # ── Calendar tasks for today ──────────────────────────────────────────────
    ok, err, cal_tasks = await fetch_tasks(
        user["source"], user["calendar_id"], user.get("notion_token"), today
    )

    completed_today = db.get_completed_today(interaction.user.id)
    completed_lower = [c.lower() for c in completed_today]

    def _is_done(name: str) -> bool:
        nl = name.lower()
        return any(nl in c or c in nl for c in completed_lower)

    if ok and cal_tasks:
        cal_lines = []
        for t in cal_tasks:
            if not show_done and _is_done(t["name"]):
                continue
            status = "✅" if _is_done(t["name"]) else "🔲"
            line = f"{status} **{t['name']}**"
            if t.get("description"):
                line += f"\n   ↳ {t['description'][:80]}"
            if t.get("url"):
                line += f"\n   🔗 [Open]({t['url']})"
            cal_lines.append(line)
        if cal_lines:
            source_label = user["source"].title()
            embed.add_field(
                name=f"📅 {source_label} — Today",
                value="\n\n".join(cal_lines),
                inline=False,
            )
    elif not ok:
        embed.add_field(
            name="📅 Calendar",
            value=f"⚠️ Could not fetch calendar tasks: `{err}`",
            inline=False,
        )

    # ── Manual tasks ─────────────────────────────────────────────────────────
    manual_tasks = db.get_manual_tasks(interaction.user.id, include_done=show_done)
    if manual_tasks:
        man_lines = []
        for t in manual_tasks:
            status = "✅" if t["done"] else "🔲"
            due = t["due_date"].strftime("%b %-d") if t.get("due_date") else "No due date"
            line = f"{status} **{t['name']}**  `{due}`"
            if t.get("description"):
                line += f"\n   ↳ {t['description'][:80]}"
            man_lines.append(line)
        embed.add_field(
            name="📝 Manual Tasks",
            value="\n\n".join(man_lines),
            inline=False,
        )

    if not embed.fields:
        await interaction.followup.send("📭 No tasks found for today.", ephemeral=True)
        return

    await interaction.followup.send(embed=embed, ephemeral=True)


# ─── /delete ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="delete", description="Delete a manual task.")
@app_commands.describe(task_name="Name or part of the task name to delete")
async def delete_task(interaction: discord.Interaction, task_name: str):
    await interaction.response.defer(ephemeral=True)
    if not _require_setup(interaction.user.id):
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return

    result = db.delete_manual_task(interaction.user.id, task_name)
    if result:
        await interaction.followup.send(f"🗑️ Deleted task: **{result}**", ephemeral=True)
    else:
        await interaction.followup.send(f"⚠️ No manual task matching `{task_name}` found.", ephemeral=True)


# ─── /reminder ────────────────────────────────────────────────────────────────

@bot.tree.command(name="reminder", description="Set a reminder for a task.")
@app_commands.describe(
    task_name="Task name (or partial name)",
    remind_at="When to remind you — format: YYYY-MM-DD HH:MM (24h)",
)
async def set_reminder(interaction: discord.Interaction, task_name: str, remind_at: str):
    await interaction.response.defer(ephemeral=True)
    if not _require_setup(interaction.user.id):
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return

    dt = _parse_datetime(remind_at)
    if dt is None:
        await interaction.followup.send("❌ Invalid format — use `YYYY-MM-DD HH:MM`.", ephemeral=True)
        return

    if dt < datetime.now(pytz.timezone(TIMEZONE)):
        await interaction.followup.send("❌ Reminder time must be in the future.", ephemeral=True)
        return

    result = db.set_reminder(interaction.user.id, task_name, dt)
    await interaction.followup.send(
        f"⏰ Reminder set for **{result}** at `{dt.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE})`.",
        ephemeral=True,
    )


# ─── /reminders ───────────────────────────────────────────────────────────────

@bot.tree.command(name="reminders", description="List your pending reminders.")
async def list_reminders(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    reminders = db.get_reminders(interaction.user.id)
    if not reminders:
        await interaction.followup.send("📭 No pending reminders.", ephemeral=True)
        return

    embed = discord.Embed(title="⏰ Your Reminders", color=0x5865F2)
    for r in reminders:
        snoozed_str = f" _(snoozed {r['snoozed']}×)_" if r.get("snoozed") else ""
        embed.add_field(
            name=r["task_name"],
            value=f"🕐 `{r['remind_at'].strftime('%Y-%m-%d %H:%M')}` ({TIMEZONE}){snoozed_str}",
            inline=False,
        )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ─── /snooze ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="snooze", description="Snooze a reminder by a set number of minutes.")
@app_commands.describe(
    task_name="Task name (or partial name) of the reminder to snooze",
    minutes="How many minutes to snooze (default: 30)",
)
async def snooze_reminder(interaction: discord.Interaction, task_name: str, minutes: int = 30):
    await interaction.response.defer(ephemeral=True)
    if not _require_setup(interaction.user.id):
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return

    if minutes < 1 or minutes > 1440:
        await interaction.followup.send("❌ Minutes must be between 1 and 1440.", ephemeral=True)
        return

    reminders = db.get_reminders(interaction.user.id)
    match = next(
        (r for r in reminders if task_name.lower() in r["task_name"].lower()),
        None,
    )
    if not match:
        await interaction.followup.send(f"⚠️ No reminder matching `{task_name}` found.", ephemeral=True)
        return

    new_time = datetime.now(pytz.timezone(TIMEZONE)) + timedelta(minutes=minutes)
    db.snooze_reminder(match["id"], new_time)
    await interaction.followup.send(
        f"💤 Snoozed **{match['task_name']}** for {minutes} minute{'s' if minutes != 1 else ''}.\n"
        f"New time: `{new_time.strftime('%H:%M')}`",
        ephemeral=True,
    )


# ─── /cancelreminder ──────────────────────────────────────────────────────────

@bot.tree.command(name="cancelreminder", description="Cancel a pending reminder.")
@app_commands.describe(task_name="Task name (or partial name) of the reminder to cancel")
async def cancel_reminder(interaction: discord.Interaction, task_name: str):
    await interaction.response.defer(ephemeral=True)
    result = db.cancel_reminder(interaction.user.id, task_name)
    if result:
        await interaction.followup.send(f"🗑️ Cancelled reminder for **{result}**.", ephemeral=True)
    else:
        await interaction.followup.send(f"⚠️ No reminder matching `{task_name}` found.", ephemeral=True)


# ─── /weekly ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="weekly", description="View your weekly task summary and streak.")
async def weekly_summary(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user = _require_setup(interaction.user.id)
    if not user:
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return
    embed = await task_manager.build_weekly_embed(interaction.user, user)
    await interaction.followup.send(embed=embed, ephemeral=True)


# ─── /status ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="status", description="Show your current bot configuration.")
async def status(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user = _require_setup(interaction.user.id)
    if not user:
        await interaction.followup.send("❌ Not set up. Use `/setup` first.", ephemeral=True)
        return

    channel = bot.get_channel(user["channel_id"])
    streak = db.get_completion_streak(interaction.user.id)
    total = db.get_total_completed(interaction.user.id)
    manual_pending = len(db.get_manual_tasks(interaction.user.id, include_done=False))

    dr = db.get_daily_reminder(interaction.user.id)
    if dr and dr["enabled"]:
        dr_friendly = datetime.strptime(
            f"{dr['reminder_hour']:02d}:{dr['reminder_minute']:02d}", "%H:%M"
        ).strftime("%-I:%M %p")
        dr_value = f"`{dr_friendly} {TIMEZONE}`"
    else:
        dr_value = "Off"

    embed = discord.Embed(title="⚙️ Your Configuration", color=0x57F287)
    embed.add_field(name="Source", value=user["source"].title(), inline=True)
    embed.add_field(name="Calendar ID", value=f"`{user['calendar_id']}`", inline=True)
    embed.add_field(name="Digest Channel", value=channel.mention if channel else "Unknown", inline=True)
    embed.add_field(name="Daily Post Time", value=f"`{DAILY_POST_HOUR:02d}:{DAILY_POST_MINUTE:02d} {TIMEZONE}`", inline=True)
    embed.add_field(name="🌙 EOD Reminder", value=dr_value, inline=True)
    embed.add_field(name="🔥 Streak", value=f"{streak} day{'s' if streak != 1 else ''}", inline=True)
    embed.add_field(name="🏆 All-time Completed", value=str(total), inline=True)
    embed.add_field(name="📝 Manual Tasks Pending", value=str(manual_pending), inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)


# ─── /nudge ───────────────────────────────────────────────────────────────────

@bot.tree.command(name="nudge", description="Remind another server member to complete their tasks.")
@app_commands.describe(
    member="The server member you want to nudge",
    message="Optional custom message (default: a friendly reminder)",
)
async def nudge(interaction: discord.Interaction, member: discord.Member, message: Optional[str] = None):
    await interaction.response.defer(ephemeral=False)  # visible to channel

    # Can't nudge yourself
    if member.id == interaction.user.id:
        await interaction.followup.send("🤔 You can't nudge yourself! Use `/reminder` instead.", ephemeral=True)
        return

    # Can't nudge bots
    if member.bot:
        await interaction.followup.send("🤖 You can't nudge a bot.", ephemeral=True)
        return

    # Check if the target user has set up the bot
    target_user = db.get_user(member.id)
    if not target_user:
        await interaction.followup.send(
            f"⚠️ {member.display_name} hasn't set up the task bot yet — they can use `/setup` to get started.",
            ephemeral=True,
        )
        return

    # Build the nudge embed (public in channel)
    custom_msg = message or "Hey, don't forget to check off your tasks today! 💪"
    embed = discord.Embed(
        title="👋 Task Nudge!",
        description=f"{interaction.user.mention} is reminding you to get things done!",
        color=0xFEE75C,
    )
    embed.add_field(name="💬 Message", value=custom_msg, inline=False)
    embed.add_field(
        name="📋 Quick Actions",
        value="`/tasks` — view today's tasks\n`/complete <task>` — mark a task done\n`/weekly` — see your progress",
        inline=False,
    )

    # Fetch today's pending count for the nudged user (without exposing task names)
    try:
        ok, _, cal_tasks = await fetch_tasks(
            target_user["source"],
            target_user["calendar_id"],
            target_user.get("notion_token"),
            date.today(),
        )
        completed = db.get_completed_today(member.id)
        completed_lower = [c.lower() for c in completed]
        pending_count = sum(
            1 for t in cal_tasks
            if not any(t["name"].lower() in c or c in t["name"].lower() for c in completed_lower)
        ) if ok else 0
        manual_pending = len(db.get_manual_tasks(member.id))
        total_pending = pending_count + manual_pending

        if total_pending > 0:
            embed.add_field(
                name="📊 Their Status",
                value=f"**{total_pending}** task{'s' if total_pending != 1 else ''} still pending today",
                inline=False,
            )
        else:
            embed.add_field(name="📊 Their Status", value="✅ All caught up for today!", inline=False)
    except Exception:
        pass  # Don't break the nudge if stats fail

    embed.set_footer(text=f"Nudged by {interaction.user.display_name}")
    await interaction.followup.send(content=f"{member.mention}", embed=embed)


# ─── /dailyreminder ───────────────────────────────────────────────────────────

@bot.tree.command(
    name="dailyreminder",
    description="Set a daily end-of-day check-in showing your incomplete tasks.",
)
@app_commands.describe(
    enabled="Turn the reminder on or off",
    time="Time to send it — 24-hour HH:MM format, e.g. 21:00 for 9 pm",
)
async def daily_reminder_cmd(
    interaction: discord.Interaction,
    enabled: bool = True,
    time: Optional[str] = None,
):
    await interaction.response.defer(ephemeral=True)
    if not _require_setup(interaction.user.id):
        await interaction.followup.send("❌ Run `/setup` first.", ephemeral=True)
        return

    # ── Disable path ──────────────────────────────────────────────────────────
    if not enabled:
        db.disable_daily_reminder(interaction.user.id)
        await interaction.followup.send(
            "🔕 Daily end-of-day reminder **disabled**.\n"
            "Run `/dailyreminder enabled:True time:HH:MM` to turn it back on.",
            ephemeral=True,
        )
        return

    # ── Enable path ───────────────────────────────────────────────────────────
    if not time:
        await interaction.followup.send(
            "❌ Please provide a `time` — e.g. `21:00` for 9 pm.",
            ephemeral=True,
        )
        return

    try:
        parts = time.strip().split(":")
        if len(parts) != 2:
            raise ValueError
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        await interaction.followup.send(
            "❌ Invalid time — use `HH:MM` in 24-hour format, e.g. `21:00` for 9 pm.",
            ephemeral=True,
        )
        return

    db.set_daily_reminder(interaction.user.id, hour, minute)

    friendly = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").strftime("%-I:%M %p")
    await interaction.followup.send(
        f"🌙 Daily end-of-day reminder set for **{friendly} {TIMEZONE}**.\n"
        "Each day at this time you'll receive a check-in listing any tasks "
        "you haven't yet marked as complete.\n\n"
        "To change the time, run this command again with a new time.\n"
        "To disable, run `/dailyreminder enabled:False`.",
        ephemeral=True,
    )


# ─── /unlink ──────────────────────────────────────────────────────────────────

@bot.tree.command(name="unlink", description="Remove your calendar integration and all data.")
async def unlink(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    db.delete_user(interaction.user.id)
    await interaction.followup.send(
        "🗑️ Your data has been removed. You can run `/setup` again at any time.",
        ephemeral=True,
    )


# ─── /help ────────────────────────────────────────────────────────────────────

@bot.tree.command(name="help", description="Show all available commands.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📅 Task Bot — Command Reference",
        description="All responses are private (ephemeral) — only you see them.",
        color=0x5865F2,
    )
    commands_info = [
        ("/setup", "Link your Google Calendar or Notion database"),
        ("/tasks [date]", "Show your tasks for today or a date (YYYY-MM-DD)"),
        ("/complete <task>", "Mark a task done (calendar or manual)"),
        ("/add <name> [due] [description]", "Add a manual task (not from calendar)"),
        ("/mytasks [show_done]", "List your manual tasks + today's calendar tasks"),
        ("/delete <task>", "Delete a manual task"),
        ("/reminder <task> <datetime>", "Set a reminder (YYYY-MM-DD HH:MM)"),
        ("/reminders", "List your pending reminders"),
        ("/snooze <task> [minutes]", "Snooze a reminder (default 30 min)"),
        ("/cancelreminder <task>", "Cancel a pending reminder"),
        ("/nudge @member [message]", "Publicly remind someone else to complete their tasks"),
        ("/dailyreminder [time] [enabled]", "Set or toggle a daily end-of-day incomplete-task check-in"),
        ("/weekly", "Weekly summary, streak, and upcoming tasks"),
        ("/status", "Show your configuration and stats"),
        ("/unlink", "Remove all your data"),
        ("/help", "Show this message"),
    ]
    for name, desc in commands_info:
        embed.add_field(name=f"`{name}`", value=desc, inline=False)

    embed.set_footer(text=f"Daily digest posts at {DAILY_POST_HOUR:02d}:{DAILY_POST_MINUTE:02d} {TIMEZONE}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─── Prefix !help (instant fallback before slash commands propagate) ──────────

@bot.command(name="help")
async def prefix_help(ctx: commands.Context):
    """Show the full command list via the !help prefix command."""
    embed = discord.Embed(
        title="📅 TaskList Bot — Command Reference",
        description=(
            "**Get started:** `/setup` links your Google Calendar or Notion database.\n"
            "All `/` slash commands are listed below. Responses are private — only you see them."
        ),
        color=0x5865F2,
    )
    commands_info = [
        ("/setup", "Link your Google Calendar or Notion database"),
        ("/tasks [date]", "Show your tasks for today or a date (YYYY-MM-DD)"),
        ("/complete <task>", "Mark a task done (calendar or manual)"),
        ("/add <name> [due] [description]", "Add a manual task (not from calendar)"),
        ("/mytasks [show_done]", "List your manual tasks + today's calendar tasks"),
        ("/delete <task>", "Delete a manual task"),
        ("/reminder <task> <datetime>", "Set a reminder (YYYY-MM-DD HH:MM)"),
        ("/reminders", "List your pending reminders"),
        ("/snooze <task> [minutes]", "Snooze a reminder (default 30 min)"),
        ("/cancelreminder <task>", "Cancel a pending reminder"),
        ("/nudge @member [message]", "Publicly remind someone else to complete their tasks"),
        ("/dailyreminder [time] [enabled]", "Set or toggle a daily end-of-day incomplete-task check-in"),
        ("/weekly", "Weekly summary, streak, and upcoming tasks"),
        ("/status", "Show your configuration and stats"),
        ("/unlink", "Remove all your data"),
        ("/help", "Show this message"),
    ]
    for name, desc in commands_info:
        embed.add_field(name=f"`{name}`", value=desc, inline=False)

    embed.set_footer(
        text=f"Daily digest posts at {DAILY_POST_HOUR:02d}:{DAILY_POST_MINUTE:02d} {TIMEZONE} • "
             "Slash commands also available — type / in the message box"
    )
    await ctx.send(embed=embed)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot.run(BOT_TOKEN)
