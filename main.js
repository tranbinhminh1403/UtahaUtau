// Import necessary modules
const { Client, GatewayIntentBits, Collection } = require('discord.js');
const ytdl = require('ytdl-core');
const fs = require('fs');
const path = require('path');

// Bot configuration
const token = process.env.DISCORD_TOKEN;
const prefix = '!';
const CACHE_DIRECTORY = 'music_cache';

// Create cache directory if it doesn't exist
if (!fs.existsSync(CACHE_DIRECTORY)) {
    fs.mkdirSync(CACHE_DIRECTORY);
}

// Initialize Discord client
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.MessageContent
    ]
});

// Cache management
let songCache = {};
const loadCache = () => {
    try {
        const data = fs.readFileSync('song_cache.json', 'utf8');
        return JSON.parse(data);
    } catch (err) {
        return {};
    }
};

const saveCache = (cache) => {
    fs.writeFileSync('song_cache.json', JSON.stringify(cache, null, 4));
};

songCache = loadCache();

// Music queue class
class MusicQueue {
    constructor() {
        this.queue = [];
        this.current = null;
        this.loopCount = 0;
        this.currentLoops = 0;
    }

    add(item, loopCount = 0) {
        this.queue.push({ item, loopCount });
    }

    next() {
        if (this.current && this.loopCount !== 0) {
            if (this.loopCount > 0) {
                this.currentLoops += 1;
                if (this.currentLoops < this.loopCount) {
                    return this.current;
                }
            } else if (this.loopCount === -1) {
                return this.current;
            }
        }
        this.currentLoops = 0;
        if (this.queue.length > 0) {
            const nextItem = this.queue.shift();
            this.current = nextItem.item;
            this.loopCount = nextItem.loopCount;
            return this.current;
        }
        this.current = null;
        this.loopCount = 0;
        return null;
    }

    clear() {
        this.queue = [];
        this.current = null;
        this.loopCount = 0;
        this.currentLoops = 0;
    }

    getCurrentTitle() {
        return this.current ? this.current.title : null;
    }
}

const musicQueues = new Map();

// Helper function to play music
async function playNext(guildId, connection, currentPlayer = null) {
    const queue = musicQueues.get(guildId);
    if (!queue) return;

    if (!currentPlayer) {
        currentPlayer = queue.next();
    }

    if (!currentPlayer) {
        connection.disconnect();
        return;
    }

    const dispatcher = connection.play(currentPlayer.url);
    dispatcher.on('finish', () => {
        playNext(guildId, connection);
    });

    dispatcher.on('error', console.error);
}

// Event listener for when the bot is ready
client.once('ready', () => {
    console.log(`Logged in as ${client.user.tag}!`);
});

// Event listener for messages
client.on('messageCreate', async (message) => {
    if (!message.content.startsWith(prefix) || message.author.bot) return;

    const args = message.content.slice(prefix.length).trim().split(/ +/);
    const command = args.shift().toLowerCase();

    if (command === 'play') {
        const url = args[0];
        if (!url) {
            message.channel.send('Please provide a URL!');
            return;
        }

        const guildId = message.guild.id;
        if (!musicQueues.has(guildId)) {
            musicQueues.set(guildId, new MusicQueue());
        }

        const queue = musicQueues.get(guildId);

        if (message.member.voice.channel) {
            const connection = await message.member.voice.channel.join();

            if (queue.getCurrentTitle() === url) {
                message.channel.send(`'${url}' is already playing!`);
                return;
            }

            const info = await ytdl.getInfo(url);
            const title = info.videoDetails.title;
            const format = ytdl.chooseFormat(info.formats, { quality: 'highestaudio' });
            const song = { title, url: format.url };

            if (connection.dispatcher && connection.dispatcher.writable) {
                queue.add(song);
                message.channel.send(`Added to queue: ${title}`);
            } else {
                queue.clear();
                queue.add(song);
                playNext(guildId, connection, song);
                message.channel.send(`Now playing: ${title}`);
            }
        } else {
            message.channel.send("You're not connected to a voice channel!");
        }
    }

    if (command === 'skip') {
        const guildId = message.guild.id;
        const queue = musicQueues.get(guildId);
        if (queue && queue.current) {
            queue.current = null;
            playNext(guildId, message.guild.voice.connection);
            message.channel.send('Skipped current song!');
        } else {
            message.channel.send('Nothing to skip!');
        }
    }

    if (command === 'clear') {
        const guildId = message.guild.id;
        if (musicQueues.has(guildId)) {
            musicQueues.get(guildId).clear();
            message.channel.send('Queue cleared!');
        } else {
            message.channel.send('No queue exists!');
        }
    }
});

// Log in to Discord
client.login(token);