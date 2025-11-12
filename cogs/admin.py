import discord
from discord.ext import commands
import json
import logging

logger = logging.getLogger('AdminCog')

PREFIX_FILE = 'prefixes.json'

def load_prefixes():
    """Load prefixes from JSON file"""
    try:
        with open(PREFIX_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_prefixes(prefixes):
    """Save prefixes to JSON file"""
    with open(PREFIX_FILE, 'w') as f:
        json.dump(prefixes, f, indent=4)

class Admin(commands.Cog):
    """Admin and configuration commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.prefixes = load_prefixes()
    
    @commands.command(name='setprefix')
    @commands.has_permissions(administrator=True)
    async def setprefix(self, ctx, new_prefix: str):
        """Set a custom prefix for this server (Admin only)"""
        if len(new_prefix) > 5:
            await ctx.send("❌ Prefix must be 5 characters or less!")
            return
        
        guild_id = str(ctx.guild.id)
        self.prefixes[guild_id] = new_prefix
        save_prefixes(self.prefixes)
        
        # Update the bot's prefix cache
        from bot import prefixes as bot_prefixes
        bot_prefixes[guild_id] = new_prefix
        
        embed = discord.Embed(
            title="✅ Prefix Updated",
            description=f"The new prefix for this server is: `{new_prefix}`",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Example",
            value=f"Try: `{new_prefix}help`",
            inline=False
        )
        
        await ctx.send(embed=embed)
        logger.info(f'Prefix changed to "{new_prefix}" in {ctx.guild.name}')
    
    @setprefix.error
    async def setprefix_error(self, ctx, error):
        """Error handler for setprefix command"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need Administrator permissions to change the prefix!")
        elif isinstance(error, commands.MissingRequiredArgument):
            current_prefix = self.prefixes.get(str(ctx.guild.id), '!')
            await ctx.send(f"❌ Please provide a new prefix! Current prefix: `{current_prefix}`")
    
    @commands.command(name='prefix')
    async def prefix(self, ctx):
        """Show the current server prefix"""
        guild_id = str(ctx.guild.id)
        current_prefix = self.prefixes.get(guild_id, '!')
        
        embed = discord.Embed(
            title="📝 Server Prefix",
            description=f"The current prefix for this server is: `{current_prefix}`",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Change Prefix",
            value=f"Admins can use: `{current_prefix}setprefix <new_prefix>`",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='clear', aliases=['purge'])
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 10):
        """Clear a specified number of messages (Manage Messages permission required)"""
        if amount < 1 or amount > 100:
            await ctx.send("❌ Please specify a number between 1 and 100!")
            return
        
        deleted = await ctx.channel.purge(limit=amount + 1)  # +1 to include command message
        
        confirmation = await ctx.send(f"✅ Deleted {len(deleted) - 1} messages!")
        await confirmation.delete(delay=3)
        
        logger.info(f'Cleared {len(deleted) - 1} messages in {ctx.guild.name}')
    
    @clear.error
    async def clear_error(self, ctx, error):
        """Error handler for clear command"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need Manage Messages permission to use this command!")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Please provide a valid number!")

async def setup(bot):
    """Setup function for loading the cog"""
    await bot.add_cog(Admin(bot))