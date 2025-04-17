import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import logging
from datetime import datetime
import traceback
from atproto import Client, models
import asyncio
import requests
from dotenv import load_dotenv
from config import has_allowed_role, ALLOWED_ROLE_IDS

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Remove file handler for Railway
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

# Validate required environment variables
required_vars = {
    'DISCORD_TOKEN': DISCORD_TOKEN,
    'DISCORD_CHANNEL_ID': DISCORD_CHANNEL_ID,
    'BLUESKY_HANDLE': BLUESKY_HANDLE,
    'BLUESKY_LOGIN_EMAIL': BLUESKY_LOGIN_EMAIL,
    'BLUESKY_LOGIN_PASSWORD': BLUESKY_LOGIN_PASSWORD
}

missing_vars = [var for var, value in required_vars.items() if not value]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

logging.info(f"Channel ID: {DISCORD_CHANNEL_ID}")
logging.info(f"BlueSky Handle: {BLUESKY_HANDLE}")

class BlueSkyMonitor(commands.Cog):
    def __init__(self, bot):
        logging.info("Initializing BlueSky Monitor Cog...")
        self.bot = bot
        self.discord_channel_id = int(DISCORD_CHANNEL_ID)
        self.bluesky_handle = BLUESKY_HANDLE
        self.bluesky_email = BLUESKY_LOGIN_EMAIL
        self.bluesky_password = BLUESKY_LOGIN_PASSWORD
        self.client = None
        self.last_post_uri = None
        
        # Initialize BlueSky client
        try:
            logging.info("Attempting to initialize BlueSky client...")
            self.client = Client()
            # Create session with proper model
            session = self.client.com.atproto.server.create_session(
                data=models.ComAtprotoServerCreateSession.Data(
                    identifier=self.bluesky_email,
                    password=self.bluesky_password
                )
            )
            # Set the session in the client
            self.client.session = session
            # Set the access token in the client's headers
            self.client._headers['Authorization'] = f'Bearer {session.access_jwt}'
            logging.info("Successfully initialized and logged into BlueSky client")
        except Exception as e:
            logging.error(f"Failed to initialize BlueSky client: {str(e)}")
            logging.error(traceback.format_exc())
        
        # Start the feed check task
        try:
            self.check_feed.start()
            logging.info("BlueSky feed check task started successfully")
        except Exception as e:
            logging.error(f"Failed to start feed check task: {str(e)}")
            logging.error(traceback.format_exc())
            
        logging.info("BlueSky Monitor Cog initialization completed")
        
    def cog_unload(self):
        logging.info("Unloading BlueSky Monitor Cog...")
        try:
            self.check_feed.cancel()
            logging.info("Feed check task cancelled successfully")
        except Exception as e:
            logging.error(f"Error cancelling feed check task: {str(e)}")
        logging.info("BlueSky Monitor Cog unloaded")
        
    async def ensure_authenticated(self):
        """Ensure the client is authenticated before making requests"""
        try:
            if not self.client or not hasattr(self.client, 'session'):
                logging.info("Reinitializing BlueSky client and session...")
                self.client = Client()
                try:
                    # Create session with proper model
                    session = self.client.com.atproto.server.create_session(
                        data=models.ComAtprotoServerCreateSession.Data(
                            identifier=self.bluesky_email,
                            password=self.bluesky_password
                        )
                    )
                    # Set the session in the client
                    self.client.session = session
                    # Set the access token in the client's headers
                    self.client._headers['Authorization'] = f'Bearer {session.access_jwt}'
                    logging.info("Successfully reinitialized BlueSky client and session")
                except Exception as auth_error:
                    logging.error(f"Authentication error: {str(auth_error)}")
                    # Try alternative authentication method
                    try:
                        response = requests.post(
                            'https://bsky.social/xrpc/com.atproto.server.createSession',
                            json={
                                'identifier': self.bluesky_email,
                                'password': self.bluesky_password
                            }
                        )
                        if response.status_code == 200:
                            session_data = response.json()
                            self.client.session = type('Session', (), {'access_jwt': session_data.get('accessJwt')})
                            self.client._headers['Authorization'] = f'Bearer {session_data.get("accessJwt")}'
                            logging.info("Successfully authenticated using alternative method")
                        else:
                            raise Exception(f"Authentication failed with status code: {response.status_code}")
                    except Exception as alt_auth_error:
                        logging.error(f"Alternative authentication failed: {str(alt_auth_error)}")
                        raise
        except Exception as e:
            logging.error(f"Error ensuring authentication: {str(e)}")
            logging.error(traceback.format_exc())
            raise
        
    @tasks.loop(minutes=5)
    async def check_feed(self):
        try:
            logging.info(f"Checking BlueSky feed for {self.bluesky_handle}")
            await self.ensure_authenticated()
                    
            # Get the latest posts using the correct method
            logging.info("Fetching latest posts from BlueSky...")
            response = self.client.app.bsky.feed.get_author_feed(
                params=models.AppBskyFeedGetAuthorFeed.Params(
                    actor=self.bluesky_handle,
                    limit=1
                )
            )
            if not response or not response.feed:
                logging.warning("No posts found in BlueSky feed")
                return
                
            latest_post = response.feed[0]
            post_uri = latest_post.post.uri
            logging.info(f"Latest post URI: {post_uri}")
            
            if not self.last_post_uri:
                self.last_post_uri = post_uri
                logging.info("Initial BlueSky post URI set")
                return
                
            if post_uri != self.last_post_uri:
                logging.info(f"New BlueSky post found: {post_uri}")
                # Process and send the new post
                await self.process_and_send_post(latest_post)
                self.last_post_uri = post_uri
            else:
                logging.info("No new posts found")
                
        except Exception as e:
            logging.error(f"Error checking BlueSky feed: {str(e)}")
            logging.error(traceback.format_exc())
            
    @check_feed.before_loop
    async def before_check_feed(self):
        logging.info("Waiting for bot to be ready before starting feed check...")
        await self.bot.wait_until_ready()
        logging.info("Bot is ready, BlueSky feed check task starting")
        
    async def process_and_send_post(self, post):
        try:
            logging.info("Processing new BlueSky post...")
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
            logging.info(f"Successfully sent BlueSky post to Discord channel {self.discord_channel_id}")
            
        except Exception as e:
            logging.error(f"Error processing and sending BlueSky post: {str(e)}")
            logging.error(traceback.format_exc())
            
    @app_commands.command(name="testbluesky", description="Test the BlueSky monitor by fetching the latest post")
    @has_allowed_role()
    async def test_bluesky(self, interaction: discord.Interaction):
        try:
            logging.info(f"Test command triggered by user {interaction.user.name}")
            await interaction.response.defer()
            logging.info("Testing BlueSky monitor...")
            
            await self.ensure_authenticated()
                
            response = self.client.app.bsky.feed.get_author_feed(
                params=models.AppBskyFeedGetAuthorFeed.Params(
                    actor=self.bluesky_handle,
                    limit=1
                )
            )
            if not response or not response.feed:
                logging.warning("No posts found during test command")
                await interaction.followup.send("No posts found in BlueSky feed.")
                return
                
            latest_post = response.feed[0]
            await self.process_and_send_post(latest_post)
            await interaction.followup.send("Successfully fetched and posted the latest BlueSky post!")
            logging.info("Test command completed successfully")
            
        except Exception as e:
            logging.error(f"Error in test_bluesky command: {str(e)}")
            logging.error(traceback.format_exc())
            await interaction.followup.send(f"An error occurred: {str(e)}")

async def setup(bot):
    logging.info("Setting up BlueSky Monitor Cog...")
    try:
        # Add the cog
        await bot.add_cog(BlueSkyMonitor(bot))
        logging.info("BlueSky Monitor Cog setup completed successfully")
    except Exception as e:
        logging.error(f"Error setting up BlueSky Monitor Cog: {str(e)}")
        logging.error(traceback.format_exc())
        raise

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        logging.info("Setting up bot...")
        try:
            await setup(self)
            logging.info("Bot setup completed successfully")
        except Exception as e:
            logging.error(f"Error in bot setup: {str(e)}")
            logging.error(traceback.format_exc())
            raise

    async def on_ready(self):
        logging.info(f'Logged in as {self.user.name} ({self.user.id})')
        logging.info('------')

def main():
    """Main entry point for the bot"""
    try:
        bot = Bot()
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logging.error(f"Error running bot: {str(e)}")
        logging.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    main() 