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

# Bot setup
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix='!', intents=intents)

class InstagramMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_entry_id = None
        self.rss_url = os.getenv('INSTAGRAM_RSS_URL')
        self.discord_channel_id = int(os.getenv('DISCORD_CHANNEL_ID'))
        self.check_feed.start()
        logging.info("Instagram Monitor initialized")

    def cog_unload(self):
        self.check_feed.cancel()

    @tasks.loop(minutes=5)
    async def check_feed(self):
        try:
            feed = feedparser.parse(self.rss_url)
            if feed.entries:
                latest_entry = feed.entries[0]
                
                if self.last_entry_id is None:
                    self.last_entry_id = latest_entry.id
                    logging.info("Initial post ID set")
                elif latest_entry.id != self.last_entry_id:
                    self.last_entry_id = latest_entry.id
                    channel = self.bot.get_channel(self.discord_channel_id)
                    
                    # Create embed for the new post
                    embed = discord.Embed(
                        title="New Instagram Post",
                        description=latest_entry.description,
                        url=latest_entry.link,
                        timestamp=datetime.now()
                    )
                    
                    # Add image if available
                    if 'media_content' in latest_entry:
                        embed.set_image(url=latest_entry.media_content[0]['url'])
                    
                    await channel.send(embed=embed)
                    logging.info(f"New post detected and sent to channel {self.discord_channel_id}")
                    
        except Exception as e:
            error_msg = f"Error checking feed: {str(e)}\nTraceback: {traceback.format_exc()}"
            logging.error(error_msg)
            # Try to notify in Discord if possible
            try:
                channel = self.bot.get_channel(self.discord_channel_id)
                if channel:
                    await channel.send(f"⚠️ Error checking Instagram feed: {str(e)}")
            except:
                logging.error("Failed to send error notification to Discord channel")

    @check_feed.before_loop
    async def before_check_feed(self):
        await self.bot.wait_until_ready()

@bot.event
async def on_ready():
    logging.info(f'Bot is ready: {bot.user.name}')
    await bot.add_cog(InstagramMonitor(bot))
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
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

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))