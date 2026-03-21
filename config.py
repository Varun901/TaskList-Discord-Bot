import os
from dotenv import load_dotenv

load_dotenv()

# ── Discord ────────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ── Daily Digest Schedule ─────────────────────────────────────────────────────
# Time (24h) at which the bot posts everyone's daily task list.
DAILY_POST_HOUR: int = int(os.getenv("DAILY_POST_HOUR", "8"))
DAILY_POST_MINUTE: int = int(os.getenv("DAILY_POST_MINUTE", "0"))
TIMEZONE: str = os.getenv("TIMEZONE", "America/Toronto")

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "taskbot.db")
