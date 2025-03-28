import discord
from discord.ext import commands, tasks
import feedparser
import os
from dotenv import load_dotenv
import logging
from datetime import datetime

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
            logging.error(f"Error checking feed: {e}")

    @check_feed.before_loop
    async def before_check_feed(self):
        await self.bot.wait_until_ready()

@bot.event
async def on_ready():
    logging.info(f'Bot is ready: {bot.user.name}')
    await bot.add_cog(InstagramMonitor(bot))

@bot.command(name='status')
async def status(ctx):
    """Check the bot's status"""
    embed = discord.Embed(
        title="Bot Status",
        description="Instagram Monitor Bot is running",
        color=discord.Color.green()
    )
    embed.add_field(name="Last Check", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    await ctx.send(embed=embed)

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))