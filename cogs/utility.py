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
        await ctx.send(f"🏓 Pong! Latency: **{latency}ms**")
    
    @commands.command(name='help')
    async def help(self, ctx):
        """Show all commands"""
        embed = discord.Embed(
            title="🎵 Music Bot Commands",
            description=f"Mention me or use `!` or `?` prefix",
            color=discord.Color.blue()
        )
        
        music = [
            "`!play <song>` - Play a song",
            "`!pause` - Pause music",
            "`!resume` - Resume music",
            "`!skip` - Skip current song",
            "`!stop` - Stop and disconnect",
            "`!queue` - Show queue",
            "`!np` - Now playing"
        ]
        
        utility = [
            "`!ping` - Check latency",
            "`!help` - Show this message",
            "`!info` - Bot info"
        ]
        
        embed.add_field(name="🎵 Music", value="\n".join(music), inline=False)
        embed.add_field(name="🔧 Utility", value="\n".join(utility), inline=False)
        
        bot_name = self.bot.user.name if self.bot.user else "Bot"
        embed.set_footer(text=f"You can also mention me to use commands!")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='info')
    async def info(self, ctx):
        """Bot information"""
        embed = discord.Embed(
            title="🎵 Music Bot",
            description="A simple Discord music bot",
            color=discord.Color.blue()
        )
        
        stats_text = f"Servers: {len(self.bot.guilds)}\nUsers: {len(self.bot.users)}\nLatency: {round(self.bot.latency * 1000, 2)}ms"
        
        embed.add_field(
            name="📊 Stats",
            value=stats_text,
            inline=False
        )
        
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))