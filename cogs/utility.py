import discord
from discord.ext import commands
import time

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='ping')
    async def ping(self, ctx):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000, 2)
        await ctx.send(f"pong — latency: {latency}ms")
    
    @commands.command(name='help')
    async def help(self, ctx):
        """Show all commands"""
        embed = discord.Embed(
            title="music bot commands",
            description=f"mention me or use `!` or `?` prefix",
            color=discord.Color.purple()
        )
        
        music = [
            "`!play <song>` - play a song",
            "`!pause` - pause music",
            "`!resume` - resume music",
            "`!skip` - skip current song",
            "`!stop` - stop and disconnect",
            "`!queue` - show queue",
            "`!np` - now playing"
        ]
        
        utility = [
            "`!ping` - check latency",
            "`!help` - show this message",
            "`!info` - bot info"
        ]
        
        embed.add_field(name="music", value="\n".join(music), inline=False)
        embed.add_field(name="utility", value="\n".join(utility), inline=False)
        
        bot_name = self.bot.user.name if self.bot.user else "Bot"
        embed.set_footer(text=f"you can also mention me to use commands")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='info')
    async def info(self, ctx):
        """Bot information"""
        embed = discord.Embed(
            title="music bot",
            description="a simple discord music bot",
            color=discord.Color.purple()
        )
        
        stats_text = f"Servers: {len(self.bot.guilds)}\nUsers: {len(self.bot.users)}\nLatency: {round(self.bot.latency * 1000, 2)}ms"
        
        embed.add_field(
            name="stats",
            value=stats_text,
            inline=False
        )
        
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))