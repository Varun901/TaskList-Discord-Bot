# Discord Task Bot
### Complete Setup & User Guide

> Fetch tasks from Google Calendar or Notion • Daily digests • Reminders • Manual tasks • Nudge teammates

---

## Table of Contents

1. [What Is This Bot?](#1-what-is-this-bot)
2. [Requirements](#2-requirements)
3. [Adding the Bot to Discord](#3-adding-the-bot-to-discord)
4. [Installation & Configuration](#4-installation--configuration)
5. [Hosting on Oracle Cloud VM](#5-hosting-on-oracle-cloud-vm)
6. [User Setup — Connecting Your Calendar](#6-user-setup--connecting-your-calendar)
7. [Adding Tasks Manually](#7-adding-tasks-manually)
8. [Command Reference](#8-command-reference)
9. [The /nudge Command](#9-the-nudge-command)
10. [Troubleshooting](#10-troubleshooting)
11. [FAQ](#11-frequently-asked-questions)

---

## 1. What Is This Bot?

The Discord Task Bot connects each member of your Discord server to their own Google Calendar or Notion database. Every morning the bot automatically posts a personalised task digest in the channel of their choice. Members can mark tasks complete, set reminders, add manual tasks, and even nudge each other to stay on track.

**Key highlights:**

- **Per-user calendars** — each person links their own source, completely separate from everyone else
- Supports **Google Calendar** (public iCal) and **Notion** databases
- **Daily digest** posted automatically at a configurable time
- **Manual tasks** — add tasks directly in Discord alongside your calendar events
- **Reminders** with snooze support
- **/nudge** — publicly remind a teammate to complete their tasks
- **Weekly summary** with streak tracking and an upcoming 7-day preview

---

## 2. Requirements

Before running the bot you need the following on the machine that will host it:

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 or later | Installed on the Oracle VM — see Section 5 |
| pip | Latest | Bundled with Python |
| Discord account | Any | To create the bot application |
| Internet access | Always-on | Bot must stay connected 24/7 |
| Google or Notion account | Any | At least one user needs a calendar |

**Python packages** (installed automatically from `requirements.txt`):

- `discord.py >= 2.3` — Discord bot framework
- `httpx` — async HTTP client for calendar fetching
- `icalendar` — parses Google Calendar iCal feeds
- `python-dotenv` — loads `.env` config file
- `pytz` — timezone support

> **Optional: Docker** — You can run the bot inside a Docker container on your Oracle VM instead of installing Python directly. A `Dockerfile` and `docker-compose.yml` are included. See [Option B in Section 5](#option-b--docker-on-oracle-vm).

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
   - **Server Members Intent**
   - **Message Content Intent**
7. Click **"Save Changes"**.
8. Click **"Reset Token"** to reveal your bot token. **Copy it** — you will need it later.

> **Keep your token secret.** Never share your bot token publicly. Anyone with it can control your bot. If it leaks, regenerate it immediately from the Developer Portal.

### Step 2 — Invite the Bot to Your Server

Build the invite URL manually. Replace `YOUR_CLIENT_ID` with your application's Client ID (found on the **"General Information"** page of your app in the Developer Portal):

```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=84992&scope=bot+applications.commands
```

**How to find your Client ID:**
1. In the Developer Portal, click your application.
2. Click **"General Information"** in the left sidebar.
3. Copy the **"Application ID"** — this is your Client ID.

Paste the completed URL into your browser, select your server from the dropdown, and click **Authorise**.

The `permissions=84992` covers exactly what the bot needs:

| Permission | Why it's needed |
|---|---|
| `View Channels` | Lets the bot see the channels it posts into |
| `Send Messages` | Posts daily digests and reminder alerts |
| `Embed Links` | Sends formatted embed cards for task lists |
| `Read Message History` | Allows the bot to function correctly in channels |

The bot will now appear in your server's member list but will show as offline until you run it.

> **Note on the "Redirects" field:** The Developer Portal may show a Redirects section with the note *"You must specify at least one URI for authentication to work."* This only applies to OAuth2 **user login flows** (e.g. "Sign in with Discord" on a website). This bot uses the `bot` scope to join your server — it does not perform user authentication and does not need a redirect URI. Leave the field empty.

---

## 4. Installation & Configuration

### Step 1 — Project Structure

```
discord_task_bot/
├── src/
│   ├── bot.py                # Entry point — all slash commands
│   ├── task_manager.py       # Digest and reminder logic
│   ├── calendar_fetcher.py   # Google Calendar and Notion fetchers
│   ├── database.py           # SQLite storage (per-user isolation)
│   └── config.py             # Reads environment variables
├── Dockerfile                # Docker image definition
├── docker-compose.yml        # Docker Compose support
├── requirements.txt          # Python dependencies
└── .env.example              # Configuration template — copy to .env
```

### Step 2 — Create Your `.env` File

A template is included. Copy it and fill in your values:

```bash
cp .env.example .env
```

Then open `.env` in any editor and set your values:

```env
# Required
DISCORD_BOT_TOKEN=your_bot_token_here

# Optional — defaults shown
DAILY_POST_HOUR=8
DAILY_POST_MINUTE=0
TIMEZONE=America/Toronto
DATABASE_PATH=taskbot.db
```

| Variable | Default | Description |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *(required)* | Bot token from the Developer Portal |
| `DAILY_POST_HOUR` | `8` | Hour to post daily digests (24-hour, 0–23) |
| `DAILY_POST_MINUTE` | `0` | Minute to post (0–59) |
| `TIMEZONE` | `America/Toronto` | Your server's timezone ([full list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)) |
| `DATABASE_PATH` | `taskbot.db` | Path to the SQLite file (created automatically) |

> The bot will refuse to start with a clear error message if `DISCORD_BOT_TOKEN` is missing or empty, or if the hour/minute values are out of range.

### Step 3 — Install Python Dependencies

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 4 — Test the Bot Locally

```bash
python src/bot.py
```

You should see:

```
INFO  TaskBot: Logged in as Task Bot#1234 (ID: 123456789)
INFO  TaskBot: Slash commands synced.
INFO  TaskBot: Daily digest scheduled for 08:00 America/Toronto
```

> Slash commands may take **1–5 minutes** to appear in Discord after the first sync. Press `Ctrl+C` to stop — Section 5 covers keeping it running permanently on Oracle VM.

---

## 5. Hosting on Oracle Cloud VM

Oracle Cloud's Always Free tier includes two Arm-based VMs (4 OCPUs and 24 GB RAM combined) at no cost, permanently. This is more than enough to run the bot indefinitely.

Two deployment options are covered below. **Option A (systemd)** is simpler to manage day-to-day. **Option B (Docker)** is useful if you prefer container isolation or already run Docker on your VM.

---

### Option A — Direct Python with systemd (Recommended)

systemd runs the bot as a background service, starts it automatically on VM boot, and restarts it immediately if it crashes.

#### Step 1 — Connect to Your VM

```bash
ssh -i /path/to/your_private_key ubuntu@<your-vm-public-ip>
```

> Your VM's public IP is shown in the OCI Console under **Compute → Instances → your instance → Instance information**.

#### Step 2 — Install Python

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv
```

Verify:

```bash
python3 --version   # should be 3.10 or later
```

#### Step 3 — Upload the Project

From your **local machine**, copy the project folder to the VM:

```bash
scp -i /path/to/your_private_key -r /path/to/discord_task_bot ubuntu@<ip>:~/
```

Or, if the project is in a git repository, clone it directly on the VM:

```bash
git clone <your-repo-url> ~/discord_task_bot
```

#### Step 4 — Create the .env File on the VM

```bash
cd ~/discord_task_bot
cp .env.example .env
nano .env
```

Fill in your values and save with `Ctrl+O`, `Enter`, `Ctrl+X`.

Set the database path to keep it inside the project folder:

```env
DISCORD_BOT_TOKEN=your_token_here
DAILY_POST_HOUR=8
DAILY_POST_MINUTE=0
TIMEZONE=America/Toronto
DATABASE_PATH=/home/ubuntu/discord_task_bot/taskbot.db
```

#### Step 5 — Install Dependencies

```bash
cd ~/discord_task_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Step 6 — Test That It Runs

```bash
python src/bot.py
```

Confirm the bot logs in and the slash commands sync, then press `Ctrl+C`.

#### Step 7 — Create a systemd Service

```bash
sudo nano /etc/systemd/system/taskbot.service
```

Paste the following exactly — adjust the paths only if you installed in a different directory:

```ini
[Unit]
Description=Discord Task Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/discord_task_bot
EnvironmentFile=/home/ubuntu/discord_task_bot/.env
ExecStart=/home/ubuntu/discord_task_bot/venv/bin/python src/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save and close (`Ctrl+O`, `Enter`, `Ctrl+X`).

#### Step 8 — Enable and Start the Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable taskbot    # start automatically on boot
sudo systemctl start taskbot     # start right now
```

Check it's running:

```bash
sudo systemctl status taskbot
```

You should see `Active: active (running)`.

#### Useful Service Commands

```bash
sudo systemctl status taskbot      # Is it running?
sudo systemctl restart taskbot     # Restart after changes
sudo systemctl stop taskbot        # Stop the bot
sudo systemctl disable taskbot     # Prevent starting on boot
journalctl -u taskbot -f           # Live log stream
journalctl -u taskbot -n 100       # Last 100 log lines
```

#### Updating the Bot After Code Changes

From your **local machine**, upload the changed file(s):

```bash
scp -i /path/to/key src/bot.py ubuntu@<ip>:~/discord_task_bot/src/
```

Then restart the service on the VM:

```bash
sudo systemctl restart taskbot
journalctl -u taskbot -f   # confirm it came back up cleanly
```

---

### Option B — Docker on Oracle VM

Use this if you prefer Docker. The database is stored on a named Docker volume so it survives container restarts and rebuilds.

#### Step 1 — Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
```

Log out and back in for the group change to take effect:

```bash
exit
ssh -i /path/to/key ubuntu@<ip>
```

#### Step 2 — Upload the Project and Create .env

```bash
# From your local machine
scp -i /path/to/key -r /path/to/discord_task_bot ubuntu@<ip>:~/
```

Then on the VM:

```bash
cd ~/discord_task_bot
nano .env
```

Use `/data/taskbot.db` as the database path — this is where Docker mounts the persistent volume:

```env
DISCORD_BOT_TOKEN=your_token_here
DAILY_POST_HOUR=8
DAILY_POST_MINUTE=0
TIMEZONE=America/Toronto
DATABASE_PATH=/data/taskbot.db
```

#### Step 3 — Start with Docker Compose

```bash
docker compose up -d        # build image and start in background
docker compose logs -f      # stream logs
```

Docker Compose is configured with `restart: unless-stopped`, so the bot restarts automatically on crash or VM reboot.

#### Useful Docker Commands

```bash
docker compose logs -f          # Live log stream
docker compose ps               # Is the container running?
docker compose restart          # Restart the bot
docker compose down             # Stop and remove the container
docker compose up -d --build    # Rebuild image after code changes
```

#### Updating the Bot After Code Changes

```bash
# From local machine — upload changed files
scp -i /path/to/key src/bot.py ubuntu@<ip>:~/discord_task_bot/src/

# On the VM — rebuild and restart
cd ~/discord_task_bot
docker compose up -d --build
```

---

### Option C — Run Locally (Development / Testing Only)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python src/bot.py
```

The bot goes offline when you close the terminal or shut down your computer. Use Option A or B on the Oracle VM for permanent hosting.

---

## 6. User Setup — Connecting Your Calendar

Every user in the server sets up independently. Their data is completely private — no one else can see their task list or calendar ID.

> **Per-user isolation:** Each user has their own row in the database. Tasks, completions, reminders, and settings are strictly scoped to the individual Discord user ID. Other members — including server admins — cannot view your tasks.

**Every user must run `/setup` before using any other command**, including manual tasks. Setup takes about 30 seconds.

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
   or for a shared/secondary calendar:
   ```
   abc123xyz@group.calendar.google.com
   ```
6. In Discord, run:
   ```
   /setup source:Google Calendar calendar_id:<paste your ID here> channel:#your-channel
   ```

> **What gets fetched?** The bot reads events from your Google Calendar's public iCal feed. Google Tasks are **not** included — only Calendar Events appear. The calendar must remain public for the bot to access it.

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
/setup source:Notion calendar_id:<database-id> channel:#your-channel notion_token:<secret_...>
```

---

## 7. Adding Tasks Manually

You don't need a calendar event for every task. Use `/add` to create tasks directly in Discord. Manual tasks are stored in the bot's database and appear alongside your calendar events in `/tasks`.

> **Note:** You still need to run `/setup` first (to register your digest channel), even if you only plan to use manual tasks.

### Adding a Manual Task

```
/add name:Buy groceries due:2024-06-15 description:Milk, eggs, bread
```

All parameters except `name` are optional. If you omit `due`, the task has no due date and appears in every daily digest until you complete it.

### Viewing Your Manual Tasks

```
/mytasks
```

Shows all pending manual tasks. Add `show_done:True` to include completed ones.

### Completing a Task

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
| `/setup` | Link your Google Calendar or Notion database. Choose the source from the dropdown. *(private)* |
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

## 9. The /nudge Command

The `/nudge` command lets any server member publicly remind another member to check off their tasks. It posts a visible message in the current channel tagging the target user.

```
/nudge member:@Jane message:Don't forget your standup tasks!
```

The nudge embed shows:

- Who sent the nudge
- The optional custom message (or a friendly default if none is provided)
- How many tasks are still pending for the nudged user today (**count only** — task names stay private)
- Quick-action reminders (`/tasks`, `/complete`, `/weekly`)

> **Privacy note:** The nudge shows only a task *count* — never the actual task names. A teammate can see that you have 3 tasks pending but not what those tasks are.

**Rules:**

- You **cannot nudge yourself** — use `/reminder` instead.
- You **cannot nudge bots**.
- If the target user has not run `/setup`, you are told privately rather than posting publicly.

---

## 10. Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| Bot won't start: "DISCORD_BOT_TOKEN is not set" | Missing `.env` file or empty token | Create `.env` in the project root and set `DISCORD_BOT_TOKEN` |
| Bot won't start: hour/minute out of range | Invalid schedule values in `.env` | Set `DAILY_POST_HOUR` to 0–23 and `DAILY_POST_MINUTE` to 0–59 |
| Commands don't appear in Discord | Slash commands haven't propagated yet | Wait 5–10 minutes after starting the bot for the first time |
| systemd service won't start | Wrong paths in service file | Run `journalctl -u taskbot -n 50` and check the error; verify all paths in the `[Service]` section |
| Google Calendar returns no tasks | Calendar is not set to public | Go to Calendar Settings → Access Permissions → Make available to public |
| Google Calendar returns wrong tasks | Wrong Calendar ID | Confirm the ID in Google Calendar → Settings and sharing → Integrate calendar |
| Notion returns `401 Unauthorized` | Invalid token or integration not connected | Check the token starts with `secret_` and the integration is added to the database via Connections |
| Notion returns `404 Not Found` | Wrong Database ID | Copy the 32-character ID from the Notion page URL — not a page inside the database |
| Notion tasks not showing for a date | Date property name not recognised | Rename your date property to one of: `Date`, `Due`, `Due Date`, or `Deadline` |
| Daily digest not posting | Bot is offline or wrong channel | Run `sudo systemctl status taskbot` and check the channel in `/status` is accessible |
| Reminders not firing | Bot was offline at reminder time | Keep the bot running 24/7 — overdue reminders fire on next startup |
| Can't see bot commands | Missing `applications.commands` scope | Re-invite the bot using the OAuth2 URL in [Section 3](#3-adding-the-bot-to-discord) |
| `/setup` says "Could not connect" | Calendar not public / bad Notion token | Follow the setup steps in [Section 6](#6-user-setup--connecting-your-calendar) exactly |

---

## 11. Frequently Asked Questions

**Can multiple people use the bot in the same server?**

Yes — that is the core design. Each user who runs `/setup` gets their own independent task list, reminder schedule, and digest channel. There is no limit on the number of users per server.

**Can two users share the same digest channel?**

Yes. The bot posts separate messages, each mentioning the respective user. You can also give everyone their own private channel for a cleaner experience.

**Does my Google Calendar have to stay public?**

Yes, for as long as you want the bot to fetch your tasks. If you make it private, the bot will show a connection error in your next digest. You can re-link at any time with `/setup`.

**Are my Notion tokens stored securely?**

Tokens are stored in the local SQLite database on the Oracle VM. Use a dedicated integration token with **read-only** access. The bot never writes to or modifies your Notion data.

**What happens if I run `/setup` again?**

Your configuration is updated in place. Your existing completions, reminders, and manual tasks are preserved. Only your calendar source, ID, channel, and token are updated.

**How do I change my digest channel?**

Run `/setup` again with the new channel. All other settings remain unchanged.

**Will the bot post digests on days when I have no tasks?**

Yes — it posts a message confirming there are no tasks scheduled for that day, so you always know the bot is working.

**Can I use both Google Calendar events and manual tasks at the same time?**

Yes. Manual tasks (added with `/add`) appear in `/tasks` alongside your Google Calendar or Notion events. The `/complete` command checks manual tasks first, then calendar events.

**I only want manual tasks — do I still need a Google Calendar or Notion account?**

You still need to run `/setup` (which requires a calendar source) to register your digest channel. If you don't have a calendar, set up a free Google account, create a calendar, make it public, and use that Calendar ID — you can leave it empty and use only manual tasks.

---

*Discord Task Bot — built with [discord.py](https://discordpy.readthedocs.io/), [httpx](https://www.python-httpx.org/), and [icalendar](https://icalendar.readthedocs.io/).*
