import discord
from discord.ext import commands
import yt_dlp
import asyncio
from datetime import datetime, timedelta
import os
from pathlib import Path
import json
from collections import deque
from dotenv import load_dotenv

load_dotenv()

token = os.getenv('DISCORD_TOKEN')
prefix = '!'
CACHE_DIRECTORY = "music_cache"

# Bot config
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=prefix, intents=intents)

# YouTube DL options
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': os.path.join(CACHE_DIRECTORY, '%(extractor)s-%(id)s-%(title)s.%(ext)s'),
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

# Create Youtube DL client
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# Add these functions to manage cache persistence
def load_cache():
    try:
        with open('song_cache.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_cache(cache):
    with open('song_cache.json', 'w') as f:
        json.dump(cache, f, indent=4)

# Replace the song_cache initialization with this
song_cache = load_cache()

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.filename = data.get('filename', None)

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        
        print(f"Checking cache for URL: {url}")
        
        # Check if the song is in cache
        if url in song_cache and os.path.exists(song_cache[url]['filename']):
            data = song_cache[url]
            filename = data['filename']
            print(f"Cache hit! Loading from cache: {filename}")
        else:
            print(f"Cache miss! Downloading...")
            # Download if not in cache
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
            
            if 'entries' in data:
                data = data['entries'][0]

            filename = ytdl.prepare_filename(data)
            
            # Store in cache
            song_cache[url] = {
                'title': data.get('title'),
                'url': data.get('url'),
                'filename': filename
            }
            # Save cache to file after updating
            save_cache(song_cache)
            print(f"Downloaded new song: {filename}")

        return cls(discord.FFmpegPCMAudio(filename, options='-vn'), data=data)

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')

def is_correct_channel():
    async def predicate(ctx):
        return ctx.channel.name == 'seggs-bot-cmd'
    return commands.check(predicate)

@bot.command(name='join')
@is_correct_channel()
async def join(ctx):
    if ctx.author.voice is None:
        await ctx.send("You're not connected to a voice channel!")
        return
    
    voice_channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await voice_channel.connect()
    else:
        await ctx.voice_client.move_to(voice_channel)

class MusicQueue:
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.loop_count = 0  # Number of times to loop (0 = no loop, -1 = infinite)
        self.current_loops = 0  # Track how many times current song has looped

    def add(self, item, loop_count=0):
        self.queue.append((item, loop_count))

    def next(self):
        if self.current and self.loop_count != 0:
            # Still have loops to go
            if self.loop_count > 0:
                self.current_loops += 1
                if self.current_loops < self.loop_count:
                    return self.current
            elif self.loop_count == -1:  # Infinite loop
                return self.current
                
        # No more loops or no current song
        self.current_loops = 0
        if len(self.queue) > 0:
            self.current, self.loop_count = self.queue.popleft()
            return self.current
        self.current = None
        self.loop_count = 0
        return None

    def clear(self):
        self.queue.clear()
        self.current = None
        self.loop_count = 0
        self.current_loops = 0

    def get_current_title(self):
        return self.current.title if self.current else None

music_queues = {}  # Dictionary to store queues for each guild

@bot.command(name='play')
@is_correct_channel()
async def play(ctx, *args):
    if len(args) == 0:
        await ctx.send("Please provide a URL!")
        return

    # Parse arguments
    skip_flag = False
    loop_count = 0
    url = args[0]
    
    # Check for flags
    if args[0].startswith('x'):
        if len(args) < 2:
            await ctx.send("Please provide a URL after loop count!")
            return
        
        loop_str = args[0][1:]  # Remove 'x' prefix
        url = args[1]
        
        if loop_str == '!':
            loop_count = -1  # Infinite loop
        else:
            try:
                loop_count = int(loop_str)
                if loop_count <= 0:
                    await ctx.send("Loop count must be positive!")
                    return
            except ValueError:
                await ctx.send("Invalid loop count format!")
                return
    
    elif args[0] == '--skip':
        if len(args) < 2:
            await ctx.send("Please provide a URL after --skip!")
            return
        skip_flag = True
        url = args[1]

    guild_id = ctx.guild.id
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue()

    # Check if the song is currently playing
    queue = music_queues[guild_id]
    if ctx.voice_client and ctx.voice_client.is_playing():
        current_title = queue.get_current_title()
        new_song = await YTDLSource.from_url(url, loop=bot.loop, stream=False)
        
        if current_title == new_song.title:
            await ctx.send(f"'{new_song.title}' is already playing!")
            return

    if ctx.voice_client is None:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You're not connected to a voice channel!")
            return

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=False)
        
        if ctx.voice_client.is_playing():
            if skip_flag:
                ctx.voice_client.stop()
                music_queues[guild_id].loop_count = loop_count
                await play_next(ctx, guild_id, player)
            else:
                music_queues[guild_id].add(player, loop_count)
                loop_msg = ""
                if loop_count == -1:
                    loop_msg = " (will loop infinitely)"
                elif loop_count > 0:
                    loop_msg = f" (will loop {loop_count} times)"
                await ctx.send(f'Added to queue: {player.title}{loop_msg}')
            return

        music_queues[guild_id].clear()
        music_queues[guild_id].loop_count = loop_count
        await play_next(ctx, guild_id, player)

async def play_next(ctx, guild_id, current_player=None):
    if guild_id not in music_queues:
        return

    queue = music_queues[guild_id]
    
    # If no current_player provided, get next from queue
    if current_player is None:
        current_player = queue.next()
        
    if current_player is None:
        return

    def after_playing(error):
        if error:
            print(f'Player error: {error}')
            asyncio.run_coroutine_threadsafe(
                ctx.send(f"An error occurred: {error}"), bot.loop
            )
        else:
            print("Song finished playing normally")
            # Play next song in queue
            next_player = queue.next()
            if next_player:
                asyncio.run_coroutine_threadsafe(
                    play_next(ctx, guild_id, next_player), bot.loop
                )
            else:
                asyncio.run_coroutine_threadsafe(
                    ctx.send("Queue finished!"), bot.loop
                )

    try:
        ctx.voice_client.play(current_player, after=after_playing)
        await ctx.send(f'Now playing: {current_player.title}')
    except Exception as e:
        await ctx.send(f"An error occurred while playing: {str(e)}")

@bot.command(name='stop')
@is_correct_channel()
async def stop(ctx):
    guild_id = ctx.guild.id
    if guild_id in music_queues:
        music_queues[guild_id].clear()
    
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Stopped playing and cleared queue!")
    else:
        await ctx.send("Not playing anything right now!")

@bot.command(name='leave')
@is_correct_channel()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left the voice channel!")
    else:
        await ctx.send("I'm not in a voice channel!")

# Simplify the on_message event handler
@bot.event
async def on_message(message):
    try:
        await bot.process_commands(message)
    except Exception as e:
        print(f"Error processing message: {e}")

# Add error handling to your commands
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandOnCooldown):
        await ctx.send(f"Please wait {error.retry_after:.2f}s before using this command again.")
    elif isinstance(error, discord.errors.HTTPException) and error.code == 429:
        retry_after = error.retry_after if hasattr(error, 'retry_after') else 60
        await ctx.send(f"Bot is rate limited. Please try again in {retry_after} seconds.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("Please use commands in the #seggs-bot-cmd channel!")
    else:
        print(f"Command error: {error}")

@bot.command()
async def example(ctx):
    try:
        await ctx.send("Command executed!")
    except Exception as e:
        print(f"Error in example command: {e}")

# Add queue command to show current queue
@bot.command(name='queue')
@is_correct_channel()
async def show_queue(ctx):
    guild_id = ctx.guild.id
    if guild_id not in music_queues:
        await ctx.send("No queue exists!")
        return

    queue = music_queues[guild_id]
    if len(queue.queue) == 0:
        await ctx.send("Queue is empty!")
        return

    queue_list = "\n".join([f"{i+1}. {player.title}" for i, player in enumerate(queue.queue)])
    await ctx.send(f"**Current queue:**\n{queue_list}")

@bot.command(name='skip')
@is_correct_channel()
async def skip(ctx):
    guild_id = ctx.guild.id
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()  # This will trigger the after_playing callback
        await ctx.send("Skipped current song!")
    else:
        await ctx.send("Nothing to skip!")

@bot.command(name='clear')
@is_correct_channel()
async def clear(ctx):
    guild_id = ctx.guild.id
    if guild_id in music_queues:
        music_queues[guild_id].clear()
        await ctx.send("Queue cleared!")
    else:
        await ctx.send("No queue exists!")

@bot.command(name='seia')
@is_correct_channel()
async def seia(ctx):
    url = "https://www.youtube.com/watch?v=6wqcni74cM4"
    await play(ctx, url)

@bot.command(name='aru')
@is_correct_channel()
async def seia(ctx):
    url = "https://www.youtube.com/watch?v=ptKDIAXYoE8"
    await play(ctx, url)

@bot.command(name='arisu')
@is_correct_channel()
async def seia(ctx):
    url = "https://www.youtube.com/watch?v=toPWvdaC84w"
    await play(ctx, url)


# Run bot
bot.run(token)
