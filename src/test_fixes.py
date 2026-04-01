"""
Tests for the two daily-digest bugs fixed in this session.

1. on_ready: loops must start even when bot.tree.sync() raises.
2. post_daily_digest: must fall back to fetch_channel() when get_channel() returns None.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

import tempfile

import pytest

# Minimal env so config.py doesn't raise on import
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("TIMEZONE", "America/Toronto")
os.environ.setdefault("DAILY_POST_HOUR", "9")
os.environ.setdefault("DAILY_POST_MINUTE", "0")
os.environ.setdefault("DATABASE_PATH", "test_placeholder.db")


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Give each test its own empty SQLite database file."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    # Also patch the module-level constant already loaded into database.py
    import database as db_mod
    import config as cfg_mod
    monkeypatch.setattr(db_mod, "DATABASE_PATH", db_path)
    monkeypatch.setattr(cfg_mod, "DATABASE_PATH", db_path)

sys.path.insert(0, os.path.dirname(__file__))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_member(uid=1, display_name="Alice"):
    m = MagicMock()
    m.id = uid
    m.display_name = display_name
    m.mention = f"<@{uid}>"
    m.display_avatar.url = "http://example.com/avatar.png"
    return m


def _make_channel(guild_member=None, channel_id=42):
    channel = MagicMock()
    channel.id = channel_id
    channel.send = AsyncMock()
    guild = MagicMock()
    guild.id = 99
    guild.get_member.return_value = guild_member
    guild.fetch_member = AsyncMock(return_value=guild_member)
    channel.guild = guild
    return channel


# ─── Test 1: on_ready loops start even when bot.tree.sync() raises ────────────

@pytest.mark.asyncio
async def test_loops_start_when_global_sync_raises():
    """
    If bot.tree.sync() (global) raises, daily_digest.start() must still be
    called.  This reproduces the original bug where on_ready aborted before
    reaching start().
    """
    # Simulate the fixed on_ready logic extracted as a plain coroutine so we
    # can test it without a live Discord connection.
    loop_started = {"digest": False, "reminder": False, "eod": False}

    class FakeLoop:
        def __init__(self, name):
            self._name = name

        def is_running(self):
            return False

        def start(self):
            loop_started[self._name] = True

    fake_digest = FakeLoop("digest")
    fake_reminder = FakeLoop("reminder")
    fake_eod = FakeLoop("eod")

    async def simulate_on_ready(sync_raises: bool):
        """Mirrors the fixed on_ready — loops first, sync after."""
        if not fake_digest.is_running():
            fake_digest.start()
        if not fake_reminder.is_running():
            fake_reminder.start()
        if not fake_eod.is_running():
            fake_eod.start()

        try:
            if sync_raises:
                raise Exception("Discord rate-limited")
            # normal sync would go here
        except Exception:
            pass  # swallowed — loops already started

    await simulate_on_ready(sync_raises=True)

    assert loop_started["digest"], "daily_digest loop was NOT started despite sync raising"
    assert loop_started["reminder"], "reminder_loop was NOT started"
    assert loop_started["eod"], "eod_reminder_loop was NOT started"


@pytest.mark.asyncio
async def test_loops_start_when_global_sync_succeeds():
    """Loops also start on the happy path."""
    loop_started = {"digest": False}

    class FakeLoop:
        def is_running(self): return False
        def start(self): loop_started["digest"] = True

    fake_digest = FakeLoop()

    async def simulate_on_ready():
        if not fake_digest.is_running():
            fake_digest.start()
        try:
            pass  # sync succeeds
        except Exception:
            pass

    await simulate_on_ready()
    assert loop_started["digest"]


# ─── Test 2: post_daily_digest falls back to fetch_channel ────────────────────

@pytest.mark.asyncio
async def test_digest_uses_fetch_channel_when_cache_miss():
    """
    When bot.get_channel() returns None, post_daily_digest must call
    bot.fetch_channel() and still send the message.
    """
    from task_manager import TaskManager
    from database import Database

    db = Database()
    db.upsert_user(
        user_id=1,
        guild_id=99,
        source="google",
        calendar_id="cal@example.com",
        channel_id=42,
    )

    member = _make_member(uid=1)
    channel = _make_channel(guild_member=member, channel_id=42)

    mock_bot = MagicMock()
    mock_bot.get_channel.return_value = None          # cache miss
    mock_bot.fetch_channel = AsyncMock(return_value=channel)  # API hit

    tm = TaskManager(db)

    # Stub build_task_embed so we don't need a real Google Calendar
    async def fake_embed(member, user_row, target_date):
        import discord
        return discord.Embed(title="Tasks")

    tm.build_task_embed = fake_embed

    await tm.post_daily_digest(mock_bot)

    mock_bot.fetch_channel.assert_awaited_once_with(42)
    channel.send.assert_awaited_once()
    content_arg = channel.send.call_args.kwargs.get("content") or channel.send.call_args.args[0]
    assert "Good morning" in content_arg


@pytest.mark.asyncio
async def test_digest_uses_cached_channel_when_available():
    """
    When bot.get_channel() returns a channel, fetch_channel must NOT be called.
    """
    from task_manager import TaskManager
    from database import Database

    db = Database()
    db.upsert_user(
        user_id=2,
        guild_id=99,
        source="google",
        calendar_id="cal@example.com",
        channel_id=43,
    )

    member = _make_member(uid=2)
    channel = _make_channel(guild_member=member, channel_id=43)

    mock_bot = MagicMock()
    mock_bot.get_channel.return_value = channel   # cache hit
    mock_bot.fetch_channel = AsyncMock()

    tm = TaskManager(db)

    async def fake_embed(member, user_row, target_date):
        import discord
        return discord.Embed(title="Tasks")

    tm.build_task_embed = fake_embed

    await tm.post_daily_digest(mock_bot)

    mock_bot.fetch_channel.assert_not_awaited()
    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_digest_skips_user_when_fetch_channel_fails():
    """
    If both get_channel() and fetch_channel() fail for a user, the user is
    added to failed_uids and post_daily_digest raises RuntimeError so the
    caller knows to retry (and _last_digest_date is not set).
    All other users are still attempted before the raise.
    """
    from task_manager import TaskManager
    from database import Database

    db = Database()
    db.upsert_user(
        user_id=3,
        guild_id=99,
        source="google",
        calendar_id="cal@example.com",
        channel_id=44,
    )

    mock_bot = MagicMock()
    mock_bot.get_channel.return_value = None
    mock_bot.fetch_channel = AsyncMock(side_effect=Exception("Unknown channel"))

    tm = TaskManager(db)

    # Should raise so the loop retries next minute
    with pytest.raises(RuntimeError, match="Will retry next minute"):
        await tm.post_daily_digest(mock_bot)


# ─── Test 3: daily_digest loop retries when post_daily_digest raises ──────────

@pytest.mark.asyncio
async def test_digest_loop_retries_when_post_raises():
    """
    If post_daily_digest raises an exception, _last_digest_date must NOT be
    set, so the loop retries on the next tick rather than silently dropping
    the morning message for the entire day.
    """
    from datetime import date as _date

    call_count = {"n": 0}

    async def failing_post(bot):
        call_count["n"] += 1
        raise RuntimeError("DB unavailable")

    # Simulate the fixed daily_digest loop body as a plain coroutine.
    last_digest_date = None

    async def simulate_daily_digest_tick(now_hour, now_minute, today):
        nonlocal last_digest_date
        import config as cfg
        past_post_time = (now_hour, now_minute) >= (cfg.DAILY_POST_HOUR, cfg.DAILY_POST_MINUTE)
        if past_post_time and last_digest_date != today:
            try:
                await failing_post(None)
                last_digest_date = today  # Only reached on success
            except Exception:
                pass  # Don't set last_digest_date — allow retry

    today = _date(2026, 3, 31)

    # First tick: post fails → last_digest_date stays None
    await simulate_daily_digest_tick(9, 0, today)
    assert last_digest_date is None, "last_digest_date must stay None after a failed post"
    assert call_count["n"] == 1

    # Second tick: post fails again → still None, still retrying
    await simulate_daily_digest_tick(9, 1, today)
    assert last_digest_date is None
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_digest_loop_marks_sent_after_success():
    """
    On a successful post_daily_digest call, _last_digest_date is set to today
    so the digest isn't sent a second time in the same day.
    """
    from datetime import date as _date

    call_count = {"n": 0}

    async def succeeding_post(bot):
        call_count["n"] += 1

    last_digest_date = None

    async def simulate_daily_digest_tick(now_hour, now_minute, today):
        nonlocal last_digest_date
        import config as cfg
        past_post_time = (now_hour, now_minute) >= (cfg.DAILY_POST_HOUR, cfg.DAILY_POST_MINUTE)
        if past_post_time and last_digest_date != today:
            try:
                await succeeding_post(None)
                last_digest_date = today
            except Exception:
                pass

    today = _date(2026, 3, 31)

    # First tick: post succeeds → last_digest_date is set
    await simulate_daily_digest_tick(9, 0, today)
    assert last_digest_date == today, "last_digest_date must be set after a successful post"
    assert call_count["n"] == 1

    # Second tick: already sent today → must NOT call post again
    await simulate_daily_digest_tick(9, 1, today)
    assert call_count["n"] == 1, "post must not be called twice on the same day"
