import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
import traceback
from atproto import Client, models
import asyncio

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
        self.last_post_uri = None
        self.discord_channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
        self.bsky_handle = os.getenv('BLUESKY_HANDLE')
        self.bsky_login_email = os.getenv('BLUESKY_LOGIN_EMAIL')
        self.bsky_login_password = os.getenv('BLUESKY_LOGIN_PASSWORD')
        self.bsky_client = Client()
        self.initialized = False
        
        # Create a session with the API
        try:
            # Try to login and handle validation errors
            try:
                # Create session with raw response handling
                response = self.bsky_client._session.post(
                    'https://bsky.social/xrpc/com.atproto.server.createSession',
                    json={
                        'identifier': self.bsky_login_email,
                        'password': self.bsky_login_password
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logging.info(f"BlueSky API Response: {data}")
                    
                    # Verify we have the required data
                    if not data.get('accessJwt') or not data.get('did'):
                        raise Exception(f"Missing required data in response: {data}")
                    
                    # Set the session data directly
                    self.bsky_client._session.headers.update({
                        'Authorization': f'Bearer {data["accessJwt"]}'
                    })
                    self.bsky_client._session.me = data['did']
                    logging.info("Successfully logged into BlueSky")
                    self.initialized = True
                else:
                    error_msg = f"Failed to create session: {response.status_code} {response.text}"
                    logging.error(error_msg)
                    raise Exception(error_msg)
            except Exception as e:
                logging.error(f"Failed to login to BlueSky: {str(e)}")
                # Notify Discord about the failure
                channel = self.bot.get_channel(self.discord_channel_id)
                if channel:
                    asyncio.create_task(channel.send("⚠️ Failed to initialize BlueSky monitor. Instagram monitoring will be stopped."))
                return  # Exit initialization if login fails
                
        except Exception as e:
            logging.error(f"Failed to initialize BlueSky client: {str(e)}")
            # Notify Discord about the failure
            channel = self.bot.get_channel(self.discord_channel_id)
            if channel:
                asyncio.create_task(channel.send("⚠️ Failed to initialize BlueSky monitor. Instagram monitoring will be stopped."))
            return  # Exit initialization if login fails
            
        if self.initialized:
            self.check_feed.start()
            logging.info("BlueSky Monitor initialized")
            logging.info(f"Monitoring BlueSky handle: {self.bsky_handle}")
        else:
            logging.error("BlueSky Monitor failed to initialize")

    async def send_latest_post(self):
        """Send the latest post to Discord for testing"""
        try:
            if not self.initialized:
                logging.error("BlueSky monitor not properly initialized")
                return

            logging.info("Fetching latest post for initial display")
            # Ensure we have a valid session
            if not hasattr(self.bsky_client, '_session') or not self.bsky_client._session:
                try:
                    self.bsky_client.login(self.bsky_login_email, self.bsky_login_password)
                except Exception as e:
                    if "validation errors for Response" in str(e):
                        if not hasattr(self.bsky_client, '_session') or not self.bsky_client._session:
                            logging.error(f"Failed to re-login to BlueSky: {str(e)}")
                            return
                    else:
                        logging.error(f"Failed to re-login to BlueSky: {str(e)}")
                        return
            
            response = self.bsky_client.app.bsky.feed.get_author_feed({'actor': self.bsky_handle})
            
            if not response.feed:
                logging.warning("No posts found for initial display")
                return
                
            latest_post = response.feed[0]
            channel = self.bot.get_channel(self.discord_channel_id)
            
            if not channel:
                logging.error(f"Could not find channel with ID: {self.discord_channel_id}")
                return
            
            # Create embed for the latest post
            embed = discord.Embed(
                description=latest_post.post.record.text,
                url=f"https://bsky.app/profile/{self.bsky_handle}/post/{latest_post.uri.split('/')[-1]}",
                timestamp=datetime.now(),
                color=discord.Color.blue()
            )
            
            # Add image if available
            if hasattr(latest_post.post.embed, 'images'):
                embed.set_image(url=latest_post.post.embed.images[0].fullsize)
                logging.info(f"Added image to embed: {latest_post.post.embed.images[0].fullsize}")
            
            # Add footer with source
            embed.set_footer(text="BlueSky", icon_url="https://bsky.app/static/icon.png")
            
            # Send as ephemeral message for testing
            await channel.send(f"Hey! Goose the Organization just posted something on [BlueSky](https://bsky.app/profile/{self.bsky_handle})", embed=embed)
            logging.info(f"Successfully sent initial post to channel {self.discord_channel_id}")
            
        except Exception as e:
            error_msg = f"Error sending initial post: {str(e)}\nTraceback: {traceback.format_exc()}"
            logging.error(error_msg)
            try:
                channel = self.bot.get_channel(self.discord_channel_id)
                if channel:
                    await channel.send(f"⚠️ Error sending initial post: {str(e)}")
                else:
                    logging.error(f"Could not find channel with ID: {self.discord_channel_id}")
            except Exception as e:
                logging.error(f"Failed to send error notification to Discord channel: {str(e)}")

    def cog_unload(self):
        self.check_feed.cancel()

    @tasks.loop(minutes=5)
    async def check_feed(self):
        try:
            if not self.initialized:
                logging.error("BlueSky monitor not properly initialized")
                return

            logging.info(f"Checking BlueSky feed for: {self.bsky_handle}")
            # Ensure we have a valid session
            if not hasattr(self.bsky_client, '_session') or not self.bsky_client._session:
                try:
                    self.bsky_client.login(self.bsky_login_email, self.bsky_login_password)
                except Exception as e:
                    if "validation errors for Response" in str(e):
                        if not hasattr(self.bsky_client, '_session') or not self.bsky_client._session:
                            logging.error(f"Failed to re-login to BlueSky: {str(e)}")
                            return
                    else:
                        logging.error(f"Failed to re-login to BlueSky: {str(e)}")
                        return
            
            response = self.bsky_client.app.bsky.feed.get_author_feed({'actor': self.bsky_handle})
            
            if not response.feed:
                logging.warning("No posts found in BlueSky feed")
                return
                
            latest_post = response.feed[0]
            logging.info(f"Latest post URI: {latest_post.uri}")
            logging.info(f"Last known post URI: {self.last_post_uri}")
            
            if self.last_post_uri is None:
                self.last_post_uri = latest_post.uri
                logging.info("Initial post URI set")
            elif latest_post.uri != self.last_post_uri:
                logging.info("New post detected, preparing to send to Discord")
                self.last_post_uri = latest_post.uri
                channel = self.bot.get_channel(self.discord_channel_id)
                
                if not channel:
                    logging.error(f"Could not find channel with ID: {self.discord_channel_id}")
                    return
                
                # Create embed for the new post
                embed = discord.Embed(
                    description=latest_post.post.record.text,
                    url=f"https://bsky.app/profile/{self.bsky_handle}/post/{latest_post.uri.split('/')[-1]}",
                    timestamp=datetime.now(),
                    color=discord.Color.green()
                )
                
                # Add image if available
                if hasattr(latest_post.post.embed, 'images'):
                    embed.set_image(url=latest_post.post.embed.images[0].fullsize)
                    logging.info(f"Added image to embed: {latest_post.post.embed.images[0].fullsize}")
                
                # Add footer with source
                embed.set_footer(text="BlueSky", icon_url="https://bsky.app/static/icon.png")
                
                # Send as ephemeral message for testing
                await channel.send(f"Hey! Goose the Organization just posted something on [BlueSky](https://bsky.app/profile/{self.bsky_handle})", embed=embed)
                logging.info(f"Successfully sent new post to channel {self.discord_channel_id}")
            else:
                logging.info("No new posts detected")
                    
        except Exception as e:
            error_msg = f"Error checking feed: {str(e)}\nTraceback: {traceback.format_exc()}"
            logging.error(error_msg)
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
    
    # Only initialize Instagram monitor if BlueSky monitor is running
    instagram_monitor = InstagramMonitor(bot)
    await bot.add_cog(instagram_monitor)
    
    # Send initial post after cog is added
    await instagram_monitor.send_latest_post()
    
    try:
        # Add delay before syncing commands
        await asyncio.sleep(5)
        # Sync commands globally
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
        
        # Log all registered commands
        for command in bot.tree.get_commands():
            logging.info(f"Registered command: {command.name}")
    except Exception as e:
        logging.error(f"Failed to sync commands: {str(e)}\nTraceback: {traceback.format_exc()}")

@bot.tree.command(name="statusbluesky", description="Check the bot's status and last BlueSky check")
async def status(interaction: discord.Interaction):
    """Check the bot's status"""
    try:
        # Get the BlueSkyMonitor cog
        bluesky_cog = bot.get_cog('BlueSkyMonitor')
        last_check = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        embed = discord.Embed(
            title="Bot Status",
            description="BlueSky Monitor Bot is running" if bluesky_cog else "BlueSky Monitor Bot is not running",
            color=discord.Color.green() if bluesky_cog else discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Last Check", value=last_check)
        embed.add_field(name="BlueSky Handle", value=bluesky_cog.bsky_handle if bluesky_cog else "Not initialized")
        embed.add_field(name="Channel ID", value=bluesky_cog.discord_channel_id if bluesky_cog else "Not initialized")
        embed.add_field(name="Last Post URI", value=bluesky_cog.last_post_uri if bluesky_cog else "Not initialized")
        embed.add_field(name="Initialized", value="Yes" if bluesky_cog and bluesky_cog.initialized else "No")
        
        await interaction.response.send_message(embed=embed)
        logging.info(f"statusbluesky command used by {interaction.user.name}")
    except Exception as e:
        error_msg = f"Error in statusbluesky command: {str(e)}\nTraceback: {traceback.format_exc()}"
        logging.error(error_msg)
        await interaction.response.send_message("❌ An error occurred while checking the status.", ephemeral=True)

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN')) 