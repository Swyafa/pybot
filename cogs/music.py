import discord
from discord.ext import commands
import asyncio
import yt_dlp
from collections import deque
import logging
import functools
import os

logger = logging.getLogger('MusicCog')

# Check if cookies file exists
COOKIES_FILE = 'cookies.txt'
HAS_COOKIES = os.path.exists(COOKIES_FILE)

if HAS_COOKIES:
    logger.info("✅ YouTube cookies found - YouTube should work!")
else:
    logger.warning("⚠️ No cookies.txt found - YouTube may be blocked. Use SoundCloud or add cookies.")

# Enhanced yt-dlp options with cookies
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': 'downloads/%(extractor)s-%(id)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,  # Changed to False to support playlists
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'force-ipv4': True,
    'geo_bypass': True,
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'referer': 'https://www.youtube.com/',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
        'Sec-Fetch-Mode': 'navigate',
    },
    'extractor_retries': 5,
    'fragment_retries': 5,
    'skip_unavailable_fragments': True,
    'keepvideo': False,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '128',
    }],
}

# Add cookies if available
if HAS_COOKIES:
    YTDL_OPTIONS['cookiefile'] = COOKIES_FILE

# Simple FFmpeg options
FFMPEG_OPTIONS = {
    'options': '-vn'
}

def get_ytdl():
    """Get a fresh YTDL instance"""
    os.makedirs('downloads', exist_ok=True)
    return yt_dlp.YoutubeDL(YTDL_OPTIONS)

class Song:
    def __init__(self, url, title, duration, thumbnail, requester, source='Unknown', filepath=None):
        self.url = url
        self.title = title
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester
        self.source = source
        self.filepath = filepath

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
                
                ytdl = get_ytdl()
                
                logger.info(f"Downloading: {self.current.title}")
                
                data = await loop.run_in_executor(
                    None,
                    functools.partial(ytdl.extract_info, self.current.url, download=True)
                )
                
                if not data:
                    await self.text_channel.send(f"❌ Could not download: {self.current.title}")
                    continue
                
                if 'entries' in data:
                    data = data['entries'][0]
                
                filename = ytdl.prepare_filename(data)
                
                audio_file = None
                base_name = os.path.splitext(filename)[0]
                
                for ext in ['.opus', '.mp3', '.m4a', '.webm', '.ogg']:
                    potential_file = base_name + ext
                    if os.path.exists(potential_file):
                        audio_file = potential_file
                        break
                
                if not audio_file:
                    audio_file = filename
                
                if not os.path.exists(audio_file):
                    logger.error(f"Audio file not found: {audio_file}")
                    await self.text_channel.send(f"❌ Could not find audio file for: {self.current.title}")
                    continue
                
                logger.info(f"Playing file: {audio_file}")
                
                source = discord.FFmpegPCMAudio(audio_file, **FFMPEG_OPTIONS)
                
                if self.voice_client and self.voice_client.is_connected():
                    def after_playing(error):
                        try:
                            if os.path.exists(audio_file):
                                os.remove(audio_file)
                                logger.info(f"Cleaned up: {audio_file}")
                        except Exception as e:
                            logger.error(f"Could not delete file: {e}")
                        
                        self.bot.loop.call_soon_threadsafe(self.next_event.set)
                    
                    self.voice_client.play(source, after=after_playing)
                    
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
                await self.text_channel.send(f'❌ Error playing song. Skipping...')
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
        elif 'spotify.com' in url_or_query_lower:
            return 'Spotify'
        elif url_or_query.startswith('http'):
            return 'URL'
        else:
            return 'Search'
    
    def is_playlist(self, url):
        """Check if URL is a playlist"""
        return 'playlist' in url.lower() or 'list=' in url or '/sets/' in url
    
    async def extract_info(self, query, prefer_soundcloud=False, allow_playlist=False):
        """Extract song info from various sources"""
        loop = self.bot.loop or asyncio.get_event_loop()
        
        try:
            ytdl_opts = YTDL_OPTIONS.copy()
            ytdl_opts['noplaylist'] = not allow_playlist
            
            ytdl = yt_dlp.YoutubeDL(ytdl_opts)
            
            if query.startswith('http'):
                data = await loop.run_in_executor(
                    None,
                    functools.partial(ytdl.extract_info, query, download=False)
                )
            else:
                if prefer_soundcloud:
                    search_query = f"scsearch:{query}"
                else:
                    search_query = f"ytsearch:{query}"
                
                data = await loop.run_in_executor(
                    None,
                    functools.partial(ytdl.extract_info, search_query, download=False)
                )
            
            return data
            
        except Exception as e:
            logger.error(f'Extract error: {e}')
            return None
    
    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Play a song or playlist
        
        Usage: 
        !play <song name>
        !play <youtube url>
        !play <soundcloud url>
        !play <youtube playlist url>
        """
        
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel!")
            return
        
        platform = self.detect_platform(query)
        is_playlist = self.is_playlist(query)
        
        if platform == 'Spotify':
            await ctx.send("❌ Spotify links are not supported. Try searching the song name instead!")
            return
        
        if is_playlist:
            msg = await ctx.send(f"📋 Loading playlist from **{platform}**... This may take a moment.")
        else:
            if platform == 'SoundCloud':
                msg = await ctx.send(f"🔍 Loading from **SoundCloud**...")
            elif platform == 'YouTube':
                if not HAS_COOKIES:
                    await ctx.send("⚠️ YouTube may be blocked. Consider using SoundCloud or adding cookies.txt")
                msg = await ctx.send(f"🔍 Loading from **YouTube**...")
            else:
                msg = await ctx.send(f"🔍 Searching for: `{query[:50]}...`")
        
        data = await self.extract_info(query, allow_playlist=is_playlist)
        
        if not data:
            error_msg = "❌ Could not find any results!"
            if platform == 'YouTube' and not HAS_COOKIES:
                error_msg += "\n\n**YouTube is blocking requests.** Solutions:\n• Use SoundCloud: `!sc <song>`\n• Add cookies.txt file\n• Use SoundCloud links instead"
            await msg.edit(content=error_msg)
            return
        
        player = self.get_player(ctx)
        
        if not player.voice_client or not player.voice_client.is_connected():
            try:
                player.voice_client = await ctx.author.voice.channel.connect()
                await ctx.send(f"🔊 Connected to **{ctx.author.voice.channel.name}**")
            except Exception as e:
                await msg.edit(content=f"❌ Could not connect to voice: {str(e)}")
                return
        
        # Handle playlist
        if 'entries' in data and is_playlist:
            entries = data['entries']
            added_count = 0
            
            for entry in entries[:50]:  # Limit to 50 songs
                if not entry:
                    continue
                
                webpage_url = entry.get('webpage_url', '')
                if 'soundcloud' in webpage_url.lower():
                    source = '🎵 SoundCloud'
                elif 'youtube' in webpage_url.lower():
                    source = '📺 YouTube'
                else:
                    source = '🎵 Audio'
                
                song = Song(
                    url=webpage_url or entry.get('url'),
                    title=entry.get('title', 'Unknown'),
                    duration=entry.get('duration'),
                    thumbnail=entry.get('thumbnail'),
                    requester=ctx.author,
                    source=source
                )
                
                player.queue.append(song)
                added_count += 1
            
            embed = discord.Embed(
                title="📋 Playlist Added",
                description=f"Added **{added_count}** songs to queue",
                color=discord.Color.green()
            )
            embed.add_field(name="Requested by", value=ctx.author.mention)
            await msg.edit(content=None, embed=embed)
            logger.info(f'Added playlist: {added_count} songs')
        
        # Handle single song
        else:
            if 'entries' in data:
                data = data['entries'][0]
            
            webpage_url = data.get('webpage_url', '')
            if 'soundcloud' in webpage_url.lower():
                actual_source = '🎵 SoundCloud'
            elif 'youtube' in webpage_url.lower():
                actual_source = '📺 YouTube'
            else:
                actual_source = '🎵 Audio'
            
            song = Song(
                url=webpage_url or data.get('url'),
                title=data.get('title', 'Unknown Title'),
                duration=data.get('duration'),
                thumbnail=data.get('thumbnail'),
                requester=ctx.author,
                source=actual_source
            )
            
            player.queue.append(song)
            
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
            logger.info(f'Queued ({song.source}): {song.title}')
    
    @commands.command(name='playlist', aliases=['pl'])
    async def playlist(self, ctx, *, url: str):
        """Load an entire playlist
        
        Usage: !playlist <playlist url>
        """
        
        if not self.is_playlist(url):
            await ctx.send("❌ This doesn't look like a playlist URL!")
            return
        
        await self.play(ctx, query=url)
    
    @commands.command(name='sc', aliases=['soundcloud'])
    async def soundcloud(self, ctx, *, query: str):
        """Search and play from SoundCloud only
        
        Usage: !sc <song name or url>
        """
        
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel!")
            return
        
        is_playlist = self.is_playlist(query)
        
        if is_playlist:
            msg = await ctx.send(f"📋 Loading SoundCloud playlist...")
        else:
            msg = await ctx.send(f"🔍 Searching SoundCloud for: `{query[:50]}...`")
        
        if not query.startswith('http'):
            query = f"scsearch:{query}"
        
        data = await self.extract_info(query, prefer_soundcloud=True, allow_playlist=is_playlist)
        
        if not data:
            await msg.edit(content="❌ Could not find any SoundCloud results!")
            return
        
        player = self.get_player(ctx)
        
        if not player.voice_client or not player.voice_client.is_connected():
            try:
                player.voice_client = await ctx.author.voice.channel.connect()
            except Exception as e:
                await msg.edit(content=f"❌ Could not connect: {str(e)}")
                return
        
        # Handle playlist
        if 'entries' in data and is_playlist:
            entries = data['entries']
            added_count = 0
            
            for entry in entries[:50]:
                if not entry:
                    continue
                
                song = Song(
                    url=entry.get('webpage_url') or entry.get('url'),
                    title=entry.get('title', 'Unknown'),
                    duration=entry.get('duration'),
                    thumbnail=entry.get('thumbnail'),
                    requester=ctx.author,
                    source='🎵 SoundCloud'
                )
                
                player.queue.append(song)
                added_count += 1
            
            embed = discord.Embed(
                title="📋 SoundCloud Playlist Added",
                description=f"Added **{added_count}** songs to queue",
                color=discord.Color.green()
            )
            embed.add_field(name="Requested by", value=ctx.author.mention)
            await msg.edit(content=None, embed=embed)
        
        # Handle single song
        else:
            if 'entries' in data:
                data = data['entries'][0]
            
            song = Song(
                url=data.get('webpage_url') or data.get('url'),
                title=data.get('title', 'Unknown'),
                duration=data.get('duration'),
                thumbnail=data.get('thumbnail'),
                requester=ctx.author,
                source='🎵 SoundCloud'
            )
            
            player.queue.append(song)
            
            embed = discord.Embed(
                title="✅ Added to Queue",
                description=f"**{song.title}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Source", value="🎵 SoundCloud", inline=True)
            embed.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
            
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            
            await msg.edit(content=None, embed=embed)
    
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
            
            try:
                if os.path.exists('downloads'):
                    for file in os.listdir('downloads'):
                        file_path = os.path.join('downloads', file)
                        os.remove(file_path)
            except Exception as e:
                logger.error(f"Could not clean downloads: {e}")
            
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
                queue_list.append(f"`{i}.` **{song.title}**")
            
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