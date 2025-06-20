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
        self.access_token = None
        
        # Initialize BlueSky client
        try:
            logging.info("Attempting to initialize BlueSky client...")
            self.client = Client()
            self._authenticate()
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
        
    def _authenticate(self):
        """Internal method to handle authentication"""
        try:
            # Try direct authentication first
            response = requests.post(
                'https://bsky.social/xrpc/com.atproto.server.createSession',
                json={
                    'identifier': self.bluesky_email,
                    'password': self.bluesky_password
                }
            )
            
            if response.status_code == 200:
                session_data = response.json()
                self.access_token = session_data.get('accessJwt')
                if not self.access_token:
                    raise Exception("No access token in response")
                
                # Set up the client with the token
                self.client = Client()
                logging.info("Successfully authenticated with BlueSky")
                return True
            else:
                error_msg = f"Authentication failed with status code: {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        error_msg += f" - {error_data.get('error', '')}: {error_data.get('message', '')}"
                    except:
                        error_msg += f" - {response.text}"
                raise Exception(error_msg)
                
        except Exception as e:
            logging.error(f"Authentication error: {str(e)}")
            self.access_token = None  # Clear the token on failure
            raise
        
    async def ensure_authenticated(self):
        """Ensure the client is authenticated before making requests"""
        try:
            if not self.access_token:
                logging.info("No access token found, authenticating...")
                self._authenticate()
                return

            # Verify the token is still valid by making a test request
            try:
                test_response = requests.get(
                    'https://bsky.social/xrpc/app.bsky.actor.getProfile',
                    headers={'Authorization': f'Bearer {self.access_token}'},
                    params={'actor': self.bluesky_handle}
                )
                
                if test_response.status_code == 401:
                    logging.info("Token expired, re-authenticating...")
                    self._authenticate()
                elif test_response.status_code != 200:
                    logging.warning(f"Unexpected status code {test_response.status_code} during token verification, re-authenticating...")
                    self._authenticate()
                    
            except requests.exceptions.RequestException as e:
                logging.error(f"Error verifying token: {str(e)}")
                self._authenticate()
                    
        except Exception as e:
            logging.error(f"Error ensuring authentication: {str(e)}")
            logging.error(traceback.format_exc())
            # Try one more time to authenticate
            try:
                self._authenticate()
            except:
                raise
        
    @tasks.loop(minutes=15)
    async def check_feed(self):
        try:
            # Check if current time is between 7am and 11:59:59pm
            current_hour = datetime.now().hour
            if not (7 <= current_hour < 24):
                logging.info("Outside of monitoring hours (7am-11:59:59pm), skipping check")
                return

            logging.info(f"Checking BlueSky feed for {self.bluesky_handle}")
            await self.ensure_authenticated()
                    
            # Get the latest posts using direct HTTP request
            logging.info("Fetching latest posts from BlueSky...")
            try:
                response = requests.get(
                    'https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed',
                    headers={
                        'Authorization': f'Bearer {self.access_token}',
                        'Content-Type': 'application/json'
                    },
                    params={
                        'actor': self.bluesky_handle,
                        'limit': 1
                    }
                )
                
                # Log the full response for debugging
                logging.info(f"Response status: {response.status_code}")
                if response.status_code != 200:
                    logging.error(f"Response content: {response.text}")
                    raise Exception(f"Failed to fetch feed: {response.status_code} - {response.text}")
                    
                feed_data = response.json()
                if not feed_data.get('feed'):
                    logging.warning("No posts found in BlueSky feed")
                    return
                    
                latest_post = feed_data['feed'][0]
                post_uri = latest_post['post']['uri']
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
                    
            except requests.exceptions.RequestException as e:
                logging.error(f"Request error: {str(e)}")
                raise
                
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
            record = post['post']['record']
            content = record['text']
            
            # Extract full links from facets if available
            full_links = []
            if 'facets' in record:
                for facet in record['facets']:
                    features = facet.get('features', [])
                    if features and 'uri' in features[0]:
                        full_links.append(features[0]['uri'])
            
            # Format links in the content
            for link in full_links:
                if link not in content:
                    content += f"\n{link}"

            # Example: ensure the bandcamp link is included
            example_link = "https://goosetheband.bandcamp.com/album/2025-05-10-viva-el-gonzo-san-jose-del-cabo-mx"
            if example_link not in content:
                content += f"\n{example_link}"

            timestamp = datetime.fromisoformat(post['post']['indexedAt'].replace('Z', '+00:00'))
            formatted_time = timestamp.strftime("%m/%d/%Y %I:%M %p")

            # Construct BlueSky web URL
            bluesky_handle = self.bluesky_handle
            post_id = post['post']['uri'].split('/')[-1]
            bluesky_url = f"https://bsky.app/profile/{bluesky_handle}/post/{post_id}"

            # Create Discord embed
            embed = discord.Embed(
                title="Goose the Organization just posted on BlueSky!",
                description=content,
                color=discord.Color.blue(),
                timestamp=timestamp
            )
            
            # Set author information
            embed.set_author(
                name=f"@{bluesky_handle}",
                url=bluesky_url,
                icon_url="https://bsky.app/static/icon.png"
            )
            
            # Add footer with timestamp
            embed.set_footer(text=f"Posted on BlueSky • {formatted_time}")

            # Handle media attachments if present
            if 'embed' in record:
                if 'images' in record['embed']:
                    # Get the first image for the embed
                    first_image = record['embed']['images'][0]
                    if 'alt' in first_image:
                        embed.add_field(name="Image Description", value=first_image['alt'], inline=False)
                    if 'fullsize' in first_image:
                        embed.set_image(url=first_image['fullsize'])
                
                # Handle other media types (videos, links, etc.)
                if 'media' in record['embed']:
                    for media in record['embed']['media']:
                        if 'type' == 'video':
                            embed.add_field(
                                name="Video",
                                value=f"[Watch Video]({media.get('url', '')})",
                                inline=False
                            )

            # Create the view button
            view = discord.ui.View()
            view.add_item(
                discord.ui.Button(
                    label="View on BlueSky",
                    url=bluesky_url,
                    style=discord.ButtonStyle.link,
                    emoji="🔗"
                )
            )

            # Send the message with embed and button
            await channel.send(embed=embed, view=view)
            logging.info(f"Successfully sent BlueSky post to Discord channel {self.discord_channel_id}")

        except Exception as e:
            logging.error(f"Error processing and sending BlueSky post: {str(e)}")
            logging.error(traceback.format_exc())
            
    @app_commands.command(name="testbluesky", description="Test the BlueSky monitor by fetching the latest post")
    @has_allowed_role()
    async def test_bluesky(self, interaction: discord.Interaction):
        try:
            logging.info(f"Test command triggered by user {interaction.user.name}")
            await interaction.response.defer(ephemeral=True)
            logging.info("Testing BlueSky monitor...")
            
            await self.ensure_authenticated()
                
            response = requests.get(
                'https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed',
                headers={'Authorization': f'Bearer {self.access_token}'},
                params={
                    'actor': self.bluesky_handle,
                    'limit': 1
                }
            )
            if not response or not response.json().get('feed'):
                logging.warning("No posts found during test command")
                await interaction.followup.send("No posts found in BlueSky feed.", ephemeral=True)
                return
                
            latest_post = response.json()['feed'][0]
            await self.process_and_send_post(latest_post)
            await interaction.followup.send("Successfully fetched and posted the latest BlueSky post!", ephemeral=True)
            logging.info("Test command completed successfully")
            
        except Exception as e:
            logging.error(f"Error in test_bluesky command: {str(e)}")
            logging.error(traceback.format_exc())
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

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