import discord
from discord.ext import commands
import asyncio
import yt_dlp
from collections import deque
import logging
import re

logger = logging.getLogger('MusicCog')

# Enhanced yt-dlp options for SoundCloud + YouTube
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'force-ipv4': True,
    'prefer_ffmpeg': True,
    'keepvideo': False,
    'extract_flat': False,
    'skip_download': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 128k'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class Song:
    def __init__(self, url, title, duration, thumbnail, requester, source='Unknown'):
        self.url = url
        self.title = title
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester
        self.source = source

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
                
                # Re-extract to get fresh stream URL
                data = await loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(self.current.url, download=False)
                )
                
                if 'entries' in data:
                    data = data['entries'][0]
                
                # Get audio URL
                audio_url = data.get('url')
                
                if not audio_url:
                    logger.error("No audio URL found")
                    await self.text_channel.send("❌ Could not get audio stream URL")
                    continue
                
                source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)
                
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
                    
                    embed.add_field(name="Source", value=self.current.source, inline=True)
                    
                    if self.current.duration:
                        mins, secs = divmod(self.current.duration, 60)
                        embed.add_field(name="Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)
                    
                    embed.add_field(name="Requested by", value=self.current.requester.mention, inline=True)
                    
                    if self.current.thumbnail:
                        embed.set_thumbnail(url=self.current.thumbnail)
                    
                    await self.text_channel.send(embed=embed)
                    await self.next_event.wait()
                    
            except Exception as e:
                logger.error(f'Player error: {e}')
                await self.text_channel.send(f'❌ Error playing song: {str(e)}')
                await asyncio.sleep(2)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
    
    def get_player(self, ctx):
        if ctx.guild.id not in self.players:
            self.players[ctx.guild.id] = MusicPlayer(ctx)
        return self.players[ctx.guild.id]
    
    def detect_platform(self, url_or_query):
        """Detect if query is YouTube, SoundCloud, or search term"""
        url_or_query_lower = url_or_query.lower()
        
        if 'soundcloud.com' in url_or_query_lower or 'snd.sc' in url_or_query_lower:
            return 'SoundCloud'
        elif 'youtube.com' in url_or_query_lower or 'youtu.be' in url_or_query_lower:
            return 'YouTube'
        elif url_or_query.startswith('http'):
            return 'URL'
        else:
            return 'Search'
    
    async def extract_info(self, query):
        """Extract song info from YouTube or SoundCloud"""
        loop = self.bot.loop or asyncio.get_event_loop()
        
        try:
            # Check if it's a direct URL
            if query.startswith('http'):
                data = await loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(query, download=False)
                )
            else:
                # Search YouTube by default
                data = await loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(f"ytsearch:{query}", download=False)
                )
            
            if 'entries' in data:
                # Take first result
                data = data['entries'][0]
            
            return data
            
        except Exception as e:
            logger.error(f'Extract error: {e}')
            return None
    
    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Play music from YouTube or SoundCloud
        
        Usage: 
        !play <song name>
        !play <youtube url>
        !play <soundcloud url>
        """
        
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel!")
            return
        
        platform = self.detect_platform(query)
        
        # Show searching message
        if platform == 'SoundCloud':
            msg = await ctx.send(f"🔍 Loading from **SoundCloud**: `{query}`...")
        elif platform == 'YouTube':
            msg = await ctx.send(f"🔍 Loading from **YouTube**: `{query}`...")
        else:
            msg = await ctx.send(f"🔍 Searching YouTube for: `{query}`...")
        
        # Extract song info
        data = await self.extract_info(query)
        
        if not data:
            await msg.edit(content="❌ Could not find any results! Try a different search.")
            return
        
        # Determine actual source from URL
        webpage_url = data.get('webpage_url', '')
        if 'soundcloud' in webpage_url.lower():
            actual_source = '🎵 SoundCloud'
        elif 'youtube' in webpage_url.lower():
            actual_source = '📺 YouTube'
        else:
            actual_source = '🎵 Unknown'
        
        # Create song object
        song = Song(
            url=webpage_url or data.get('url'),
            title=data.get('title', 'Unknown Title'),
            duration=data.get('duration'),
            thumbnail=data.get('thumbnail'),
            requester=ctx.author,
            source=actual_source
        )
        
        # Get player
        player = self.get_player(ctx)
        
        # Connect to voice if not connected
        if not player.voice_client or not player.voice_client.is_connected():
            try:
                player.voice_client = await ctx.author.voice.channel.connect()
                await ctx.send(f"🔊 Connected to **{ctx.author.voice.channel.name}**")
            except Exception as e:
                await msg.edit(content=f"❌ Could not connect to voice: {str(e)}")
                return
        
        # Add to queue
        player.queue.append(song)
        
        # Send confirmation embed
        embed = discord.Embed(
            title="✅ Added to Queue",
            description=f"**{song.title}**",
            color=discord.Color.green()
        )
        
        embed.add_field(name="Source", value=song.source, inline=True)
        embed.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
        
        if song.duration:
            mins, secs = divmod(song.duration, 60)
            embed.add_field(name="Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)
        
        embed.add_field(name="Requested by", value=ctx.author.mention, inline=False)
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        
        await msg.edit(content=None, embed=embed)
        logger.info(f'Queued ({song.source}): {song.title} in {ctx.guild.name}')
    
    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pause the current song"""
        player = self.get_player(ctx)
        
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            await ctx.send("⏸️ Paused!")
        else:
            await ctx.send("❌ Nothing is playing!")
    
    @commands.command(name='resume')
    async def resume(self, ctx):
        """Resume the paused song"""
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
        """Stop music and disconnect"""
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
        """Show the music queue"""
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
                value=f"**{player.current.title}**\n{player.current.source}",
                inline=False
            )
        
        if player.queue:
            queue_list = []
            for i, song in enumerate(list(player.queue)[:10], 1):
                queue_list.append(f"`{i}.` **{song.title}** ({song.source})")
            
            embed.add_field(
                name=f"Up Next ({len(player.queue)} songs)",
                value="\n".join(queue_list),
                inline=False
            )
            
            if len(player.queue) > 10:
                embed.set_footer(text=f"And {len(player.queue) - 10} more...")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='np', aliases=['nowplaying'])
    async def nowplaying(self, ctx):
        """Show the currently playing song"""
        player = self.get_player(ctx)
        
        if not player.current:
            await ctx.send("❌ Nothing is playing!")
            return
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{player.current.title}**",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Source", value=player.current.source, inline=True)
        
        if player.current.duration:
            mins, secs = divmod(player.current.duration, 60)
            embed.add_field(name="Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)
        
        embed.add_field(name="Requested by", value=player.current.requester.mention, inline=True)
        
        if player.current.thumbnail:
            embed.set_thumbnail(url=player.current.thumbnail)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot))