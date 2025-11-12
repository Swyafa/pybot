import discord
from discord.ext import commands
import asyncio
import yt_dlp
from collections import deque
import logging

logger = logging.getLogger('MusicCog')

# yt-dlp options
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class Song:
    def __init__(self, url, title, duration, thumbnail, requester):
        self.url = url
        self.title = title
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester

class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.text_channel = ctx.channel
        self.queue = deque()
        self.current = None
        self.voice_client = None
        self.next_event = asyncio.Event()
        
        self.bot.loop.create_task(self.player_loop())
    
    async def player_loop(self):
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            self.next_event.clear()
            
            if not self.queue:
                await asyncio.sleep(1)
                continue
            
            try:
                self.current = self.queue.popleft()
                
                loop = self.bot.loop or asyncio.get_event_loop()
                data = await loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(self.current.url, download=False)
                )
                
                if 'entries' in data:
                    data = data['entries'][0]
                
                source = discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS)
                
                if self.voice_client and self.voice_client.is_connected():
                    self.voice_client.play(
                        source,
                        after=lambda e: self.bot.loop.call_soon_threadsafe(self.next_event.set)
                    )
                    
                    # Send now playing message
                    embed = discord.Embed(
                        title="🎵 Now Playing",
                        description=f"**{self.current.title}**",
                        color=discord.Color.blue()
                    )
                    
                    if self.current.duration:
                        mins, secs = divmod(self.current.duration, 60)
                        embed.add_field(name="Duration", value=f"{int(mins)}:{int(secs):02d}")
                    
                    embed.add_field(name="Requested by", value=self.current.requester.mention)
                    
                    if self.current.thumbnail:
                        embed.set_thumbnail(url=self.current.thumbnail)
                    
                    await self.text_channel.send(embed=embed)
                    await self.next_event.wait()
                    
            except Exception as e:
                logger.error(f'Player error: {e}')
                await self.text_channel.send(f'❌ Error playing: {str(e)}')
                await asyncio.sleep(1)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
    
    def get_player(self, ctx):
        if ctx.guild.id not in self.players:
            self.players[ctx.guild.id] = MusicPlayer(ctx)
        return self.players[ctx.guild.id]
    
    async def extract_info(self, query):
        loop = self.bot.loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(f"ytsearch:{query}", download=False)
            )
            if 'entries' in data:
                data = data['entries'][0]
            return data
        except Exception as e:
            logger.error(f'Search error: {e}')
            return None
    
    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Play a song - Usage: !play song name OR @bot play song name"""
        
        # Check voice channel
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel!")
            return
        
        # Send searching message
        msg = await ctx.send(f"🔍 Searching for: `{query}`...")
        
        # Search for song
        data = await self.extract_info(query)
        
        if not data:
            await msg.edit(content="❌ Could not find any results!")
            return
        
        # Create song
        song = Song(
            url=data.get('webpage_url') or data.get('url'),
            title=data.get('title', 'Unknown'),
            duration=data.get('duration'),
            thumbnail=data.get('thumbnail'),
            requester=ctx.author
        )
        
        # Get player
        player = self.get_player(ctx)
        
        # Connect to voice
        if not player.voice_client or not player.voice_client.is_connected():
            try:
                player.voice_client = await ctx.author.voice.channel.connect()
                await ctx.send(f"🔊 Connected to **{ctx.author.voice.channel.name}**")
            except Exception as e:
                await msg.edit(content=f"❌ Could not connect: {str(e)}")
                return
        
        # Add to queue
        player.queue.append(song)
        
        # Send confirmation
        embed = discord.Embed(
            title="✅ Added to Queue",
            description=f"**{song.title}**",
            color=discord.Color.green()
        )
        embed.add_field(name="Position", value=f"#{len(player.queue)}")
        embed.add_field(name="Requested by", value=ctx.author.mention)
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        
        await msg.edit(content=None, embed=embed)
        logger.info(f'Queued: {song.title}')
    
    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pause the music"""
        player = self.get_player(ctx)
        
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            await ctx.send("⏸️ Paused!")
        else:
            await ctx.send("❌ Nothing is playing!")
    
    @commands.command(name='resume')
    async def resume(self, ctx):
        """Resume the music"""
        player = self.get_player(ctx)
        
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
            await ctx.send("▶️ Resumed!")
        else:
            await ctx.send("❌ Music is not paused!")
    
    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        """Skip the current song"""
        player = self.get_player(ctx)
        
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
            await ctx.send("⏭️ Skipped!")
        else:
            await ctx.send("❌ Nothing is playing!")
    
    @commands.command(name='stop')
    async def stop(self, ctx):
        """Stop and disconnect"""
        player = self.get_player(ctx)
        
        if player.voice_client:
            player.queue.clear()
            player.voice_client.stop()
            await player.voice_client.disconnect()
            await ctx.send("⏹️ Stopped and disconnected!")
        else:
            await ctx.send("❌ Not connected!")
    
    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx):
        """Show the queue"""
        player = self.get_player(ctx)
        
        if not player.queue and not player.current:
            await ctx.send("❌ Queue is empty!")
            return
        
        embed = discord.Embed(
            title="🎵 Music Queue",
            color=discord.Color.blue()
        )
        
        if player.current:
            embed.add_field(
                name="Now Playing",
                value=f"**{player.current.title}**",
                inline=False
            )
        
        if player.queue:
            queue_list = []
            for i, song in enumerate(list(player.queue)[:10], 1):
                queue_list.append(f"`{i}.` {song.title}")
            
            embed.add_field(
                name=f"Up Next ({len(player.queue)} songs)",
                value="\n".join(queue_list),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='np', aliases=['nowplaying'])
    async def nowplaying(self, ctx):
        """Show current song"""
        player = self.get_player(ctx)
        
        if not player.current:
            await ctx.send("❌ Nothing playing!")
            return
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{player.current.title}**",
            color=discord.Color.blue()
        )
        
        if player.current.duration:
            mins, secs = divmod(player.current.duration, 60)
            embed.add_field(name="Duration", value=f"{int(mins)}:{int(secs):02d}")
        
        embed.add_field(name="Requested by", value=player.current.requester.mention)
        
        if player.current.thumbnail:
            embed.set_thumbnail(url=player.current.thumbnail)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot))