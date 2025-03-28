import discord
from discord.ext import commands, tasks
import feedparser
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
import traceback

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
required_vars = ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'INSTAGRAM_RSS_URL', 'APPLICATION_ID']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

logging.info("Environment variables loaded successfully")
logging.info(f"Channel ID: {os.getenv('DISCORD_CHANNEL_ID')}")
logging.info(f"RSS URL: {os.getenv('INSTAGRAM_RSS_URL')}")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix='!', intents=intents, application_id=os.getenv('APPLICATION_ID'))

class InstagramMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_entry_id = None
        self.rss_url = os.getenv('INSTAGRAM_RSS_URL')
        self.discord_channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
        self.check_feed.start()
        logging.info("Instagram Monitor initialized")

    async def send_latest_post(self):
        """Send the latest post to Discord for testing"""
        try:
            logging.info("Fetching latest post for initial display")
            feed = feedparser.parse(self.rss_url)
            
            if not feed.entries:
                logging.warning("No entries found in RSS feed for initial display")
                return
                
            latest_entry = feed.entries[0]
            channel = self.bot.get_channel(self.discord_channel_id)
            
            if not channel:
                logging.error(f"Could not find channel with ID: {self.discord_channel_id}")
                return
            
            # Clean up the description by removing HTML tags
            description = latest_entry.description
            if '<div>' in description:
                # Extract text content from div tags
                description = description.replace('<div>', '').replace('</div>', '\n').strip()
            
            # Create embed for the latest post
            embed = discord.Embed(
                title=latest_entry.title,  # Use the original title from the feed
                description=description,
                url=latest_entry.link,
                timestamp=datetime.now(),
                color=discord.Color.blue()
            )
            
            # Add image if available
            if 'media_content' in latest_entry:
                embed.set_image(url=latest_entry.media_content[0]['url'])
                logging.info(f"Added image to embed: {latest_entry.media_content[0]['url']}")
            
            # Add footer with source
            embed.set_footer(text="Instagram", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Instagram_logo.svg/2560px-Instagram_logo.svg.png")
            
            await channel.send("Initial post display for testing:", embed=embed)
            logging.info(f"Successfully sent initial post to channel {self.discord_channel_id}")
            
        except Exception as e:
            error_msg = f"Error sending initial post: {str(e)}\nTraceback: {traceback.format_exc()}"
            logging.error(error_msg)

    def cog_unload(self):
        self.check_feed.cancel()

    @tasks.loop(minutes=5)
    async def check_feed(self):
        try:
            logging.info(f"Checking RSS feed: {self.rss_url}")
            feed = feedparser.parse(self.rss_url)
            
            # Check if the feed is valid
            if feed.bozo:  # Feed parsing error
                error_msg = f"Invalid RSS feed: {feed.bozo_exception}"
                logging.error(error_msg)
                channel = self.bot.get_channel(self.discord_channel_id)
                if channel:
                    await channel.send(f"RSS Feed Error: The feed URL appears to be invalid or expired. Please check the URL: {self.rss_url}")
                return
            
            # Log feed details
            logging.info(f"Feed title: {feed.feed.get('title', 'No title')}")
            logging.info(f"Feed description: {feed.feed.get('description', 'No description')}")
            logging.info(f"Feed link: {feed.feed.get('link', 'No link')}")
            
            if not feed.entries:
                logging.warning("No entries found in RSS feed")
                return
                
            latest_entry = feed.entries[0]
            logging.info(f"Latest entry ID: {latest_entry.id}")
            logging.info(f"Latest entry title: {latest_entry.get('title', 'No title')}")
            logging.info(f"Latest entry link: {latest_entry.get('link', 'No link')}")
            logging.info(f"Last known entry ID: {self.last_entry_id}")
            
            if self.last_entry_id is None:
                self.last_entry_id = latest_entry.id
                logging.info("Initial post ID set")
            elif latest_entry.id != self.last_entry_id:
                logging.info("New post detected, preparing to send to Discord")
                self.last_entry_id = latest_entry.id
                channel = self.bot.get_channel(self.discord_channel_id)
                
                if not channel:
                    logging.error(f"Could not find channel with ID: {self.discord_channel_id}")
                    return
                
                # Clean up the description by removing HTML tags
                description = latest_entry.description
                if '<div>' in description:
                    # Extract text content from div tags
                    description = description.replace('<div>', '').replace('</div>', '\n').strip()
                
                # Create embed for the new post
                embed = discord.Embed(
                    title=latest_entry.title,  # Use the original title from the feed
                    description=description,
                    url=latest_entry.link,
                    timestamp=datetime.now(),
                    color=discord.Color.green()
                )
                
                # Add image if available
                if 'media_content' in latest_entry:
                    embed.set_image(url=latest_entry.media_content[0]['url'])
                    logging.info(f"Added image to embed: {latest_entry.media_content[0]['url']}")
                
                # Add footer with source
                embed.set_footer(text="Instagram", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/Instagram_logo.svg/2560px-Instagram_logo.svg.png")
                
                await channel.send(embed=embed)
                logging.info(f"Successfully sent new post to channel {self.discord_channel_id}")
            else:
                logging.info("No new posts detected")
                    
        except Exception as e:
            error_msg = f"Error checking feed: {str(e)}\nTraceback: {traceback.format_exc()}"
            logging.error(error_msg)
            # Try to notify in Discord if possible
            try:
                channel = self.bot.get_channel(self.discord_channel_id)
                if channel:
                    await channel.send(f"⚠️ Error checking Instagram feed: {str(e)}")
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
    instagram_monitor = InstagramMonitor(bot)
    await bot.add_cog(instagram_monitor)
    
    # Send initial post after cog is added
    await instagram_monitor.send_latest_post()
    
    try:
        # Sync commands globally
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
        
        # Log all registered commands
        for command in bot.tree.get_commands():
            logging.info(f"Registered command: {command.name}")
    except Exception as e:
        logging.error(f"Failed to sync commands: {str(e)}\nTraceback: {traceback.format_exc()}")

@bot.tree.command(name="statusflodown", description="Check the bot's status and last Instagram check")
async def status(interaction: discord.Interaction):
    """Check the bot's status"""
    try:
        # Get the InstagramMonitor cog
        instagram_cog = bot.get_cog('InstagramMonitor')
        last_check = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        embed = discord.Embed(
            title="Bot Status",
            description="Instagram Monitor Bot is running",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Last Check", value=last_check)
        embed.add_field(name="RSS URL", value=instagram_cog.rss_url if instagram_cog else "Not initialized")
        embed.add_field(name="Channel ID", value=instagram_cog.discord_channel_id if instagram_cog else "Not initialized")
        embed.add_field(name="Last Post ID", value=instagram_cog.last_entry_id if instagram_cog else "Not initialized")
        
        await interaction.response.send_message(embed=embed)
        logging.info(f"statusflodown command used by {interaction.user.name}")
    except Exception as e:
        error_msg = f"Error in statusflodown command: {str(e)}\nTraceback: {traceback.format_exc()}"
        logging.error(error_msg)
        await interaction.response.send_message("❌ An error occurred while checking the status.", ephemeral=True)

@bot.tree.command(name="inviteflodown", description="Get the bot's invite link with proper permissions")
async def invite(interaction: discord.Interaction):
    """Get the bot's invite link"""
    try:
        # Calculate permissions integer
        permissions = discord.Permissions(
            send_messages=True,
            embed_links=True,
            view_channel=True,
            read_message_history=True
        )
        
        # Generate invite link
        invite_url = discord.utils.oauth_url(
            bot.user.id,
            permissions=permissions,
            scopes=('bot', 'applications.commands')
        )
        
        embed = discord.Embed(
            title="Bot Invite Link",
            description="Click the link below to invite the bot with proper permissions:",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Invite Link", value=f"[Click here to invite]({invite_url})")
        embed.add_field(name="Required Permissions", value="• Send Messages\n• Embed Links\n• View Channel\n• Read Message History")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        logging.info(f"Invite link generated for {interaction.user.name}")
    except Exception as e:
        error_msg = f"Error generating invite link: {str(e)}\nTraceback: {traceback.format_exc()}"
        logging.error(error_msg)
        await interaction.response.send_message("❌ An error occurred while generating the invite link.", ephemeral=True)

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))