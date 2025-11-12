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
        """Extract info (single or playlist)"""
        loop = self.bot.loop or asyncio.get_event_loop()
        try:
            data = await ytdl_source.extract_info(loop, query)
            if not data:
                return None

            # Playlist support
            if 'entries' in data and data.get('_type') == 'playlist':
                return data['entries']
            if 'entries' in data:
                data = data['entries'][0]
            return data
        except Exception as e:
            logger.error(f'Search error: {e}')
            return None

    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Play music or playlist from YouTube or SoundCloud"""
        if not ctx.author.voice:
            return await ctx.send("❌ You need to be in a voice channel!")

        platform = self.detect_platform(query)
        msg = await ctx.send(f"🔍 Loading from **{platform}**: `{query[:60]}...`")

        data = await self.extract_info(query)
        if not data:
            return await msg.edit(content="❌ Could not retrieve any results!")

        player = self.get_player(ctx)

        # Connect to voice if needed
        if not player.voice_client or not player.voice_client.is_connected():
            try:
                player.voice_client = await ctx.author.voice.channel.connect()
                await ctx.send(f"🔊 Connected to **{ctx.author.voice.channel.name}**")
            except Exception as e:
                return await msg.edit(content=f"❌ Could not connect: {e}")

        # Playlist handling
        if isinstance(data, list):
            for entry in data:
                if not entry:
                    continue
                song = Song(
                    url=entry.get('webpage_url', entry.get('url')),
                    title=entry.get('title', 'Unknown Title'),
                    duration=entry.get('duration'),
                    thumbnail=entry.get('thumbnail'),
                    requester=ctx.author,
                    source='🎵 SoundCloud Playlist' if 'soundcloud' in query else '📺 YouTube Playlist'
                )
                player.queue.append(song)

            await msg.edit(content=f"✅ Added **{len(data)} tracks** from playlist!")
            logger.info(f'Queued playlist of {len(data)} songs from {platform}')
            return

        # Single track
        song = Song(
            url=data.get('webpage_url', data.get('url')),
            title=data.get('title', 'Unknown Title'),
            duration=data.get('duration'),
            thumbnail=data.get('thumbnail'),
            requester=ctx.author,
            source='🎵 SoundCloud' if 'soundcloud' in query else '📺 YouTube'
        )

        player.queue.append(song)
        await msg.edit(content=f"✅ Added to queue: **{song.title}**")
        logger.info(f'Queued ({song.source}): {song.title}')

    @commands.command(name='pause')
    async def pause(self, ctx):
        player = self.get_player(ctx)
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.pause()
            await ctx.send("⏸️ Music paused.")
        else:
            await ctx.send("❌ Nothing is playing!")

    @commands.command(name='resume')
    async def resume(self, ctx):
        player = self.get_player(ctx)
        if player.voice_client and player.voice_client.is_paused():
            player.voice_client.resume()
            await ctx.send("▶️ Music resumed.")
        else:
            await ctx.send("❌ Music is not paused!")

    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        player = self.get_player(ctx)
        if player.voice_client and player.voice_client.is_playing():
            player.voice_client.stop()
            await ctx.send("⏭️ Skipped current track.")
        else:
            await ctx.send("❌ Nothing is playing!")

    @commands.command(name='stop')
    async def stop(self, ctx):
        player = self.get_player(ctx)
        if player.voice_client:
            player.queue.clear()
            player.voice_client.stop()
            await player.voice_client.disconnect()
            await ctx.send("⏹️ Music stopped and disconnected.")
        else:
            await ctx.send("❌ Not connected to any voice channel.")

    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx):
        player = self.get_player(ctx)
        if not player.queue and not player.current:
            return await ctx.send("❌ Queue is empty.")

        embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blue())

        if player.current:
            embed.add_field(
                name="Now Playing",
                value=f"**{player.current.title}**\n{player.current.source}",
                inline=False
            )

        if player.queue:
            queue_list = [
                f"`{i+1}.` **{song.title}** ({song.source})"
                for i, song in enumerate(list(player.queue)[:10])
            ]
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
        player = self.get_player(ctx)
        if not player.current:
            return await ctx.send("❌ Nothing is playing!")

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
