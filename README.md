# Instagram RSS Discord Bot

A Discord bot that monitors an Instagram RSS feed and posts updates to a specified channel.

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
   - `APPLICATION_ID`: Your bot's application ID

3. **Channel Permissions**
   Make sure the bot has these permissions in the target channel:
   - Send Messages
   - Embed Links
   - View Channel
   - Read Message History

## Commands
- `/statusflodown`: Check the bot's status and last Instagram check

## Features
- Monitors Instagram RSS feed every 5 minutes
- Posts new Instagram content to Discord
- Includes images and post descriptions
- Provides status updates via slash commands

## Notes
- The bot checks for new posts every 5 minutes
- Make sure the Instagram profile is public
- The RSS feed URL can be obtained from services like RSS.app or Pikaso.me