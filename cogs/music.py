import discord
from discord.ext import commands
import asyncio
import yt_dlp
from collections import deque
import logging

logger = logging.getLogger('MusicCog')

# Updated yt-dlp options
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'force-ipv4': True,
    'prefer_ffmpeg': True,
    'geo_bypass': True,
    'cachedir': False,
    'extract_flat': False,
    'retries': 3,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'user-agent': 'Mozilla/5.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 128k'
}

class YTDLSource:
    """Handles extracting info from YouTube/SoundCloud using yt-dlp"""
    def __init__(self):
        self.ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

    async def extract_info(self, loop, query):
        """Extract media info with retries"""
        try:
            data = await loop.run_in_executor(
                None, lambda: self.ytdl.extract_info(query, download=False)
            )
            return data
        except Exception as e:
            logger.error(f"Extract error: {e}")
            return None

ytdl_source = YTDLSource()

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
                data = await ytdl_source.extract_info(loop, self.current.url)

                if not data:
                    await self.text_channel.send(f"❌ Could not play: {self.current.title}")
                    continue

                if 'entries' in data:
                    data = data['entries'][0]

                audio_url = data.get('url')
                if not audio_url:
                    logger.error("No audio URL found")
                    await self.text_channel.send("❌ Could not get audio stream URL")
                    continue

                source = discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS)

                if self.voice_client and self.voice_client.is_connected():
                    def after_play(e):
                        if e:
                            logger.warning(f"FFmpeg exited with error: {e}")
                        self.bot.loop.call_soon_threadsafe(self.next_event.set)

                    self.voice_client.play(source, after=after_play)

                    embed = discord.Embed(
                        title="🎵 Now Playing",
                        description=f"**{self.current.title}**",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Source", value=self.current.source, inline=True)

                    if self.current.duration:
                        mins, secs = divmod(self.current.duration, 60)
                        embed.add_field(
                            name="Duration", value=f"{int(mins)}:{int(secs):02d}", inline=True
                        )

                    embed.add_field(
                        name="Requested by", value=self.current.requester.mention, inline=True
                    )

                    if self.current.thumbnail:
                        embed.set_thumbnail(url=self.current.thumbnail)

                    await self.text_channel.send(embed=embed)
                    await self.next_event.wait()

            except Exception as e:
                logger.error(f'Player error: {e}')
                await self.text_channel.send(f'❌ Error playing song: {e}')
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
        """Detect if query is YouTube, SoundCloud, or search"""
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
        """Extract info (single or play
