# Discord Birthday Bot

A working MVP birthday bot written in Python.

## Features

- `/birthday set` — save your birthday.
- `/birthday view` — view your birthday.
- `/birthday remove` — delete your birthday.
- `/birthday upcoming` — list upcoming birthdays.
- `/birthday-admin set` — an administrator adds a birthday for another member.
- `/birthday-admin remove` — an administrator deletes a member's birthday.
- `/birthday-admin channel` — set the birthday announcement channel.
- `/birthday-admin timezone` — set the time zone.
- `/birthday-admin hour` — set the hour when announcements are sent.
- `/birthday-admin message` — change the birthday message.
- `/birthday-admin settings` — show the current settings.
- `/birthday-admin test` — test message delivery without waiting for the next day.

Admin commands require the Discord **Manage Server** permission.

## 1. Requirements

- Python 3.11 or later.
- A Discord server where you have permission to manage the server.

Check your Python version:

```bash
python --version
```

## 2. Create a Discord Application

1. Open the Discord Developer Portal.
2. Click **New Application**.
3. Name the application, for example, `Birthday Bot`.
4. Open the **Bot** section.
5. Click **Reset Token** and copy the token.
6. Do not share the token with anyone or publish the `.env` file.
7. In **Installation** or **OAuth2 → URL Generator**, select:
   - scope: `bot`;
   - scope: `applications.commands`;
   - bot permissions:
     - View Channels;
     - Send Messages;
     - Embed Links;
     - Read Message History.
8. Open the generated link and add the bot to your server.

This project does not need the Message Content Intent.

## 3. Installation

### Windows PowerShell

```powershell
cd path\to\discord_birthday_bot
```

Create a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create the `.env` file:

```powershell
Copy-Item .env.example .env
notepad .env
```

### Linux

```bash
cd /path/to/discord_birthday_bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
nano .env
```

## 4. Configure `.env`

```env
DISCORD_TOKEN=your_bot_token_here
DEFAULT_TIMEZONE=your_timezone
DATABASE_PATH=data/birthdays.db
DEV_GUILD_ID=
```

### Make slash commands appear quickly

Discord's global commands may take a while to appear. For development, you can specify a server ID:

1. In Discord, go to **User Settings → Advanced** and enable **Developer Mode**.
2. Right-click the server icon and select **Copy Server ID**.
3. Paste the ID here:

```env
DEV_GUILD_ID=123456789012345678
```

When development is complete, remove the `DEV_GUILD_ID` value and restart the bot. It will then perform a global command sync.

## 5. Run the Bot

```bash
python bot.py
```

A successful startup looks something like this:

```text
Logged in as Birthday Bot (...)
```

Keep the terminal window open while the bot needs to be running.

## 6. Initial Server Setup

In Discord, run:

```text
/birthday-admin channel
```

Select the birthday announcement channel.

Then run:

```text
/birthday-admin timezone name:Asia/Almaty
/birthday-admin hour hour:9
```

Add a test birthday for yourself:

```text
/birthday set
```

Select today's day and month. Then run:

```text
/birthday-admin test
```

The bot should send a message to the configured channel.

## 7. Keep the Bot Running

To keep the bot running 24/7, it must run continuously on one of the following:

- a VPS;
- a home computer that stays on;
- a Docker host;
- a cloud service that supports persistent Python processes.

SQLite is suitable for a single bot process. Do not run two copies at the same time using the same database.

## Security

- Mentions of `@everyone` and roles are disabled programmatically.
