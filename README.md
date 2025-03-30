# Instagram and BlueSky RSS Discord Bot

A Discord bot that monitors both Instagram and BlueSky feeds and posts updates to a specified channel. The bot includes role-based permissions for command access.

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
   Required environment variables in `.env` file:
   - `DISCORD_TOKEN`: Your bot's token
   - `DISCORD_CHANNEL_ID`: The channel ID where posts will be sent
   - `INSTAGRAM_RSS_URL`: Your Instagram RSS feed URL
   - `BLUESKY_HANDLE`: The BlueSky handle to monitor (e.g., username.bsky.social)
   - `BLUESKY_LOGIN_EMAIL`: Your BlueSky account email for authentication
   - `BLUESKY_LOGIN_PASSWORD`: Your BlueSky account password
   - `APPLICATION_ID`: Your bot's application ID
   - `ALLOWED_ROLE_IDS`: Comma-separated list of Discord role IDs that can use commands

3. **Channel Permissions**
   Make sure the bot has these permissions in the target channel:
   - Send Messages
   - Embed Links
   - View Channel
   - Read Message History

4. **Role-Based Permissions**
   - The bot requires specific roles to use commands
   - Add the role IDs to the `ALLOWED_ROLE_IDS` environment variable
   - Users without the required roles will receive an ephemeral error message

## Deployment

1. **Local Deployment**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Run the bot
   python InstagramRSS.py
   ```

2. **Container Deployment**
   ```bash
   # Build the container
   docker build -t discord-bot .
   
   # Run the container
   docker run -d --env-file Instagram.env discord-bot
   ```

3. **Platform Deployment**
   - Make sure to set all required environment variables in your deployment platform
   - The bot requires Python 3.8 or higher
   - Ensure the deployment platform has enough memory (recommended: 512MB+)
   - For Heroku deployment:
     - Add Python buildpack
     - Set environment variables in the platform settings
     - The Procfile will automatically use the correct Python version

4. **Environment Setup**
   - Create a virtual environment (recommended):
     ```bash
     python -m venv venv
     source venv/bin/activate  # On Windows: venv\Scripts\activate
     pip install -r requirements.txt
     ```
   - Or use system Python:
     ```bash
     pip install -r requirements.txt
     ```

## Commands
- `/testinstagram`: Test the Instagram monitor by fetching the latest post
- `/testbluesky`: Test the BlueSky monitor by fetching the latest post
- `/statusflodown`: Check the bot's status and last Instagram check
- `/statusbluesky`: Check the bot's status and last BlueSky check
- `/inviteflodown`: Get the bot's invite link with proper permissions

## Features
- Monitors Instagram RSS feed every 5 minutes
- Monitors BlueSky feed every 5 minutes
- Posts new Instagram and BlueSky content to Discord
- Includes images and post descriptions
- Provides status updates via slash commands
- Role-based command access control
- Automatic error handling and notifications
- Detailed logging system

## Dependencies
- discord.py==2.3.2
- python-dotenv==1.0.0
- feedparser==6.0.10
- aiohttp==3.9.1
- atproto==0.0.31
- requests==2.31.0
- PyNaCl==1.5.0 (for voice support)
- lxml==4.9.3 (for better XML parsing)
- html5lib==1.1 (for better HTML parsing)

## Troubleshooting

1. **Instagram RSS Feed Issues**
   - Ensure the Instagram profile is public
   - Verify the RSS feed URL is valid and accessible
   - Check if the RSS service (RSS.app/Pikaso.me) is working
   - Try regenerating the RSS feed URL

2. **BlueSky Authentication Issues**
   - Verify your BlueSky credentials are correct
   - Check if your BlueSky account is active
   - Ensure the handle is correct and accessible

3. **Discord Connection Issues**
   - Verify the bot token is valid
   - Check if the bot has the required permissions
   - Ensure the channel ID is correct

4. **Common Error Messages**
   - "Invalid RSS feed": The RSS feed URL is invalid or expired
   - "Failed to initialize BlueSky monitor": Authentication or connection issues
   - "No entries found in RSS feed": The feed is empty or inaccessible
   - "Python version not found": Make sure Python is installed and in your PATH

## Notes
- The bot checks for new posts every 5 minutes
- Make sure the Instagram profile is public
- The RSS feed URL can be obtained from services like RSS.app or Pikaso.me
- BlueSky integration requires a BlueSky account for authentication (using email)
- Both Instagram and BlueSky posts will be sent to the same Discord channel
- The bot will stop Instagram monitoring if BlueSky monitoring fails to initialize
- All commands require specific role permissions to use
- Logs are stored in `bot.log` for debugging