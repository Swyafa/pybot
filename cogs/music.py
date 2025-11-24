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
    logger.info("youtube cookies found - youtube should work")
else:
    logger.warning("no cookies.txt found - youtube may be blocked. use soundcloud or add cookies")

# Enhanced yt-dlp options with cookies
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': 'downloads/%(extractor)s-%(id)s.%(ext)s',
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
        
        # Loop settings
        self.loop_song = False  # Loop current song
        self.loop_queue = False  # Loop entire queue
        
        self.bot.loop.create_task(self.player_loop())
    
    async def player_loop(self):
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            self.next_event.clear()
            
            # If looping song and we have a current song, re-add it
            if self.loop_song and self.current:
                self.queue.appendleft(self.current)
            
            if not self.queue:
                await asyncio.sleep(1)
                continue
            
            try:
                self.current = self.queue.popleft()
                
                # If loop queue is enabled, add song back to end of queue
                if self.loop_queue:
                    self.queue.append(self.current)
                
                loop = self.bot.loop or asyncio.get_event_loop()
                
                ytdl = get_ytdl()
                
                logger.info(f"Downloading: {self.current.title}")
                
                data = await loop.run_in_executor(
                    None,
                    functools.partial(ytdl.extract_info, self.current.url, download=True)
                )
                
                if not data:
                    await self.text_channel.send(f"could not download: {self.current.title}")
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
                    logger.error(f"audio file not found: {audio_file}")
                    await self.text_channel.send(f"could not find audio file for: {self.current.title}")
                    continue
                
                logger.info(f"Playing file: {audio_file}")
                
                source = discord.FFmpegPCMAudio(audio_file, **FFMPEG_OPTIONS)
                
                if self.voice_client and self.voice_client.is_connected():
                    def after_playing(error):
                        # Only clean up if not looping the song
                        if not self.loop_song:
                            try:
                                if os.path.exists(audio_file):
                                    os.remove(audio_file)
                                    logger.info(f"Cleaned up: {audio_file}")
                            except Exception as e:
                                logger.error(f"Could not delete file: {e}")
                        
                        self.bot.loop.call_soon_threadsafe(self.next_event.set)
                    
                    self.voice_client.play(source, after=after_playing)
                    
                    # Build now playing embed
                    embed = discord.Embed(
                        title="now playing",
                        description=f"{self.current.title}",
                        color=discord.Color.purple()
                    )

                    embed.add_field(name="source", value=self.current.source, inline=True)

                    if self.current.duration:
                        mins, secs = divmod(self.current.duration, 60)
                        embed.add_field(name="duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)

                    embed.add_field(name="requested by", value=self.current.requester.mention, inline=True)

                    # Show loop status
                    if self.loop_song:
                        embed.set_footer(text="looping: single song")
                    elif self.loop_queue:
                        embed.set_footer(text="looping: queue")
                    
                    if self.current.thumbnail:
                        embed.set_thumbnail(url=self.current.thumbnail)
                    
                    await self.text_channel.send(embed=embed)
                    await self.next_event.wait()
                    
            except Exception as e:
                logger.error(f'player error: {e}')
                await self.text_channel.send(f'error playing song, skipping...')
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
            await ctx.send("you need to be in a voice channel")
            return
        
        platform = self.detect_platform(query)
        is_playlist = self.is_playlist(query)
        
        if platform == 'Spotify':
            await ctx.send("spotify links aren't supported, try searching the song name instead")
            return
        
        if is_playlist:
            msg = await ctx.send(f"loading playlist from {platform}... this may take a moment")
        else:
            if platform == 'SoundCloud':
                msg = await ctx.send(f"loading from soundcloud...")
            elif platform == 'YouTube':
                if not HAS_COOKIES:
                    await ctx.send("youtube may be blocked. consider using soundcloud or adding cookies.txt")
                msg = await ctx.send(f"loading from youtube...")
            else:
                msg = await ctx.send(f"searching for: `{query[:50]}...`")
        
        data = await self.extract_info(query, allow_playlist=is_playlist)
        
        if not data:
            error_msg = "could not find any results"
            if platform == 'YouTube' and not HAS_COOKIES:
                error_msg += "\n\nyoutube is blocking requests. solutions:\n- use soundcloud: `!sc <song>`\n- add cookies.txt file\n- use soundcloud links instead"
            await msg.edit(content=error_msg)
            return
        
        player = self.get_player(ctx)
        
        if not player.voice_client or not player.voice_client.is_connected():
            try:
                player.voice_client = await ctx.author.voice.channel.connect()
                await ctx.send(f"connected to {ctx.author.voice.channel.name}")
            except Exception as e:
                await msg.edit(content=f"could not connect to voice: {str(e)}")
                return
        
        # Handle playlist
        if 'entries' in data and is_playlist:
            entries = data['entries']
            added_count = 0
            
            for entry in entries[:50]:
                if not entry:
                    continue
                
                webpage_url = entry.get('webpage_url', '')
                if 'soundcloud' in webpage_url.lower():
                    source = 'soundcloud'
                elif 'youtube' in webpage_url.lower():
                    source = 'youtube'
                else:
                    source = 'audio'
                
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
                title="playlist added",
                description=f"added {added_count} songs to queue",
                color=discord.Color.green()
            )
            embed.add_field(name="requested by", value=ctx.author.mention)
            await msg.edit(content=None, embed=embed)
            logger.info(f'added playlist: {added_count} songs')
        
        # Handle single song
        else:
            if 'entries' in data:
                data = data['entries'][0]
            
            webpage_url = data.get('webpage_url', '')
            if 'soundcloud' in webpage_url.lower():
                actual_source = 'soundcloud'
            elif 'youtube' in webpage_url.lower():
                actual_source = 'youtube'
            else:
                actual_source = 'audio'
            
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
                title="added to queue",
                description=f"{song.title}",
                color=discord.Color.green()
            )

            embed.add_field(name="source", value=song.source, inline=True)
            embed.add_field(name="position", value=f"#{len(player.queue)}", inline=True)

            if song.duration:
                mins, secs = divmod(song.duration, 60)
                embed.add_field(name="duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)

            embed.add_field(name="requested by", value=ctx.author.mention, inline=False)
            
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            
            await msg.edit(content=None, embed=embed)
            logger.info(f'Queued ({song.source}): {song.title}')
    
    @commands.command(name='loop', aliases=['repeat'])
    async def loop(self, ctx, mode: str = None):
        """Toggle loop mode
        
        Usage:
        !loop - Toggle loop for current song
        !loop song - Loop current song
        !loop queue - Loop entire queue
        !loop off - Turn off all looping
        """
        
        player = self.get_player(ctx)
        
        if mode is None:
            # Toggle single song loop
            player.loop_song = not player.loop_song
            player.loop_queue = False
            
            if player.loop_song:
                await ctx.send("looping: current song will repeat")
            else:
                await ctx.send("loop disabled")
        
        elif mode.lower() in ['song', 'single', 'one', '1']:
            player.loop_song = True
            player.loop_queue = False
            await ctx.send("looping: current song will repeat")
        
        elif mode.lower() in ['queue', 'all', 'playlist']:
            player.loop_queue = True
            player.loop_song = False
            await ctx.send("looping: queue will repeat")
        
        elif mode.lower() in ['off', 'stop', 'disable', 'none']:
            player.loop_song = False
            player.loop_queue = False
            await ctx.send("loop disabled")
        
        else:
            await ctx.send("invalid loop mode — use: `!loop`, `!loop song`, `!loop queue`, or `!loop off`")
    
    @commands.command(name='loopstatus', aliases=['ls'])
    async def loopstatus(self, ctx):
        """Check current loop status"""
        player = self.get_player(ctx)
        
        if player.loop_song:
            status = "looping: current song"
        elif player.loop_queue:
            status = "looping: queue"
        else:
            status = "loop: disabled"

        embed = discord.Embed(
            title="loop status",
            description=status,
            color=discord.Color.purple()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='playlist', aliases=['pl'])
    async def playlist(self, ctx, *, url: str):
        """Load an entire playlist
        
        Usage: !playlist <playlist url>
        """
        
        if not self.is_playlist(url):
            await ctx.send("this doesn't look like a playlist url")
            return
        
        await self.play(ctx, query=url)
    
    @commands.command(name='sc', aliases=['soundcloud'])
    async def soundcloud(self, ctx, *, query: str):
        """Search and play from SoundCloud only
        
        Usage: !sc <song name or url>
        """
        
        if not ctx.author.voice:
            await ctx.send("you need to be in a voice channel")
            return
        
        is_playlist = self.is_playlist(query)
        
        if is_playlist:
            msg = await ctx.send(f"loading soundcloud playlist...")
        else:
            msg = await ctx.send(f"searching soundcloud for: `{query[:50]}...`")
        
        if not query.startswith('http'):
            query = f"scsearch:{query}"
        
        data = await self.extract_info(query, prefer_soundcloud=True, allow_playlist=is_playlist)
        
        if not data:
            await msg.edit(content="could not find any soundcloud results")
            return
        
        player = self.get_player(ctx)
        
        if not player.voice_client or not player.voice_client.is_connected():
            try:
                player.voice_client = await ctx.author.voice.channel.connect()
            except Exception as e:
                await msg.edit(content=f"could not connect: {str(e)}")
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
                    source='soundcloud'
                )
                
                player.queue.append(song)
                added_count += 1
            
            embed = discord.Embed(
                title="soundcloud playlist added",
                description=f"added {added_count} songs to queue",
                color=discord.Color.green()
            )
            embed.add_field(name="requested by", value=ctx.author.mention)
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
                source='soundcloud'
            )
            
            player.queue.append(song)
            
            embed = discord.Embed(
                title="added to queue",
                description=f"{song.title}",
                color=discord.Color.green()
            )
            embed.add_field(name="source", value="soundcloud", inline=True)
            embed.add_field(name="position", value=f"#{len(player.queue)}", inline=True)
            
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            
            await msg.edit(content=None, embed=embed)
    
    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pause the current song"""
        player = self.get_player(ctx)
        
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            await ctx.send("paused")
        else:
            await ctx.send("nothing is playing")
    
    @commands.command(name='resume')
    async def resume(self, ctx):
        """Resume the paused song"""
        player = self.get_player(ctx)
        
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
            await ctx.send("resumed")
        else:
            await ctx.send("music is not paused")
    
    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        """Skip the current song"""
        player = self.get_player(ctx)
        
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
            await ctx.send("skipped")
        else:
            await ctx.send("nothing is playing")
    
    @commands.command(name='stop')
    async def stop(self, ctx):
        """Stop music and disconnect"""
        player = self.get_player(ctx)
        
        if player.voice_client:
            player.queue.clear()
            player.loop_song = False
            player.loop_queue = False
            player.voice_client.stop()
            await player.voice_client.disconnect()
            
            try:
                if os.path.exists('downloads'):
                    for file in os.listdir('downloads'):
                        file_path = os.path.join('downloads', file)
                        os.remove(file_path)
            except Exception as e:
                logger.error(f"Could not clean downloads: {e}")
            
            await ctx.send("stopped and disconnected")
        else:
            await ctx.send("not connected")
    
    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx):
        """Show the music queue"""
        player = self.get_player(ctx)
        
        if not player.queue and not player.current:
            await ctx.send("queue is empty")
            return
        
        embed = discord.Embed(
            title="music queue",
            color=discord.Color.purple()
        )
        
        if player.current:
            current_info = f"{player.current.title}\n{player.current.source}"
            embed.add_field(
                name="now playing",
                value=current_info,
                inline=False
            )
        
        if player.queue:
            queue_list = []
            for i, song in enumerate(list(player.queue)[:10], 1):
                queue_list.append(f"`{i}.` {song.title}")
            
            embed.add_field(
                name=f"up next ({len(player.queue)} songs)",
                value="\n".join(queue_list),
                inline=False
            )
            
            if len(player.queue) > 10:
                embed.set_footer(text=f"and {len(player.queue) - 10} more...")
        
        # Show loop status
        if player.loop_song:
            embed.description = "looping: current song"
        elif player.loop_queue:
            embed.description = "looping: queue"
        
        await ctx.send(embed=embed)
    
    @commands.command(name='np', aliases=['nowplaying'])
    async def nowplaying(self, ctx):
        """Show the currently playing song"""
        player = self.get_player(ctx)
        
        if not player.current:
            await ctx.send("nothing is playing")
            return

        embed = discord.Embed(
            title="now playing",
            description=f"{player.current.title}",
            color=discord.Color.purple()
        )

        embed.add_field(name="source", value=player.current.source, inline=True)

        if player.current.duration:
            mins, secs = divmod(player.current.duration, 60)
            embed.add_field(name="duration", value=f"{int(mins)}:{int(secs):02d}", inline=True)

        embed.add_field(name="requested by", value=player.current.requester.mention, inline=True)

        # Show loop status
        if player.loop_song:
            embed.set_footer(text="looping: single song")
        elif player.loop_queue:
            embed.set_footer(text="looping: queue")

        if player.current.thumbnail:
            embed.set_thumbnail(url=player.current.thumbnail)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot))