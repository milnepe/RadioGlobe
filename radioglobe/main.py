import asyncio
import vlc
from dial_button_async import AsyncDialWithButton


stations = [
    ("WKSU Public Radio", "http://stream.wksu.org/wksu1.mp3.128"),
    ("WCPN Public Radio", "http://audio1.ideastream.org/wcpn128.mp3"),
]


class AudioPlayer:
    def __init__(self):
        self.instance = vlc.Instance('--input-repeat=-1')
        self.player = self.instance.media_player_new()
        self.current_url = None

    def play(self, url):
        """Play a new URL stream, stopping current playback if needed."""
        if self.player.is_playing():
            self.player.stop()

        self.current_url = url
        media = self.instance.media_new(url)
        self.player.set_media(media)
        self.player.play()
        print(f"🔊 Playing: {url}")

    def stop(self):
        """Stop playback if something is playing."""
        if self.player.is_playing():
            self.player.stop()


class App:
    def __init__(self):
        self.dial = AsyncDialWithButton()
        self.audio_player = AudioPlayer()
        self.stations = stations
        self.current_index = 0
        self.mode = "normal"

    def next_station(self, direction):
        """Navigate to the next or previous station."""
        self.current_index = (self.current_index + direction) % len(self.stations)
        name, url = self.stations[self.current_index]
        print(f"📻 Tuning to: {name}")
        self.audio_player.play(url)

    def switch_mode(self):
        """Toggle between application modes."""
        self.mode = "alt" if self.mode == "normal" else "normal"
        print(f"🌀 Mode switched to: {self.mode}")
        # Future mode-based behavior can go here

    async def run(self):
        """Main app loop."""
        self.dial.start()
        name, url = self.stations[self.current_index]
        print(f"📻 Starting with: {name}")
        self.audio_player.play(url)

        try:
            while True:
                await asyncio.sleep(0.1)

                direction = self.dial.get_direction()
                if direction != 0:
                    print(f"↪️ Dial turned: {'left' if direction > 0 else 'right'}")
                    self.next_station(direction)

                if self.dial.get_button():
                    print("🖲️ Button pressed!")
                    self.switch_mode()

        except KeyboardInterrupt:
            print("👋 Exiting on keyboard interrupt...")
        finally:
            self.audio_player.stop()
            await self.dial.stop()


if __name__ == "__main__":
    asyncio.run(App().run())
