"""
Python radio stream player that:

Tries a .pls URL first

If that fails, tries a fallback direct stream URL

Plays the stream using python-vlc

Prints helpful messages (e.g., which stream is playing)

Exits cleanly if no valid stream is found
"""

import requests
import configparser
import vlc
import time
import io


def parse_pls(pls_url):
    try:
        response = requests.get(pls_url, timeout=5)
        pls_text = response.text

        config = configparser.ConfigParser()
        config.read_file(io.StringIO(pls_text))

        if config.has_section("playlist"):
            for option in config.options("playlist"):
                if option.startswith("file"):
                    stream_url = config.get("playlist", option)
                    print(f"✅ Found stream in .pls: {stream_url}")
                    return stream_url
        print("⚠️ No valid stream URL found in .pls.")
    except Exception as e:
        print(f"❌ Failed to fetch or parse .pls: {e}")
    return None


def play_stream(stream_url):
    instance = vlc.Instance()
    player = instance.media_player_new()
    media = instance.media_new(stream_url)
    player.set_media(media)
    player.play()

    print(f"🎧 Now streaming: {stream_url}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Stopping...")
        player.stop()


# === Main Execution ===
# Try with a .pls first
pls_url = "http://www.streamvortex.com:11300/stream.pls"
fallback_stream = "http://www.streamvortex.com:11300/stream"  # direct MP3 stream
# pls_url = "http://www.streamvortex.com:11300/stream.m3u"
# fallback_stream = "http://www.streamvortex.com:11300/stream"  # direct MP3 stream - bad!

stream_url = parse_pls(pls_url)
if not stream_url:
    print("🔁 Falling back to direct stream...")
    stream_url = fallback_stream

if stream_url:
    play_stream(stream_url)
else:
    print("❌ No valid stream found. Exiting.")
