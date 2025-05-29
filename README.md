# Utaha Music Bot

Utaha is a Discord bot designed to play music in voice channels, supporting both individual songs and YouTube playlists. It uses `yt-dlp` for downloading audio and the YouTube Data API for fetching playlist details. The bot features a song queue, looping options, and a caching system to optimize performance by reusing downloaded songs.

## Features

- **Play Music**: Play songs from YouTube URLs or entire playlists.
- **Queue Management**: Add songs or playlists to a queue, view the queue, and skip songs.
- **Looping**: Loop the current song a specified number of times or infinitely.
- **Caching**: Stores downloaded songs to avoid redundant downloads, improving performance.
- **Voice Channel Control**: Join, leave, and stop playback in voice channels.
- **Error Handling**: Gracefully handles rate limits, invalid URLs, and other errors.
- **Custom Commands**: Restricted to a specific channel (`#utaha-yap-cmd`) for organized command usage.
- **Info Command**: Displays bot details with an embedded message and thumbnail.

## Prerequisites

- Python 3.8+
- Discord account and a bot token
- YouTube Data API key
- FFmpeg installed on your system
- Required Python packages (see Installation)

## Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/tranbinhminh1403/UtahaUtau.git
   cd UtahaUtau
   ```

2. **Install Dependencies**
   Install the required Python packages:
   ```bash
   pip install discord.py yt-dlp python-dotenv google-api-python-client
   ```

3. **Set Up Environment Variables**
   Create a `.env` file in the project root and add the following:
   ```plaintext
   DISCORD_TOKEN=your_discord_bot_token
   YOUTUBE_API_KEY=your_youtube_api_key
   ```

4. **Install FFmpeg**
   - On Windows: Download from [FFmpeg website](https://ffmpeg.org/download.html) and add to PATH.
   - On Linux: `sudo apt-get install ffmpeg` (Ubuntu/Debian) or equivalent for your distribution.

5. **Create Cache Directory**
   Create a `music_cache` directory in the project root to store downloaded audio files:
   ```bash
   mkdir music_cache
   ```

6. **Add Thumbnail Image**
   Place a `utaha.png` image in an `img` directory within the project root for the `/play` command embed.

## Usage

1. **Run the Bot**
   Start the bot by running:
   ```bash
   python main.py
   ```

2. **Invite the Bot**
   Add the bot to your Discord server using an invite link generated from the Discord Developer Portal.

3. **Commands**
   All commands use the `/` prefix and must be used in the `#utaha-yap-cmd` channel (except `/info`):
   - `/join`: Joins the user's voice channel.
   - `/play <url> [loop] [skip]`: Plays a song or playlist from the given URL. Optionally specify `loop` (number or `!` for infinite) and `skip` (true to skip current song).
   - `/stop`: Stops playback and clears the queue.
   - `/leave`: Disconnects the bot from the voice channel.
   - `/queue`: Displays the current song queue.
   - `/skip`: Skips the current song.
   - `/clear`: Clears the song queue.
   - `/info`: Displays bot information with an embedded message.

## Example

To play a song:
```
/play https://www.youtube.com/watch?v=example ! true
```
This plays the song, loops it infinitely, and skips the current song if one is playing.

To play a playlist:
```
/play https://www.youtube.com/playlist?list=example_playlist
```
This adds all playlist songs to the queue.

## Notes

- The bot caches downloaded songs in `song_cache.json` and the `music_cache` directory to reduce redundant downloads.
- Ensure the YouTube API key has access to the YouTube Data API v3.
- The bot requires the `message_content` intent and proper permissions to join voice channels and send messages.
- For large playlists, the bot fetches up to 50 videos per API request, handling pagination automatically.

## Troubleshooting

- **Bot not responding**: Check the Discord token and ensure the bot has proper permissions.
- **No audio playing**: Verify FFmpeg is installed and accessible in your system's PATH.
- **Playlist errors**: Ensure the YouTube API key is valid and the playlist URL is correct (make sure playlist is public or unlisted).
- **Rate limits**: If the bot encounters HTTP 429 errors, it will notify users to wait before retrying.

