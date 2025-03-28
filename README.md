# Instagram Monitor Discord Bot

A Discord bot that monitors Instagram profiles for new posts using RSS feeds.

## Setup Instructions

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with the following variables:
- DISCORD_TOKEN: Your Discord bot token
- DISCORD_CHANNEL_ID: The ID of the channel where posts should be sent
- INSTAGRAM_RSS_URL: The RSS feed URL for the Instagram profile you want to monitor

3. Run the bot:
```bash
python bot.py
```

## Features
- Monitors Instagram profiles for new posts
- Posts updates to a specified Discord channel
- Includes post images and descriptions
- Logs all activities to bot.log

## Commands
- !status: Check the bot's current status

## Notes
- The bot checks for new posts every 5 minutes
- Make sure the Instagram profile is public
- The RSS feed URL can be obtained from services like RSS.app or Pikaso.me