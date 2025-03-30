import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import logging
from datetime import datetime
import traceback
from atproto import Client
import asyncio
import requests
from config import bot, has_allowed_role

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
for var in ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'BLUESKY_HANDLE', 'BLUESKY_LOGIN_EMAIL', 'BLUESKY_LOGIN_PASSWORD', 'APPLICATION_ID', 'ALLOWED_ROLE_IDS']:
    value = os.getenv(var)
    if value:
        # Mask sensitive values
        if var in ['DISCORD_TOKEN', 'BLUESKY_LOGIN_PASSWORD']:
            value = '********'
        logging.info(f"{var}: {value}")
    else:
        logging.error(f"{var}: Not found")

# Verify environment variables
required_vars = ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'BLUESKY_HANDLE', 'BLUESKY_LOGIN_EMAIL', 'BLUESKY_LOGIN_PASSWORD', 'APPLICATION_ID', 'ALLOWED_ROLE_IDS']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Parse allowed role IDs
ALLOWED_ROLE_IDS = [int(role_id.strip()) for role_id in os.getenv('ALLOWED_ROLE_IDS').split(',')]
logging.info(f"Allowed role IDs: {ALLOWED_ROLE_IDS}")

logging.info("Environment variables loaded successfully")
logging.info(f"Channel ID: {os.getenv('DISCORD_CHANNEL_ID')}")
logging.info(f"BlueSky Handle: {os.getenv('BLUESKY_HANDLE')}")
logging.info(f"BlueSky Login Email: {os.getenv('BLUESKY_LOGIN_EMAIL')}")

class BlueSkyMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.discord_channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
        self.bsky_handle = os.getenv('BLUESKY_HANDLE')
        self.bsky_login_email = os.getenv('BLUESKY_LOGIN_EMAIL')
        self.bsky_login_password = os.getenv('BLUESKY_LOGIN_PASSWORD')
        self.session = None
        self.initialized = False
        self.last_post_uri = None
        
        # Try to login to BlueSky
        try:
            logging.info("Attempting to login to BlueSky...")
            # Create a session using requests
            self.session = requests.Session()
            response = self.session.post(
                'https://bsky.social/xrpc/com.atproto.server.createSession',
                json={
                    'identifier': self.bsky_login_email,
                    'password': self.bsky_login_password
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'accessJwt' in data and 'did' in data:
                    # Set up the session headers
                    self.session.headers.update({
                        'Authorization': f'Bearer {data["accessJwt"]}'
                    })
                    self.initialized = True
                    logging.info("BlueSky session initialized successfully")
                    # Start the feed checking task
                    self.check_feed.start()
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

    @app_commands.command(name="testbluesky", description="Test the BlueSky monitor by fetching the latest post")
    @has_allowed_role()
    async def test_bluesky(self, interaction: discord.Interaction):
        """Test the BlueSky monitor by fetching the latest post"""
        try:
            if not self.session:
                await interaction.response.send_message("❌ BlueSky monitor is not initialized.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            
            # Get the author's feed
            response = self.session.get(
                'https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed',
                params={'actor': self.bsky_handle}
            )
            
            if response.status_code != 200:
                await interaction.followup.send(f"❌ Failed to fetch BlueSky feed: {response.status_code}", ephemeral=True)
                return
                
            data = response.json()
            if not data.get('feed'):
                await interaction.followup.send("❌ No posts found in BlueSky feed", ephemeral=True)
                return
                
            latest_post = data['feed'][0]
            post_uri = latest_post['post']['uri']
            
            # Get the post content
            post_content = latest_post['post']['record'].get('text', '')
            post_images = latest_post['post']['embed'].get('images', []) if 'embed' in latest_post['post'] else []
            
            # Create embed for the post
            embed = discord.Embed(
                description=post_content,
                url=f"https://bsky.app/profile/{self.bsky_handle}/post/{post_uri.split('/')[-1]}",
                timestamp=datetime.now(),
                color=discord.Color.blue()
            )
            
            # Add images if available
            if post_images:
                embed.set_image(url=post_images[0].get('fullsize', ''))
            
            # Add footer with source
            embed.set_footer(text="BlueSky", icon_url="https://bsky.app/static/icon.png")
            
            await interaction.followup.send("✅ BlueSky monitor is working correctly! Here's the latest post:", embed=embed, ephemeral=True)
            logging.info(f"testbluesky command used by {interaction.user.name}")
            
        except Exception as e:
            error_msg = f"Error in testbluesky command: {str(e)}\nTraceback: {traceback.format_exc()}"
            logging.error(error_msg)
            await interaction.followup.send(f"❌ An error occurred while testing BlueSky monitor: {str(e)}", ephemeral=True)

    def cog_unload(self):
        if hasattr(self, 'check_feed'):
            self.check_feed.cancel()

    @tasks.loop(minutes=5)
    async def check_feed(self):
        try:
            if not self.session:
                logging.error("No active BlueSky session")
                return

            logging.info(f"Checking BlueSky feed for {self.bsky_handle}")
            
            # Get the author's feed
            response = self.session.get(
                'https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed',
                params={'actor': self.bsky_handle}
            )
            
            if response.status_code != 200:
                logging.error(f"Failed to fetch BlueSky feed: {response.status_code}")
                return
                
            data = response.json()
            if not data.get('feed'):
                logging.warning("No posts found in BlueSky feed")
                return
                
            latest_post = data['feed'][0]
            post_uri = latest_post['post']['uri']
            
            # If this is the first post we've seen, just store it and return
            if self.last_post_uri is None:
                self.last_post_uri = post_uri
                logging.info("Initial BlueSky post URI set")
                return
                
            # Check if this is a new post
            if post_uri != self.last_post_uri:
                logging.info("New BlueSky post detected")
                self.last_post_uri = post_uri
                
                # Get the post content
                post_content = latest_post['post']['record'].get('text', '')
                post_images = latest_post['post']['embed'].get('images', []) if 'embed' in latest_post['post'] else []
                
                # Create embed for the post
                embed = discord.Embed(
                    description=post_content,
                    url=f"https://bsky.app/profile/{self.bsky_handle}/post/{post_uri.split('/')[-1]}",
                    timestamp=datetime.now(),
                    color=discord.Color.blue()
                )
                
                # Add images if available
                if post_images:
                    embed.set_image(url=post_images[0].get('fullsize', ''))
                    logging.info(f"Added image to embed: {post_images[0].get('fullsize', '')}")
                
                # Add footer with source
                embed.set_footer(text="BlueSky", icon_url="https://bsky.app/static/icon.png")
                
                # Send to Discord
                channel = self.bot.get_channel(self.discord_channel_id)
                if channel:
                    await channel.send(f"Hey! Goose the Organization just posted something on [BlueSky](https://bsky.app/profile/{self.bsky_handle})", embed=embed)
                    logging.info(f"Successfully sent new BlueSky post to channel {self.discord_channel_id}")
                else:
                    logging.error(f"Could not find channel with ID: {self.discord_channel_id}")
            else:
                logging.info("No new BlueSky posts detected")
                
        except Exception as e:
            error_msg = f"Error checking BlueSky feed: {str(e)}\nTraceback: {traceback.format_exc()}"
            logging.error(error_msg)
            # Try to notify in Discord if possible
            try:
                channel = self.bot.get_channel(self.discord_channel_id)
                if channel:
                    await channel.send(f"⚠️ Error checking BlueSky feed: {str(e)}")
                else:
                    logging.error(f"Could not find channel with ID: {self.discord_channel_id}")
            except Exception as e:
                logging.error(f"Failed to send error notification to Discord channel: {str(e)}")

    @check_feed.before_loop
    async def before_check_feed(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(BlueSkyMonitor(bot))
    logging.info("BlueSky Monitor cog added successfully") 