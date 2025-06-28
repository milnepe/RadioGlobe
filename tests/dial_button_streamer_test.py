import asyncio
import vlc
from dial_button_async import AsyncDialWithButton


stations = [
    ("WKSU Public Radio", "http://stream.wksu.org/wksu1.mp3.128"),
    ("WCPN Public Radio", "http://audio1.ideastream.org/wcpn128.mp3"),
]


class AudioPlayer:
    def __init__(self):
        self.instance = vlc.Instance("--input-repeat=-1")
        self.player = self.instance.media_player_new()
        self.current_url = None

    def play(self, url):
        if self.player.is_playing():
            self.player.stop()

        self.current_url = url
        media = self.instance.media_new(url)
        self.player.set_media(media)
        self.player.play()
        print(f"🔊 Playing: {url}")

    def stop(self):
        if self.player.is_playing():
            self.player.stop()


class App:
    def __init__(self):
        self.dial = AsyncDialWithButton()
        self.audio_player = AudioPlayer()
        self.urls = [url[1] for url in stations]
        self.current_index = 0
        self.mode = "normal"

    def next_url(self, direction):
        self.current_index = (self.current_index + direction) % len(self.urls)
        url = self.urls[self.current_index]
        self.audio_player.play(url)

    def switch_mode(self):
        self.mode = "alt" if self.mode == "normal" else "normal"
        print(f"🌀 Mode switched to: {self.mode}")
        # You can perform different actions based on the mode here

    async def run(self):
        self.dial.start()
        self.audio_player.play(self.urls[self.current_index])

        try:
            while True:
                await asyncio.sleep(0.1)

                direction = self.dial.get_direction()
                if direction != 0:
                    print(f"↪️ Dial turned: {'left' if direction > 0 else 'right'}")
                    self.next_url(direction)

                if self.dial.get_button():
                    print("🖲️ Button pressed!")
                    self.switch_mode()

        except KeyboardInterrupt:
            print("👋 Exiting...")
            self.audio_player.stop()
            await self.dial.stop()


if __name__ == "__main__":
    asyncio.run(App().run())
