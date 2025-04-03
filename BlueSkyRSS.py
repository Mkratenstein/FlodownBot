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
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bluesky_monitor.log'),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv()

# Log environment variable status
logging.info("Loading environment variables...")
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
BLUESKY_HANDLE = os.getenv('BLUESKY_HANDLE')
BLUESKY_LOGIN_EMAIL = os.getenv('BLUESKY_LOGIN_EMAIL')
BLUESKY_LOGIN_PASSWORD = os.getenv('BLUESKY_LOGIN_PASSWORD')
ALLOWED_ROLE_IDS = os.getenv('ALLOWED_ROLE_IDS')

# Validate required environment variables
required_vars = {
    'DISCORD_TOKEN': DISCORD_TOKEN,
    'DISCORD_CHANNEL_ID': DISCORD_CHANNEL_ID,
    'BLUESKY_HANDLE': BLUESKY_HANDLE,
    'BLUESKY_LOGIN_EMAIL': BLUESKY_LOGIN_EMAIL,
    'BLUESKY_LOGIN_PASSWORD': BLUESKY_LOGIN_PASSWORD,
    'ALLOWED_ROLE_IDS': ALLOWED_ROLE_IDS
}

missing_vars = [var for var, value in required_vars.items() if not value]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Parse allowed role IDs
ALLOWED_ROLE_IDS = [int(role_id.strip()) for role_id in ALLOWED_ROLE_IDS.split(',')]
logging.info(f"Allowed role IDs: {ALLOWED_ROLE_IDS}")
logging.info(f"Channel ID: {DISCORD_CHANNEL_ID}")
logging.info(f"BlueSky Handle: {BLUESKY_HANDLE}")

def has_allowed_role():
    """Check if the user has any of the allowed roles"""
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.user.roles:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return False
            
        user_roles = [role.id for role in interaction.user.roles]
        has_role = any(role_id in user_roles for role_id in ALLOWED_ROLE_IDS)
        
        if not has_role:
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return False
            
        return True
    return commands.check(predicate)

class BlueSkyMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.discord_channel_id = int(DISCORD_CHANNEL_ID)
        self.bluesky_handle = BLUESKY_HANDLE
        self.bluesky_email = BLUESKY_LOGIN_EMAIL
        self.bluesky_password = BLUESKY_LOGIN_PASSWORD
        self.client = None
        self.last_post_uri = None
        self.check_feed.start()
        logging.info("BlueSky Monitor Cog initialized successfully")
        
    def cog_unload(self):
        self.check_feed.cancel()
        logging.info("BlueSky Monitor Cog unloaded")
        
    @tasks.loop(minutes=5)
    async def check_feed(self):
        try:
            logging.info(f"Checking BlueSky feed for {self.bluesky_handle}")
            if not self.client:
                self.client = Client()
                try:
                    self.client.login(self.bluesky_email, self.bluesky_password)
                    logging.info("Successfully logged in to BlueSky")
                except Exception as e:
                    logging.error(f"Failed to login to BlueSky: {str(e)}")
                    return
                    
            # Get the latest posts
            response = self.client.get_author_feed(self.bluesky_handle, limit=1)
            if not response or not response.feed:
                logging.warning("No posts found in BlueSky feed")
                return
                
            latest_post = response.feed[0]
            post_uri = latest_post.post.uri
            
            if not self.last_post_uri:
                self.last_post_uri = post_uri
                logging.info("Initial BlueSky post URI set")
                return
                
            if post_uri != self.last_post_uri:
                logging.info(f"New BlueSky post found: {post_uri}")
                # Process and send the new post
                await self.process_and_send_post(latest_post)
                self.last_post_uri = post_uri
                
        except Exception as e:
            logging.error(f"Error checking BlueSky feed: {str(e)}")
            logging.error(traceback.format_exc())
            
    @check_feed.before_loop
    async def before_check_feed(self):
        await self.bot.wait_until_ready()
        logging.info("BlueSky feed check task started")
        
    async def process_and_send_post(self, post):
        try:
            channel = self.bot.get_channel(self.discord_channel_id)
            if not channel:
                logging.error(f"Could not find channel with ID {self.discord_channel_id}")
                return
                
            # Format the post content
            content = post.post.record.text
            timestamp = datetime.fromisoformat(post.post.indexedAt.replace('Z', '+00:00'))
            formatted_time = timestamp.strftime("%m/%d/%Y %I:%M %p")
            
            # Create the message
            message = f"Hey! Goose the Organization just posted something on BlueSky\n\n{content}\n\n[BlueSky]•{formatted_time}"
            
            # Send the message
            await channel.send(message)
            logging.info(f"Successfully sent BlueSky post to Discord channel")
            
        except Exception as e:
            logging.error(f"Error processing and sending BlueSky post: {str(e)}")
            logging.error(traceback.format_exc())
            
    @app_commands.command(name="testbluesky", description="Test the BlueSky monitor by fetching the latest post")
    @has_allowed_role()
    async def test_bluesky(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            logging.info("Testing BlueSky monitor...")
            
            if not self.client:
                self.client = Client()
                self.client.login(self.bluesky_email, self.bluesky_password)
                
            response = self.client.get_author_feed(self.bluesky_handle, limit=1)
            if not response or not response.feed:
                await interaction.followup.send("No posts found in BlueSky feed.")
                return
                
            latest_post = response.feed[0]
            await self.process_and_send_post(latest_post)
            await interaction.followup.send("Successfully fetched and posted the latest BlueSky post!")
            
        except Exception as e:
            logging.error(f"Error in test_bluesky command: {str(e)}")
            logging.error(traceback.format_exc())
            await interaction.followup.send(f"An error occurred: {str(e)}")

async def setup(bot):
    # Add the cog
    await bot.add_cog(BlueSkyMonitor(bot))
    logging.info("BlueSky Monitor Cog setup completed") 