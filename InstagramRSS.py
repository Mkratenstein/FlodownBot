import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
import traceback
from instagram_monitor import InstagramMonitor
from BlueSkyRSS import BlueSkyMonitor

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
required_vars = ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'INSTAGRAM_RSS_URL', 'APPLICATION_ID', 'ALLOWED_ROLE_IDS']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Parse allowed role IDs
ALLOWED_ROLE_IDS = [int(role_id.strip()) for role_id in os.getenv('ALLOWED_ROLE_IDS').split(',')]
logging.info(f"Allowed role IDs: {ALLOWED_ROLE_IDS}")

logging.info("Environment variables loaded successfully")
logging.info(f"Channel ID: {os.getenv('DISCORD_CHANNEL_ID')}")
logging.info(f"RSS URL: {os.getenv('INSTAGRAM_RSS_URL')}")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix='!', intents=intents, application_id=os.getenv('APPLICATION_ID'))

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
            
        return has_role
    return app_commands.check(predicate)

class InstagramMonitorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logging.info("Initializing Instagram Monitor Cog...")
        self.instagram_monitor = InstagramMonitor()
        self.bluesky_monitor = BlueSkyMonitor()
        self.check_feed.start()
        self.last_check = None
        logging.info("Instagram Monitor Cog initialized successfully")
        
    def cog_unload(self):
        logging.info("Unloading Instagram Monitor Cog...")
        self.check_feed.cancel()
        logging.info("Instagram Monitor Cog unloaded")
        
    @tasks.loop(minutes=5)
    async def check_feed(self):
        """Check for new Instagram posts every 5 minutes"""
        try:
            self.last_check = datetime.now()
            logging.info("Checking for new Instagram posts...")
            post = self.instagram_monitor.get_latest_post()
            
            if post:
                logging.info(f"New post found! Post ID: {post['post_id']}")
                channel = self.bot.get_channel(int(os.getenv('DISCORD_CHANNEL_ID')))
                if channel:
                    logging.info(f"Posting to channel: {channel.name} (ID: {channel.id})")
                    embed = discord.Embed(
                        title="Hey! Goose the Organization just posted something on Instagram",
                        description=f"[Instagram]({post['url']})\n\n{post['caption']}",
                        color=discord.Color.blue()
                    )
                    
                    if post['thumbnail_url']:
                        embed.set_image(url=post['thumbnail_url'])
                        
                    await channel.send(embed=embed)
                    logging.info("Post successfully sent to Discord")
                else:
                    logging.error(f"Could not find channel with ID: {os.getenv('DISCORD_CHANNEL_ID')}")
            else:
                logging.info("No new posts found")
                    
        except Exception as e:
            logging.error(f"Error in check_feed: {str(e)}")
            logging.error(traceback.format_exc())
            
    @check_feed.before_loop
    async def before_check_feed(self):
        await self.bot.wait_until_ready()
        
    @app_commands.command(name="testinstagram", description="Test the Instagram monitor by fetching the latest post")
    @has_allowed_role()
    async def test_instagram(self, interaction: discord.Interaction):
        """Test command to fetch the latest Instagram post"""
        await interaction.response.defer()
        
        try:
            post = self.instagram_monitor.get_latest_post()
            
            if post:
                embed = discord.Embed(
                    title="Hey! Goose the Organization just posted something on Instagram",
                    description=f"[Instagram]({post['url']})\n\n{post['caption']}",
                    color=discord.Color.blue()
                )
                
                if post['thumbnail_url']:
                    embed.set_image(url=post['thumbnail_url'])
                    
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("No new posts found.")
                
        except Exception as e:
            logging.error(f"Error in test_instagram: {str(e)}")
            await interaction.followup.send(f"❌ Error: {str(e)}")
            
    @app_commands.command(name="history", description="Show recent Instagram posts")
    @has_allowed_role()
    async def show_history(self, interaction: discord.Interaction, limit: int = 5):
        """Show recent Instagram posts"""
        await interaction.response.defer()
        
        try:
            posts = self.instagram_monitor.get_post_history(limit)
            
            if posts:
                embed = discord.Embed(
                    title=f"Recent Instagram Posts (Last {len(posts)})",
                    color=discord.Color.blue()
                )
                
                for post in posts:
                    embed.add_field(
                        name=f"Post from {post[1]}",
                        value=f"[View Post]({post[5]})\nSource: {post[9]}",
                        inline=False
                    )
                    
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("No posts found in history.")
                
        except Exception as e:
            logging.error(f"Error in show_history: {str(e)}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.event
async def on_ready():
    """Bot is ready and connected to Discord"""
    logging.info(f"Bot is ready! Logged in as {bot.user.name}")
    
    # Add the Instagram monitor cog first
    await bot.add_cog(InstagramMonitorCog(bot))
    
    # Clear existing commands
    bot.tree.clear_commands(guild=None)
    
    # Register all commands from cogs
    for cog in bot.cogs.values():
        for command in cog.get_commands():
            logging.info(f"Registering command from cog {cog.__class__.__name__}: {command.name}")
            bot.tree.add_command(command)
    
    # Sync commands with Discord
    try:
        synced = await bot.tree.sync()
        logging.info(f"Synced {len(synced)} command(s)")
        
        # Log all registered commands
        for command in bot.tree.get_commands():
            logging.info(f"Registered command: {command.name}")
    except Exception as e:
        logging.error(f"Error syncing commands: {str(e)}")
        logging.error(traceback.format_exc())

@bot.tree.command(name="status", description="Check the bot's status and last Instagram check")
@has_allowed_role()
async def status(interaction: discord.Interaction):
    """Check the bot's status"""
    cog = bot.get_cog('InstagramMonitorCog')
    if cog:
        last_check = cog.last_check
        if last_check:
            time_diff = datetime.now() - last_check
            minutes = time_diff.total_seconds() / 60
            status_msg = f"✅ Bot is running\nLast check: {minutes:.1f} minutes ago"
        else:
            status_msg = "✅ Bot is running\nNo checks performed yet"
    else:
        status_msg = "❌ Instagram monitor not initialized"
        
    await interaction.response.send_message(status_msg)

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))