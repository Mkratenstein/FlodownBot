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
load_dotenv()

# Verify environment variables
required_vars = ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'BLUESKY_HANDLE', 'BLUESKY_PASSWORD', 'APPLICATION_ID']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

logging.info("Environment variables loaded successfully")
logging.info(f"Channel ID: {os.getenv('DISCORD_CHANNEL_ID')}")
logging.info(f"BlueSky Handle: {os.getenv('BLUESKY_HANDLE')}")

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
        self.bsky_password = os.getenv('BLUESKY_PASSWORD')
        self.bsky_client = Client()
        self.check_feed.start()
        logging.info("BlueSky Monitor initialized")

    async def send_latest_post(self):
        """Send the latest post to Discord for testing"""
        try:
            logging.info("Fetching latest post for initial display")
            self.bsky_client.login(self.bsky_handle, self.bsky_password)
            response = self.bsky_client.get_author_feed({'actor': self.bsky_handle})
            
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
                url=f"https://bsky.app/profile/{self.bsky_handle}.bsky.social/post/{latest_post.uri.split('/')[-1]}",
                timestamp=datetime.now(),
                color=discord.Color.blue()
            )
            
            # Add image if available
            if hasattr(latest_post.post.embed, 'images'):
                embed.set_image(url=latest_post.post.embed.images[0].fullsize)
                logging.info(f"Added image to embed: {latest_post.post.embed.images[0].fullsize}")
            
            # Add footer with source
            embed.set_footer(text="BlueSky", icon_url="https://bsky.app/static/icon.png")
            
            await channel.send(f"Hey! Goose the Organization just posted something on [BlueSky](https://bsky.app/profile/{self.bsky_handle}.bsky.social)", embed=embed)
            logging.info(f"Successfully sent initial post to channel {self.discord_channel_id}")
            
        except Exception as e:
            error_msg = f"Error sending initial post: {str(e)}\nTraceback: {traceback.format_exc()}"
            logging.error(error_msg)

    def cog_unload(self):
        self.check_feed.cancel()

    @tasks.loop(minutes=5)
    async def check_feed(self):
        try:
            logging.info(f"Checking BlueSky feed for: {self.bsky_handle}")
            self.bsky_client.login(self.bsky_handle, self.bsky_password)
            response = self.bsky_client.get_author_feed({'actor': self.bsky_handle})
            
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
                    url=f"https://bsky.app/profile/{self.bsky_handle}.bsky.social/post/{latest_post.uri.split('/')[-1]}",
                    timestamp=datetime.now(),
                    color=discord.Color.green()
                )
                
                # Add image if available
                if hasattr(latest_post.post.embed, 'images'):
                    embed.set_image(url=latest_post.post.embed.images[0].fullsize)
                    logging.info(f"Added image to embed: {latest_post.post.embed.images[0].fullsize}")
                
                # Add footer with source
                embed.set_footer(text="BlueSky", icon_url="https://bsky.app/static/icon.png")
                
                await channel.send(f"Hey! Goose the Organization just posted something on [BlueSky](https://bsky.app/profile/{self.bsky_handle}.bsky.social)", embed=embed)
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
    bluesky_monitor = BlueSkyMonitor(bot)
    await bot.add_cog(bluesky_monitor)
    
    # Send initial post after cog is added
    await bluesky_monitor.send_latest_post()
    
    try:
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
            description="BlueSky Monitor Bot is running",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Last Check", value=last_check)
        embed.add_field(name="BlueSky Handle", value=bluesky_cog.bsky_handle if bluesky_cog else "Not initialized")
        embed.add_field(name="Channel ID", value=bluesky_cog.discord_channel_id if bluesky_cog else "Not initialized")
        embed.add_field(name="Last Post URI", value=bluesky_cog.last_post_uri if bluesky_cog else "Not initialized")
        
        await interaction.response.send_message(embed=embed)
        logging.info(f"statusbluesky command used by {interaction.user.name}")
    except Exception as e:
        error_msg = f"Error in statusbluesky command: {str(e)}\nTraceback: {traceback.format_exc()}"
        logging.error(error_msg)
        await interaction.response.send_message("❌ An error occurred while checking the status.", ephemeral=True)

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN')) 