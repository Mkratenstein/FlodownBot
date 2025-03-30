import os
from dotenv import load_dotenv
import logging
import discord
from discord.ext import commands

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
for var in ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'INSTAGRAM_RSS_URL', 'BLUESKY_HANDLE', 'BLUESKY_LOGIN_EMAIL', 'BLUESKY_LOGIN_PASSWORD', 'APPLICATION_ID', 'ALLOWED_ROLE_IDS']:
    value = os.getenv(var)
    if value:
        # Mask sensitive values
        if var in ['DISCORD_TOKEN', 'BLUESKY_LOGIN_PASSWORD']:
            value = '********'
        logging.info(f"{var}: {value}")
    else:
        logging.error(f"{var}: Not found")

# Verify environment variables
required_vars = ['DISCORD_TOKEN', 'DISCORD_CHANNEL_ID', 'INSTAGRAM_RSS_URL', 'BLUESKY_HANDLE', 'BLUESKY_LOGIN_EMAIL', 'BLUESKY_LOGIN_PASSWORD', 'APPLICATION_ID', 'ALLOWED_ROLE_IDS']
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logging.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Parse allowed role IDs
ALLOWED_ROLE_IDS = [int(role_id.strip()) for role_id in os.getenv('ALLOWED_ROLE_IDS').split(',')]
logging.info(f"Allowed role IDs: {ALLOWED_ROLE_IDS}")

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
            return False
            
        return True
    return commands.check(predicate) 