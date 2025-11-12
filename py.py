import discord
from discord.ext import commands
import asyncio
import logging
from dotenv import load_dotenv
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DiscordBot')

# Load token from .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

# Use mention as prefix OR "!" as backup
def get_prefix(bot, message):
    """Allow both mention and ! prefix"""
    return commands.when_mentioned_or("!", "?")(bot, message)

bot = commands.Bot(
    command_prefix=get_prefix,
    intents=intents,
    help_command=None
)

@bot.event
async def on_ready():
    """Bot is ready"""
    logger.info(f'✅ {bot.user.name} is online!')
    logger.info(f'📊 Connected to {len(bot.guilds)} servers')
    logger.info(f'🎵 Mention me or use ! or ? prefix')
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="@mention me or use !help"
        )
    )

@bot.event
async def on_message(message):
    """Process messages"""
    if message.author.bot:
        return
    
    # Log when bot is mentioned
    if bot.user.mentioned_in(message) and message.mention_everyone is False:
        logger.info(f'Mentioned by {message.author} in {message.guild.name}')
    
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    """Error handler"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    else:
        logger.error(f'Error: {error}')
        await ctx.send(f"❌ Error: {str(error)}")

async def load_cogs():
    """Load cogs"""
    cogs = ['cogs.music', 'cogs.utility']
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f'✅ Loaded: {cog}')
        except Exception as e:
            logger.error(f'❌ Failed to load {cog}: {e}')

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('👋 Bot stopped')
