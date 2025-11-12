import discord
from discord.ext import commands
import asyncio
import os
import json
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DiscordBot')

# Bot Token from environment variable
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    raise ValueError("❌ No DISCORD_TOKEN found! Set it in Railway environment variables.")

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True

# Simple prefix function - this is likely line 22 area
def get_prefix(bot, message):
    return ["!", "?"]

bot = commands.Bot(
    command_prefix=get_prefix,
    intents=intents,
    help_command=None
)

@bot.event
async def on_ready():
    logger.info(f'✅ {bot.user.name} is online!')
    logger.info(f'📊 Connected to {len(bot.guilds)} servers')
    logger.info(f'🎵 Use !help or ?help for commands')
    
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="!help or ?help"
            )
        )
    except Exception as e:
        logger.warning(f"Could not set presence: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if bot.user.mentioned_in(message) and message.mention_everyone is False:
        logger.info(f'Mentioned by {message.author} in {message.guild.name}')
    
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    else:
        logger.error(f'Error: {error}')
        await ctx.send(f"❌ Error: {str(error)}")

async def load_cogs():
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
    except Exception as e:
        logger.error(f'❌ Fatal error: {e}')