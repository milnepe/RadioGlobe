import vlc
import logging


class AudioPlayer:
    def __init__(self):
        self.instance = vlc.Instance("--input-repeat=-1")
        self.player = self.instance.media_player_new()
        self.current_url = None

    def play(self, city, station: tuple):
        """Play a new URL stream, stopping current playback if needed."""
        if self.player.is_playing():
            self.player.stop()

        self.current_url = station[1]
        media = self.instance.media_new(self.current_url)
        self.player.set_media(media)
        self.player.play()
        logging.debug(f"🔊 Playing: {city} {station}")

    def change_volume(self, delta, min_volume=10, max_volume=100) -> int:
        """Adjust volume by delta, clamped between min and max."""
        current_volume = self.player.audio_get_volume()
        new_volume = max(min_volume, min(max_volume, current_volume + delta))
        self.player.audio_set_volume(new_volume)
        logging.debug(f"🔉 Volume changed: {current_volume} -> {new_volume}")
        return new_volume

    def change_volume_level(self, level: int) -> int:
        """Adjust volume to set level."""
        current_volume = self.player.audio_get_volume()
        self.player.audio_set_volume(level)
        logging.debug(f"🔉 Volume changed: {current_volume} -> {level}")
        return level

    def stop(self):
        """Stop playback if something is playing."""
        if self.player.is_playing():
            self.player.stop()
