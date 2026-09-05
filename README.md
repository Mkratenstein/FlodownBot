# FlodownBot

A Discord bot that watches a BlueSky account and posts new activity to a Discord channel as rich embeds.

The bot is the current FlodownBot runtime. Instagram RSS monitoring from earlier versions is no longer part of the running app.

## What it does

- Polls the configured BlueSky account every **15 minutes**
- Runs during **7:00 AM – 11:59 PM** (local server time)
- Sends new posts to a Discord channel as an embed with:
  - Post text and linked URLs from BlueSky facets
  - Author attribution back to the BlueSky profile
  - Images (including alt text when present)
  - Video links when the post embed includes video media
  - A **View on BlueSky** button
- Exposes `/testbluesky` so allowed roles can fetch and post the latest BlueSky post on demand (the confirmation is ephemeral; the post itself goes to the channel)

On startup, the first seen post is stored as a baseline and is **not** forwarded. Only later posts are sent to Discord.

## Requirements

- Python 3.8+
- A Discord bot application with message and slash-command permissions
- A BlueSky account that can authenticate and read the target handle's feed

## Discord setup

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and select the bot application.
2. Under **OAuth2 > URL Generator**, enable:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: **View Channel**, **Send Messages**, **Embed Links**, **Read Message History**
3. Invite the bot with the generated URL.
4. Confirm the same channel permissions on the target Discord channel.
5. Enable **Message Content Intent** for the bot if Discord still requires it for this application.

## Environment variables

Create a `.env` file in the project root for local runs, or set the same values in your host (Railway, etc.).

| Variable | Required | Description |
| --- | --- | --- |
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `DISCORD_CHANNEL_ID` | Yes | Channel ID that should receive BlueSky posts |
| `APPLICATION_ID` | Yes | Discord application ID |
| `ALLOWED_ROLE_IDS` | Yes | Comma-separated Discord role IDs allowed to use slash commands |
| `BLUESKY_HANDLE` | Yes | Handle to monitor, for example `username.bsky.social` |
| `BLUESKY_LOGIN_EMAIL` | Yes | BlueSky login email used to create a session |
| `BLUESKY_LOGIN_PASSWORD` | Yes | BlueSky password or app password |

Example:

```env
DISCORD_TOKEN=your-discord-bot-token
DISCORD_CHANNEL_ID=123456789012345678
APPLICATION_ID=123456789012345678
ALLOWED_ROLE_IDS=111111111111111111,222222222222222222
BLUESKY_HANDLE=username.bsky.social
BLUESKY_LOGIN_EMAIL=you@example.com
BLUESKY_LOGIN_PASSWORD=your-bluesky-app-password
```

Do not commit `.env` or real credentials.

## Local run

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
python BlueSkyRSS.py
```

The process stays running and logs to stdout.

## Deployment

The repo includes a `Procfile` for worker-style hosts:

```
worker: python BlueSkyRSS.py
```

Typical Railway / Heroku-style setup:

1. Connect this GitHub repository.
2. Set the environment variables listed above in the host's dashboard (not in git).
3. Use a Python runtime and start the worker process from the Procfile.
4. Give the service enough memory (512 MB is a reasonable starting point).

Logs go to stdout so they show up in the platform log stream.

## Commands

| Command | Who can use it | What it does |
| --- | --- | --- |
| `/testbluesky` | Users with a role in `ALLOWED_ROLE_IDS` | Fetches the latest post for `BLUESKY_HANDLE` and sends it to `DISCORD_CHANNEL_ID` |

Users without an allowed role get an ephemeral permission error.

## Project layout

| File | Role |
| --- | --- |
| `BlueSkyRSS.py` | Bot entry point, BlueSky polling, Discord embeds, `/testbluesky` |
| `config.py` | Environment loading and role-gated command checks |
| `requirements.txt` | Python dependencies |
| `Procfile` | Worker process definition for hosted deploys |
| `database.py` | Unused leftover from the old Instagram monitor (not imported by the current bot) |

## Dependencies

- `discord.py==2.3.2`
- `python-dotenv==1.0.0`
- `aiohttp==3.9.1`
- `atproto==0.0.32`
- `requests==2.31.0`
- `PyNaCl==1.5.0`
- `python-dateutil==2.8.2`

## Troubleshooting

**Missing required environment variables**  
Confirm every variable in the table above is set. `config.py` and `BlueSkyRSS.py` both refuse to start if required values are absent.

**BlueSky authentication failures**  
- Use an app password if the account has extra login protection.
- Confirm `BLUESKY_LOGIN_EMAIL` and `BLUESKY_LOGIN_PASSWORD`.
- Confirm `BLUESKY_HANDLE` is the account you intend to watch.

**No Discord messages for new posts**  
- The bot skips checks overnight (before 7:00 AM local time).
- The first post seen after startup is used as a baseline and is not posted.
- Confirm `DISCORD_CHANNEL_ID` and that the bot can send embeds in that channel.
- Use `/testbluesky` to force a fetch and post.

**Slash command not visible or permission error**  
- Reinvite the bot with the `applications.commands` scope.
- Add your Discord role ID to `ALLOWED_ROLE_IDS`.

## Notes

- Last-seen post tracking is in memory. A restart will treat the current latest post as the new baseline.
- BlueSky sessions are created against `bsky.social` and refreshed when the access token expires.
- The Discord embed title currently names **Goose the Organization** as the BlueSky poster.
