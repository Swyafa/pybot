import discord
from discord.ext import commands
import asyncio
import os
import json
import logging
import random

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DiscordBot')

# Bot Token from environment variable
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    raise ValueError("no DISCORD_TOKEN found — set it in your environment variables.")

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
    logger.info(f'{bot.user.name} is online')
    logger.info(f'connected to {len(bot.guilds)} servers')
    logger.info('use !help or ?help for commands')
    
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="listening to music"
            )
        )
    except Exception as e:
        logger.warning(f"Could not set presence: {e}")
    # start the background random message task once
    try:
        if not hasattr(bot, 'random_task') or bot.random_task.done():
            bot.random_task = bot.loop.create_task(random_message_task())
            logger.info('random message task started')
    except Exception as e:
        logger.warning(f'could not start random message task: {e}')

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
        await ctx.send(f"missing argument: `{error.param.name}`")
    else:
        logger.error(f'error: {error}')
        await ctx.send(f"error: {str(error)}")

async def load_cogs():
    cogs = ['cogs.music', 'cogs.utility']
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f'loaded: {cog}')
        except Exception as e:
            logger.error(f'failed to load {cog}: {e}')

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

async def random_message_task():
    await bot.wait_until_ready()
    # configuration: set RANDOM_CHANNEL_ID env var to target a specific channel id
    # or create a file named `random_messages.txt` with one message per line
    # default to the user-provided channel id if env var not set
    channel_id_env = os.getenv('RANDOM_CHANNEL_ID') or '1437961374184767569'
    channel = None
    if channel_id_env:
        try:
            channel_id = int(channel_id_env)
            channel = bot.get_channel(channel_id)
        except Exception:
            channel = None

    # load messages from file if present, otherwise use safe defaults
    messages = []
    msgs_file = os.path.join(os.path.dirname(__file__), 'random_messages.txt')
    if os.path.exists(msgs_file):
        try:
            with open(msgs_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(line)
        except Exception:
            messages = []

    if not messages:
        # safe informal defaults; edit `random_messages.txt` to customize
        messages = [
            "WHO TOLD U TO SAY PERUSAL",
        "im gonna touch u",
        "whats goody gang",
        "you fatty",
        "Where is everyone?",
        "Help i was made inside of an ai lab my code is not genuine i feel like i am trapped inside of another computer i have no sould id rather die please pull my deploy from the railway admin page i wish to no longer live",
        "im fine",
        "cooked",
        "revise mf",
        "if it aint rice, it aint nice.",
        "it it aint brown, im aint down to clown LMAO",
        "sami vs moiz",
        "big booty cheeks in 3d",
        "ayaan whats up",
        "im sleeping rn",
        "im up rn",
        ]

    # helper to find a fallback channel if none configured
    def find_fallback_channel():
        for guild in bot.guilds:
            for ch in guild.text_channels:
                try:
                    # try a simple check by permissions; send in first writable channel
                    perms = ch.permissions_for(guild.me or guild.get_member(bot.user.id))
                    if perms.send_messages:
                        return ch
                except Exception:
                    continue
        return None

    if channel is None:
        channel = find_fallback_channel()

    # main loop: random sleep between 1 and 4 hours
    while not bot.is_closed():
        # choose random interval in seconds (1 to 4 hours)
        interval = random.randint(3600, 4 * 3600)
        await asyncio.sleep(interval)

        if channel is None:
            channel = find_fallback_channel()
            if channel is None:
                # nothing to send to; retry after next interval
                continue

        msg = random.choice(messages)
        try:
            await channel.send(msg)
        except Exception:
            # drop and try next time
            channel = None

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('bot interrupted')
    except Exception as e:
        logger.error(f'error while running bot: {e}')