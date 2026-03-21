# 📅 Discord Task Bot
### Complete Setup & User Guide

> Fetch tasks from Google Calendar or Notion • Daily digests • Reminders • Manual tasks • Nudge teammates

---

## Table of Contents

1. [What Is This Bot?](#1-what-is-this-bot)
2. [Requirements](#2-requirements)
3. [Adding the Bot to Discord](#3-adding-the-bot-to-discord)
4. [Installation & Configuration](#4-installation--configuration)
5. [Hosting the Bot in the Cloud](#5-hosting-the-bot-in-the-cloud)
6. [User Setup — Connecting Your Calendar](#6-user-setup--connecting-your-calendar)
7. [Adding Tasks Manually](#7-adding-tasks-manually-without-a-calendar)
8. [Command Reference](#8-command-reference)
9. [The /nudge Command](#9-the-nudge-command--reminding-others)
10. [Troubleshooting](#10-troubleshooting)
11. [FAQ](#11-frequently-asked-questions)

---

## 1. What Is This Bot?

The Discord Task Bot connects each member of your Discord server to their own Google Calendar or Notion database. Every morning, the bot automatically posts a personalised task digest in the channel of their choice. Members can mark tasks complete, set reminders, add manual tasks, and even nudge each other to stay on track.

**Key highlights:**

- 🔒 **Per-user calendars** — each person links their own source, completely separate from everyone else
- 📅 Supports **Google Calendar** (public iCal) and **Notion** databases
- 🌅 **Daily digest** posted automatically at a configurable time
- 📝 **Manual tasks** — add tasks directly in Discord, no calendar needed
- ⏰ **Reminders** with snooze support
- 👋 **/nudge** — publicly remind a teammate to complete their tasks
- 📊 **Weekly summary** with streak tracking and upcoming 7-day preview

---

## 2. Requirements

Before running the bot you need the following on the machine that will host it:

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 or later | Download from [python.org](https://python.org) |
| pip | Latest | Bundled with Python |
| Discord account | Any | To create the bot application |
| Internet access | Always-on | Bot must stay connected 24/7 |
| Google or Notion account | Any | At least one user needs a calendar |

**Python packages** (installed automatically from `requirements.txt`):

- `discord.py >= 2.3`
- `httpx` — async HTTP client for calendar fetching
- `icalendar` — parses Google Calendar iCal feeds
- `python-dotenv` — loads `.env` config file
- `pytz` — timezone support

> 💡 **Optional: Docker** — You can run the bot inside Docker instead of installing Python directly. A `Dockerfile` and `docker-compose.yml` are included. See [Section 5](#5-keeping-the-bot-running-247).

---

## 3. Adding the Bot to Discord

> These steps are done **once** by the server owner or administrator.

### Step 1 — Create a Discord Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) and log in.
2. Click **"New Application"** in the top-right corner.
3. Give it a name (e.g. `Task Bot`) and click **Create**.
4. Go to the **"Bot"** tab in the left sidebar.
5. Click **"Add Bot"** and confirm.
6. Under **"Privileged Gateway Intents"**, enable both:
   - ✅ **Server Members Intent**
   - ✅ **Message Content Intent**
7. Click **"Save Changes"**.
8. Click **"Reset Token"** to reveal your bot token. **Copy it** — you will need it in Step 3.

> ⚠️ **Keep your token secret.** Never share your bot token publicly. Anyone with it can control your bot. If it leaks, regenerate it immediately from the Developer Portal.

### Step 2 — Invite the Bot to Your Server

The Discord Developer Portal has moved the URL Generator. Here is where to find it now:

1. In the Developer Portal, click on your application.
2. In the left sidebar, click **"Installation"**.
3. Under **"Install Link"**, change the dropdown from `Discord Provided Link` to **`Discord Provided Link`** — or look for a section called **"Guild Install"**.

   > If you don't see "Installation", try this alternative:
   > - In the left sidebar, click **"OAuth2"**
   > - Look for a **"Redirects"** section at the top — ignore that
   > - Scroll down on that same page for **"OAuth2 URL Generator"**, or check the sub-item **"OAuth2" → expand it** in the sidebar for a nested page

4. However the most reliable method that always works is to **build the invite URL manually**. Replace `YOUR_CLIENT_ID` with your application's Client ID (found on the **"General Information"** page of your app):

   ```
   https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=51200&scope=bot+applications.commands
   ```

   **How to find your Client ID:**
   - In the Developer Portal, click your application
   - Click **"General Information"** in the left sidebar
   - Copy the **"Application ID"** — this is your Client ID

5. Paste the URL into your browser, select your server from the dropdown, and click **Authorise**.

The `permissions=51200` in the URL covers exactly the permissions the bot needs:

| Permission | Why it's needed |
|---|---|
| ✅ `Send Messages` | Posts daily digests and reminder alerts |
| ✅ `Embed Links` | Sends formatted embed cards for task lists |
| ✅ `Read Message History` | Allows the bot to function correctly in channels |
| ✅ `View Channels` | Lets the bot see the channels it posts into |

The bot will now appear in your server's member list but will show as offline until you run it.

> 📋 **Redirects field — you can ignore this.** The Developer Portal may show a "Redirects" section with the note *"You must specify at least one URI for authentication to work."* This only applies to OAuth2 **user login flows** (e.g. "Sign in with Discord" on a website). This bot uses the `bot` scope to join your server — it does not perform any user authentication and does not need a redirect URI. Leave the Redirects field empty.

---

## 4. Installation & Configuration

### Step 1 — Download the Code

Copy the project folder to any directory on your machine. The folder contains:

```
discord_task_bot/
├── bot.py                # Main entry point, all slash commands
├── task_manager.py       # Digest and reminder logic
├── calendar_fetcher.py   # Google Calendar and Notion fetchers
├── database.py           # SQLite storage (per-user isolation)
├── config.py             # Reads environment variables
├── requirements.txt      # Python dependencies
├── .env.example          # Configuration template
├── Dockerfile            # Docker support
└── docker-compose.yml    # Docker Compose support
```

### Step 2 — Create Your `.env` File

In the project folder, copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

Open `.env` in any text editor:

| Variable | Default | Description |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *(required)* | Bot token from the Developer Portal |
| `DAILY_POST_HOUR` | `8` | Hour to post daily digests (24-hour, 0–23) |
| `DAILY_POST_MINUTE` | `0` | Minute to post (0–59) |
| `TIMEZONE` | `America/Toronto` | Your server's timezone ([full list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)) |
| `DATABASE_PATH` | `taskbot.db` | Path to the SQLite file (created automatically) |

### Step 3 — Install Python Dependencies

Open a terminal in the project folder and run:

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 4 — Run the Bot

```bash
python bot.py
```

You should see log output like:

```
INFO  TaskBot: Logged in as Task Bot#1234 (ID: 123456789)
INFO  TaskBot: Slash commands synced.
INFO  TaskBot: Daily digest scheduled for 08:00 America/Toronto
```

> Slash commands may take **1–5 minutes** to appear in Discord after the first sync. The bot must remain running at all times for digests and reminders to fire — see [Section 5](#5-keeping-the-bot-running-247).

---

## 5. Hosting the Bot in the Cloud

The bot needs to run on *some* machine 24/7. Running it on your own laptop means it goes offline whenever the laptop does. Hosting it in the cloud keeps it always-on without your computer being involved at all.

### Hosting Options Overview

| Platform | Cost | Difficulty | Notes |
|---|---|---|---|
| **Fly.io** *(recommended)* | Free tier | Moderate | Always-on, Docker-based, generous free allowance |
| Railway | Pay-as-you-go | Easy | ~$5/month, very simple but no free tier |
| Render | Free / $7/month | Easy | Free tier spins down after inactivity — not ideal for bots |
| Oracle Cloud | Free forever | Hard | Powerful free VM but complex setup |
| DigitalOcean VPS | ~$4–6/month | Moderate | Full Linux server, most control |

---

### ⭐ Option A — Fly.io (Recommended — Free)

Fly.io runs your bot inside a Docker container on their infrastructure. The free tier includes enough compute to run a Discord bot indefinitely at no cost. Your `Dockerfile` is already included in the project — Fly.io uses it automatically.

#### Step 1 — Install the Fly CLI

**macOS:**
```bash
brew install flyctl
```

**Windows** (run in PowerShell as Administrator):
```powershell
powershell -ExecutionPolicy Bypass -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

**Linux:**
```bash
curl -L https://fly.io/install.sh | sh
```

#### Step 2 — Sign Up and Log In

```bash
fly auth signup
# or if you already have an account:
fly auth login
```

This opens a browser window to complete sign-up/login. No credit card is required for the free tier.

#### Step 3 — Add the fly.toml Config File

Create a file called `fly.toml` in your project folder with the following contents. Replace `your-bot-name` with any unique name (lowercase letters, numbers, and hyphens only):

```toml
app = "your-bot-name"
primary_region = "yyz"        # Toronto — change if you prefer another region

[build]

[env]
  DAILY_POST_HOUR   = "8"
  DAILY_POST_MINUTE = "0"
  TIMEZONE          = "America/Toronto"
  DATABASE_PATH     = "/data/taskbot.db"

[mounts]
  source      = "taskbot_data"
  destination = "/data"

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

> 📌 **Regions:** `yyz` = Toronto. Other options: `ord` (Chicago), `iad` (Virginia), `lhr` (London), `syd` (Sydney). Pick the one closest to you. Full list at [fly.io/docs/reference/regions](https://fly.io/docs/reference/regions/).

#### Step 4 — Set Your Bot Token as a Secret

Never put your bot token in `fly.toml` — use Fly's secrets system instead:

```bash
fly secrets set DISCORD_BOT_TOKEN="your_token_here"
```

This stores it encrypted and injects it as an environment variable at runtime. You can verify it was saved:

```bash
fly secrets list
```

#### Step 5 — Create a Persistent Volume for the Database

The bot uses a SQLite database to store user data. Fly.io containers reset on redeploy, so you need a persistent volume to keep the database between deployments:

```bash
fly volumes create taskbot_data --region yyz --size 1
```

> Use the same region you set in `fly.toml`. The `--size 1` means 1 GB, which is more than enough.

#### Step 6 — Deploy

From inside your project folder:

```bash
fly launch --no-deploy   # first time only — reads fly.toml, sets up the app
fly deploy               # builds and deploys the bot
```

After deployment you should see:

```
--> v1 deployed successfully
```

#### Step 7 — Check It's Running

```bash
# View live logs
fly logs

# Check app status
fly status
```

You should see the same log output as running locally:
```
INFO  TaskBot: Logged in as Task Bot#1234
INFO  TaskBot: Slash commands synced.
```

#### Useful Fly.io Commands

```bash
fly logs                  # Live log stream
fly status                # Is the bot running?
fly deploy                # Redeploy after code changes
fly secrets set KEY=value # Update a secret (e.g. new bot token)
fly ssh console           # SSH into the running container
fly scale count 1         # Ensure exactly 1 instance is running
```

#### Updating the Bot After Code Changes

Whenever you change any of the Python files, just run:

```bash
fly deploy
```

Fly rebuilds the Docker image and restarts the bot with zero downtime. Your database volume and secrets are preserved.

---

### Option B — Run Locally (Development / Testing Only)

If you just want to test the bot on your own machine before deploying:

```bash
python -m venv venv
source venv/bin/activate    # macOS / Linux
venv\Scripts\activate       # Windows

pip install -r requirements.txt
python bot.py
```

The bot will go offline when you close the terminal or shut down your computer. Use Fly.io for permanent hosting.

---

### Option C — Docker on Your Own Server

If you have a Linux VPS (DigitalOcean, Linode, etc.) and prefer managing your own machine:

```bash
docker compose up -d        # Start in background
docker compose logs -f      # View logs
docker compose down         # Stop
```

Docker will automatically restart the bot if it crashes or the server reboots.

---

## 6. User Setup — Connecting Your Calendar

Every user in the server sets up independently. Their data is completely private — no one else can see their task list or calendar ID.

> 🔒 **Per-user isolation:** Each user has their own row in the database. Tasks, completions, reminders, and settings are strictly scoped to the individual Discord user ID. Other members — including server admins — cannot view your tasks.

---

### Connecting Google Calendar

1. Open Google Calendar at [calendar.google.com](https://calendar.google.com).
2. In the left sidebar, hover over the calendar you want to use and click the **three-dot menu (⋮)**.
3. Select **"Settings and sharing"**.
4. Under **"Access permissions for events"**, tick **"Make available to public"**. Click OK on the warning.
5. Scroll down to **"Integrate calendar"**. Copy the **Calendar ID** — it looks like:
   ```
   yourname@gmail.com
   ```
   or for a shared calendar:
   ```
   abc123xyz@group.calendar.google.com
   ```
6. In Discord, run:
   ```
   /setup source:google calendar_id:<paste your ID here> channel:#your-channel
   ```

> 📌 **What gets fetched?** The bot reads events from your Google Calendar's public iCal feed. Google Tasks are **not** included — only Calendar Events appear. The calendar must remain public for the bot to access it.

---

### Connecting Notion

Notion requires two things: an **integration token** and a **database ID**.

#### Create a Notion Integration

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations) and click **"+ New integration"**.
2. Name it (e.g. `Discord Task Bot`), select your workspace, and click **Submit**.
3. Copy the **Internal Integration Token** — it starts with `secret_`.
4. Set the capabilities to **Read content only** — the bot never writes to Notion.

#### Share Your Database With the Integration

1. Open the Notion database you want to use.
2. Click **"..."** in the top-right corner → **"Connections"** → find and add your integration.
3. Copy the **Database ID** from the URL bar. The URL looks like:
   ```
   https://notion.so/yourworkspace/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX?v=...
   ```
   The 32-character string between the last `/` and the `?` is your Database ID.

#### Database Property Requirements

Your Notion database must have **at least one** of these property names for date filtering to work:

| Property Name | Type |
|---|---|
| `Date` | Date |
| `Due` | Date |
| `Due Date` | Date |
| `Deadline` | Date |

The bot also looks for a `Description`, `Notes`, or `Body` rich-text property to show task descriptions.

#### Run the Setup Command

```
/setup source:notion calendar_id:<database-id> channel:#your-channel notion_token:<secret_...>
```

---

## 7. Adding Tasks Manually (Without a Calendar)

You don't need a calendar to use the task features. Use `/add` to create tasks directly in Discord. Manual tasks are stored in the bot's database and show up alongside your calendar events in `/tasks`.

### Adding a Manual Task

```
/add name:Buy groceries due:2024-06-15 description:Milk, eggs, bread
```

All parameters except `name` are optional. If you omit `due`, the task has no due date and appears in all daily digests until completed.

### Viewing Your Manual Tasks

```
/mytasks
```

Shows all pending manual tasks. Add `show_done:True` to include completed ones.

### Completing a Manual Task

```
/complete task_name:Buy groceries
```

Partial matches work — typing `groceries` is enough if it uniquely identifies the task. The bot checks manual tasks first, then calendar events.

### Deleting a Manual Task

```
/delete task_name:Buy groceries
```

Permanently removes the task from the database.

---

## 8. Command Reference

> All commands are Discord slash commands. Type `/` in the message box to see them.
> Responses marked *(private)* are ephemeral — only visible to you.

### Setup & Configuration

| Command | Description |
|---|---|
| `/setup` | Link your Google Calendar or Notion database. Run this first. *(private)* |
| `/status` | Show your current configuration, streak, and stats. *(private)* |
| `/unlink` | Remove all your data from the bot. *(private)* |

### Viewing Tasks

| Command | Description |
|---|---|
| `/tasks [date]` | Show your tasks for today or a specific date (`YYYY-MM-DD`). *(private)* |
| `/mytasks [show_done]` | List all your manual (non-calendar) tasks. *(private)* |
| `/weekly` | Weekly summary with per-day chart, streak, and upcoming tasks. *(private)* |

### Managing Tasks

| Command | Description |
|---|---|
| `/complete <task>` | Mark a task as complete — works for both calendar and manual tasks. *(private)* |
| `/add <name> [due] [description]` | Add a manual task directly in Discord. *(private)* |
| `/delete <task>` | Delete a manual task. *(private)* |

### Reminders

| Command | Description |
|---|---|
| `/reminder <task> <datetime>` | Set a reminder. Format: `YYYY-MM-DD HH:MM` (24-hour). *(private)* |
| `/reminders` | List all your pending reminders. *(private)* |
| `/snooze <task> [minutes]` | Snooze a reminder by N minutes (default: 30). *(private)* |
| `/cancelreminder <task>` | Cancel a pending reminder. *(private)* |

### Social

| Command | Description |
|---|---|
| `/nudge @member [message]` | Publicly remind another member to complete their tasks. Visible to the whole channel. |
| `/help` | Show the full command list. *(private)* |

---

## 9. The /nudge Command — Reminding Others

The `/nudge` command lets any server member publicly remind another member to check off their tasks. It posts a visible message in the current channel tagging the target user.

```
/nudge member:@Jane message:Don't forget your standup tasks!
```

The nudge embed shows:

- Who sent the nudge
- The optional custom message (or a friendly default if none is provided)
- How many tasks are still pending for the nudged user today (**count only** — task names stay private)
- Quick-action reminders (`/tasks`, `/complete`, `/weekly`)

> 🛡️ **Privacy note:** The nudge shows only a task *count* — never the actual task names. A teammate can see that you have 3 tasks pending but not what those tasks are.

**Rules:**

- You **cannot nudge yourself** — use `/reminder` instead.
- You **cannot nudge bots**.
- If the target user has not run `/setup`, you are told privately rather than posting publicly.

---

## 10. Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| Commands don't appear in Discord | Slash commands haven't propagated yet | Wait 5–10 minutes after starting the bot for the first time |
| Google Calendar returns no tasks | Calendar is not set to public | Go to Calendar Settings → Access Permissions → Make available to public |
| Google Calendar returns wrong tasks | Wrong Calendar ID | Confirm the ID in Google Calendar → Settings and sharing → Integrate calendar |
| Notion returns `401 Unauthorized` | Invalid token or not shared | Check token starts with `secret_` and the integration is added to the database's Connections |
| Notion returns `404 Not Found` | Wrong Database ID | Copy the 32-character ID from the Notion URL — not the page URL |
| Daily digest not posting | Bot is offline or wrong channel | Confirm `bot.py` is running and the channel in `/status` is correct and accessible |
| Reminder didn't fire | Bot was offline at reminder time | Keep bot running 24/7 — missed reminders fire on next startup if overdue |
| Can't see bot commands | Missing `applications.commands` scope | Re-invite the bot using the OAuth2 URL Generator with `applications.commands` ticked |
| `/setup` says "Could not connect" | Calendar not public / bad token | Follow the setup steps in [Section 6](#6-user-setup--connecting-your-calendar) exactly |

---

## 11. Frequently Asked Questions

**Can multiple people use the bot in the same server?**

Yes — that is the core design. Each user who runs `/setup` gets their own independent task list, reminder schedule, and digest channel. There is no limit on the number of users per server.

**Can two users share the same digest channel?**

Yes. The bot posts separate messages, each mentioning the respective user. You can also give everyone their own private channel for a cleaner experience.

**Does my Google Calendar have to stay public?**

Yes, for as long as you want the bot to fetch your tasks. If you make it private, the bot will show a connection error in your next digest. You can re-link with `/setup` after changing settings.

**Are my Notion tokens stored securely?**

Tokens are stored in the local SQLite database on the machine running the bot. Use a dedicated integration token with **read-only** access and restrict network access to the bot host machine. The bot never writes to or modifies your Notion data.

**What happens if I run `/setup` again?**

Your configuration is updated in place. Your existing completions, reminders, and manual tasks are preserved. Only your calendar source, ID, channel, and token are updated.

**How do I change my digest channel?**

Simply run `/setup` again with the new channel. All other settings remain unchanged.

**Will the bot post digests for days when I have no tasks?**

Yes — it posts a message confirming there are no tasks scheduled, so you always know the bot is working.

**Can I use both Google Calendar events and manual tasks at the same time?**

Yes. Manual tasks (added with `/add`) appear in `/tasks` alongside your Google Calendar or Notion events. The `/complete` command checks manual tasks first, then calendar events.

---

*Discord Task Bot — built with [discord.py](https://discordpy.readthedocs.io/), [httpx](https://www.python-httpx.org/), and [icalendar](https://icalendar.readthedocs.io/).*
