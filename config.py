import os
from dotenv import load_dotenv

load_dotenv()

# ── Discord ────────────────────────────────────────────────────────────────────
_raw_token = os.getenv("DISCORD_BOT_TOKEN", "")
if not _raw_token:
    raise RuntimeError(
        "DISCORD_BOT_TOKEN is not set. "
        "Add it to your .env file or set it as an environment variable."
    )
BOT_TOKEN: str = _raw_token

# ── Daily Digest Schedule ─────────────────────────────────────────────────────
# Time (24h) at which the bot posts everyone's daily task list.
DAILY_POST_HOUR: int = int(os.getenv("DAILY_POST_HOUR", "8"))
DAILY_POST_MINUTE: int = int(os.getenv("DAILY_POST_MINUTE", "0"))
TIMEZONE: str = os.getenv("TIMEZONE", "America/Toronto")

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "taskbot.db")
