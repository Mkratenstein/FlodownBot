# Instagram and BlueSky RSS Discord Bot

A Discord bot that monitors both Instagram and BlueSky feeds and posts updates to a specified channel.

## Setup Instructions

1. **Bot Permissions**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Select your bot application
   - Go to "OAuth2 > URL Generator"
   - Select these scopes:
     - `bot`
     - `applications.commands`
   - Select these bot permissions:
     - Send Messages
     - Embed Links
     - View Channel
     - Read Message History
   - Use the generated URL to reinvite the bot to your server

2. **Environment Variables**
   Required environment variables in Railway:
   - `DISCORD_TOKEN`: Your bot's token
   - `DISCORD_CHANNEL_ID`: The channel ID where posts will be sent
   - `INSTAGRAM_RSS_URL`: Your Instagram RSS feed URL
   - `BLUESKY_HANDLE`: Your BlueSky handle (e.g., username.bsky.social)
   - `BLUESKY_PASSWORD`: Your BlueSky account password
   - `APPLICATION_ID`: Your bot's application ID

3. **Channel Permissions**
   Make sure the bot has these permissions in the target channel:
   - Send Messages
   - Embed Links
   - View Channel
   - Read Message History

## Commands
- `/statusflodown`: Check the bot's status and last Instagram check
- `/statusbluesky`: Check the bot's status and last BlueSky check

## Features
- Monitors Instagram RSS feed every 5 minutes
- Monitors BlueSky feed every 5 minutes
- Posts new Instagram and BlueSky content to Discord
- Includes images and post descriptions
- Provides status updates via slash commands

## Notes
- The bot checks for new posts every 5 minutes
- Make sure the Instagram profile is public
- The RSS feed URL can be obtained from services like RSS.app or Pikaso.me
- BlueSky integration requires your account credentials
- Both Instagram and BlueSky posts will be sent to the same Discord channel