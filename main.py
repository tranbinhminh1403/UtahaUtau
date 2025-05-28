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
from discord import app_commands
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()

# Get Discord token, command prefix, and YouTube API key
token = os.getenv('DISCORD_TOKEN')
youtube_api_key = os.getenv('YOUTUBE_API_KEY')
prefix = '/'

# Cache directory for downloaded songs
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

# Cache management
def load_cache():
    try:
        with open('song_cache.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_cache(cache):
    with open('song_cache.json', 'w') as f:
        json.dump(cache, f, indent=4)

song_cache = load_cache()

# Utility to extract playlist ID from URL
def extract_playlist_id(url):
    pattern = r'(?:list=)([a-zA-Z0-9_-]+)'
    match = re.search(pattern, url)
    return match.group(1) if match else None

# Fetch video IDs from a YouTube playlist
async def get_playlist_videos(playlist_id):
    video_ids = []
    try:
        youtube = build('youtube', 'v3', developerKey=youtube_api_key)
        request = youtube.playlistItems().list(
            part='snippet',
            playlistId=playlist_id,
            maxResults=50
        )
        
        while request:
            response = request.execute()
            for item in response.get('items', []):
                video_id = item['snippet']['resourceId'].get('videoId')
                if video_id:
                    video_ids.append(video_id)
            
            # Handle pagination
            next_page_token = response.get('nextPageToken')
            if next_page_token:
                request = youtube.playlistItems().list(
                    part='snippet',
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
            else:
                request = None
                
        return video_ids
    except HttpError as e:
        print(f"Error fetching playlist: {e}")
        return []

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
        
        if url in song_cache and os.path.exists(song_cache[url]['filename']):
            data = song_cache[url]
            filename = data['filename']
            print(f"Cache hit! Loading from cache: {filename}")
        else:
            print(f"Cache miss! Downloading...")
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
            
            if 'entries' in data:
                data = data['entries'][0]

            filename = ytdl.prepare_filename(data)
            
            song_cache[url] = {
                'title': data.get('title'),
                'url': data.get('url'),
                'filename': filename
            }
            save_cache(song_cache)
            print(f"Downloaded new song: {filename}")

        return cls(discord.FFmpegPCMAudio(filename, options='-vn'), data=data)

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

def is_correct_channel():
    async def predicate(interaction: discord.Interaction):
        return interaction.channel.name == 'utaha-yap-cmd'
    return app_commands.check(predicate)

@bot.tree.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):
    if interaction.user.voice is None:
        await interaction.response.send_message("You're not connected to a voice channel!")
        return
    
    voice_channel = interaction.user.voice.channel
    if interaction.guild.voice_client is None:
        await voice_channel.connect()
    else:
        await interaction.guild.voice_client.move_to(voice_channel)
    await interaction.response.send_message("Joined the voice channel!")

class MusicQueue:
    def __init__(self):
        self.queue = deque()
        self.current = None
        self.loop_count = 0
        self.current_loops = 0

    def add(self, item):
        self.queue.append(item)

    def next(self):
        if self.current and self.loop_count != 0:
            if self.loop_count > 0:
                self.current_loops += 1
                if self.current_loops < self.loop_count:
                    return self.current
            elif self.loop_count == -1:
                return self.current
                
        self.current_loops = 0
        if len(self.queue) > 0:
            self.current = self.queue.popleft()
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
        if self.current is None:
            return None
        url, _ = self.current
        return song_cache[url]['title'] if url in song_cache else url

music_queues = {}

@bot.tree.command(name="play", description="Play a song or playlist from URL")
@app_commands.describe(
    url="The URL of the song or playlist to play",
    loop="Number of times to loop (use ! for infinite)",
    skip="Skip current song if playing"
)
async def play(
    interaction: discord.Interaction, 
    url: str, 
    loop: str = None, 
    skip: bool = False
):
    await interaction.response.defer()
    
    if interaction.user.voice is None:
        await interaction.followup.send("You're not connected to a voice channel!")
        return

    if interaction.guild.voice_client is None:
        await interaction.user.voice.channel.connect()
    
    guild_id = interaction.guild_id
    if guild_id not in music_queues:
        music_queues[guild_id] = MusicQueue()

    queue = music_queues[guild_id]
    
    loop_count = 0
    if loop:
        if loop == "!":
            loop_count = -1
        else:
            try:
                loop_count = int(loop)
                if loop_count <= 0:
                    await interaction.followup.send("Loop count must be positive!")
                    return
            except ValueError:
                await interaction.followup.send("Invalid loop count format!")
                return

    # Check if URL is a playlist
    if "playlist" in url.lower():
        playlist_id = extract_playlist_id(url)
        if not playlist_id:
            await interaction.followup.send("Invalid playlist URL!")
            return
        
        video_ids = await get_playlist_videos(playlist_id)
        if not video_ids:
            await interaction.followup.send("Failed to fetch playlist videos or playlist is empty!")
            return
        
        # Add each video to the queue
        video_urls = [f"https://www.youtube.com/watch?v={video_id}" for video_id in video_ids]
        for video_url in video_urls:
            queue.add((video_url, loop_count))
        
        if not interaction.guild.voice_client.is_playing() or skip:
            if skip and interaction.guild.voice_client.is_playing():
                interaction.guild.voice_client.stop()
            await play_next(interaction, guild_id)
            await interaction.followup.send(f"Added {len(video_urls)} songs from playlist to queue!")
        else:
            await interaction.followup.send(f"Added {len(video_urls)} songs from playlist to queue!")
        return

    # Handle single video
    queue.add((url, loop_count))

    if not interaction.guild.voice_client.is_playing() or skip:
        if skip and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
        await play_next(interaction, guild_id)
        return

    await interaction.followup.send(f"Added to queue: {url}")

async def play_next(interaction, guild_id, current_player=None):
    if guild_id not in music_queues:
        return

    queue = music_queues[guild_id]

    if current_player is None:
        current_player = queue.next()

    if current_player is None:
        print("Queue is empty, nothing to play.")
        return

    url, loop_count = current_player
    
    player = await YTDLSource.from_url(url, loop=bot.loop, stream=False)

    def after_playing(error):
        if error:
            print(f'Player error: {error}')
            asyncio.run_coroutine_threadsafe(
                interaction.followup.send(f"An error occurred: {error}"), bot.loop
            )
        else:
            print("Song finished playing normally")
            next_player = queue.next()
            if next_player:
                asyncio.run_coroutine_threadsafe(
                    play_next(interaction, guild_id, next_player), bot.loop
                )
            else:
                asyncio.run_coroutine_threadsafe(
                    interaction.followup.send("I'm done yapping!"), bot.loop
                )

    try:
        print(f"Playing song: {player.title}")
        interaction.guild.voice_client.play(player, after=after_playing)
        embed = discord.Embed(
            title="Now yapping",
            description=f"{player.title}",
            color=discord.Color.purple()
        )

        await interaction.followup.send(
            embed=embed,
            file=discord.File('img/utaha.png', filename='utaha.png')
        )
    except Exception as e:
        await interaction.followup.send(f"An error occurred while playing: {str(e)}")

@bot.tree.command(name="stop", description="Stop playing and clear queue")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id in music_queues:
        music_queues[guild_id].clear()
    
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Stopped playing and cleared queue!")
    else:
        await interaction.response.send_message("Not playing anything right now!")

@bot.tree.command(name="leave", description="Leave the voice channel")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Left the voice channel!")
    else:
        await interaction.response.send_message("I'm not in a voice channel!")

@bot.event
async def on_message(message):
    try:
        await bot.process_commands(message)
    except Exception as e:
        print(f"Error processing message: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandOnCooldown):
        await ctx.send(f"Please wait {error.retry_after:.2f}s before using this command again.")
    elif isinstance(error, discord.errors.HTTPException) and error.code == 429:
        retry_after = error.retry_after if hasattr(error, 'retry_after') else 60
        await ctx.send(f"Bot is rate limited. Please try again in {retry_after} seconds.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("Please use commands in the #utaha-yap-cmd channel!")
    else:
        print(f"Command error: {error}")

@discord.app_commands.command()
async def example(ctx):
    try:
        await ctx.send("Command executed!")
    except Exception as e:
        print(f"Error in example command: {e}")

@bot.tree.command(name="queue", description="Show current song queue")
async def show_queue(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id not in music_queues:
        await interaction.response.send_message("No queue exists!")
        return

    queue = music_queues[guild_id]
    if len(queue.queue) == 0:
        await interaction.response.send_message("Queue is empty!")
        return

    queue_list = "\n".join([f"{i+1}. {song_cache[url]['title'] if url in song_cache else url}" 
                           for i, ((url, _), _) in enumerate(queue.queue)])
    await interaction.response.send_message(f"**Current queue:**\n{queue_list}")

@bot.tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped current song!")
    else:
        await interaction.response.send_message("Nothing to skip!")

@discord.app_commands.command(name='clear')
@is_correct_channel()
async def clear(ctx):
    guild_id = ctx.guild.id
    if guild_id in music_queues:
        music_queues[guild_id].clear()
        await ctx.send("Queue cleared!")
    else:
        await ctx.send("No queue exists!")

@discord.app_commands.command(name='info')
async def info(ctx):
    embed = discord.Embed(
        title="Utaha",
        description="This is how Utaha sounds like",
        color=discord.Color.purple()
    )
    embed.add_field(name="Author", value="F.Femto", inline=False)
    embed.add_field(name="Version", value="1.0", inline=False)
    embed.set_footer(text="Thank you for listening Utaha!")
    embed.set_thumbnail(url="https://imgur.com/qrcB6kn")

    await ctx.send(embed=embed)
    
# Run bot
bot.run(token)