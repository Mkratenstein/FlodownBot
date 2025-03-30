import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
import traceback
from atproto import Client
import asyncio
import requests

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# Load environment variables
# Try both local and container paths
env_paths = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Instagram.env'),
    '/app/Instagram.env'
]

env_loaded = False
for env_path in env_paths:
    if os.path.exists(env_path):
        logging.info(f"Found .env file at: {env_path}")
        try:
            # Try to read the file contents
            with open(env_path, 'r') as f:
                contents = f.read()
                logging.info(f"Successfully read .env file. Contains {len(contents)} characters")
                logging.info("File contents (with sensitive data masked):")
                for line in contents.splitlines():
                    if line.strip() and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        if key in ['DISCORD_TOKEN', 'BLUESKY_LOGIN_PASSWORD']:
                            value = '********'
                        logging.info(f"{key}: {value}")
        except Exception as e:
            logging.error(f"Error reading .env file: {str(e)}")
        
        load_dotenv(env_path)
        env_loaded = True
        break

if not env_loaded:
    logging.warning("No .env file found in any expected location")

# Debug logging for environment variables
logging.info("Checking environment variables:")
for var in ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'BLUESKY_HANDLE', 'BLUESKY_LOGIN_EMAIL', 'BLUESKY_LOGIN_PASSWORD', 'APPLICATION_ID']:
    value = os.getenv(var)
    if value:
        # Mask sensitive values
        if var in ['DISCORD_TOKEN', 'BLUESKY_LOGIN_PASSWORD']:
            value = '********'
        logging.info(f"{var}: {value}")
    else:
        logging.error(f"{var}: Not found")

# Verify environment variables
required_vars = ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'BLUESKY_HANDLE', 'BLUESKY_LOGIN_EMAIL', 'BLUESKY_LOGIN_PASSWORD', 'APPLICATION_ID']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

logging.info("Environment variables loaded successfully")
logging.info(f"Channel ID: {os.getenv('DISCORD_CHANNEL_ID')}")
logging.info(f"BlueSky Handle: {os.getenv('BLUESKY_HANDLE')}")
logging.info(f"BlueSky Login Email: {os.getenv('BLUESKY_LOGIN_EMAIL')}")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, application_id=os.getenv('APPLICATION_ID'))

class BlueSkyMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.discord_channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
        self.bsky_handle = os.getenv('BLUESKY_HANDLE')
        self.bsky_login_email = os.getenv('BLUESKY_LOGIN_EMAIL')
        self.bsky_login_password = os.getenv('BLUESKY_LOGIN_PASSWORD')
        self.bsky_client = Client()
        self.initialized = False
        
        # Try to login to BlueSky
        try:
            logging.info("Attempting to login to BlueSky...")
            # Create a session using requests first to verify credentials
            session = requests.Session()
            response = session.post(
                'https://bsky.social/xrpc/com.atproto.server.createSession',
                json={
                    'identifier': self.bsky_login_email,
                    'password': self.bsky_login_password
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'accessJwt' in data and 'did' in data:
                    logging.info("Successfully authenticated with BlueSky")
                    # Now try to initialize the client
                    try:
                        self.bsky_client.login(self.bsky_login_email, self.bsky_login_password)
                        self.initialized = True
                        logging.info("BlueSky client initialized successfully")
                    except Exception as e:
                        if "validation errors for Response" in str(e):
                            # If we get validation errors but the session was created, we can still proceed
                            if hasattr(self.bsky_client, '_session') and self.bsky_client._session:
                                logging.warning("BlueSky login succeeded despite validation errors")
                                self.initialized = True
                            else:
                                raise e
                        else:
                            raise e
                else:
                    raise Exception("Invalid response from BlueSky API")
            else:
                raise Exception(f"Failed to authenticate with BlueSky: {response.status_code}")
                
        except Exception as e:
            logging.error(f"Failed to initialize BlueSky client: {str(e)}")
            # Notify Discord about the failure
            channel = self.bot.get_channel(self.discord_channel_id)
            if channel:
                asyncio.create_task(channel.send("⚠️ Failed to initialize BlueSky monitor. Instagram monitoring will be stopped."))
            return

    def cog_unload(self):
        if hasattr(self, 'check_feed'):
            self.check_feed.cancel()

@bot.event
async def on_ready():
    logging.info(f'Bot is ready: {bot.user.name}')
    
    # First try to initialize BlueSky monitor
    try:
        bluesky_monitor = BlueSkyMonitor(bot)
        await bot.add_cog(bluesky_monitor)
        if not bluesky_monitor.initialized:
            logging.error("BlueSky monitor failed to initialize properly")
            return
        logging.info("BlueSky Monitor initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize BlueSky Monitor: {str(e)}")
        # Don't initialize Instagram monitor if BlueSky fails
        return

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN')) 