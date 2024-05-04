# Thanks to Peter Milne!
import time
import logging
import vlc
import subprocess


# Edit these to suit your audio settings
AUDIO_CARD = 2
MIXER_CONTROL = "PCM"
# AUDIO_DEVICE = "UE BOOM 2"
AUDIO_DEVICE = "Built-in Audio Analog Stereo"
VOLUME_INCREMENT = 1


def print_audio_devices(p):
    '''Print the available audio outputs'''
    device = p.audio_output_device_enum()
    while device:
        logging.info(f"Name: {device.contents.description.decode('utf-8')}")
        logging.info(f"Device: {device.contents.device.decode('utf-8')}")
        device = device.contents.next


def get_audio(p, device_name):
    '''Get the audio output device(s) attached by name
    @Returns audio output device matching name

    For example "UE BOOM 2" for BT speaker
    or "Built-in Audio Analog Stereo" for speaker connected to audio jack
    '''
    device = p.audio_output_device_enum()
    while device:
        if device.contents.description.decode('utf-8') == device_name:
            logging.debug(f"Audio: {device.contents.description.decode('utf-8')}, {device.contents.device.decode('utf-8')}")
            return device.contents.device

        device = device.contents.next


class Streamer():
    """
    A streaming audio player using python-vlc
    This improves handling of media list (pls and m3u's) streams
    """
    def __init__(self, audio=AUDIO_DEVICE):
        logging.debug(f"Starting Streamer: {audio}")
        self.audio = audio
        self.player = vlc.MediaPlayer()
        self.volume = 80
        print_audio_devices(self.player)
        self.set_audio(audio)

    def set_audio(self, device_name):
        if isinstance(self.player, vlc.MediaListPlayer):
            player = self.player.get_media_player()
        else:
            player = self.player
        if device := get_audio(player, device_name):
            player.audio_output_device_set(None, device)
        else:
            # Use as fallback
            device = get_audio(player, "Built-in Audio Analog Stereo")
            player.audio_output_device_set(None, device)

    def play(self, url):
        playlists = set(['pls', 'm3u'])
        # playlists = set(['pls'])
        url = url.strip()
        logging.debug(f"Playing URL {url}")

        if self.player.is_playing:
            self.stop()

        # We need a different type of media instance for urls containing playlists
        extension = (url.rpartition(".")[2])[:3]
        logging.debug(f"Extension: {extension}")
        if extension in playlists:
            logging.debug(f"Creating media_list_player...")
            self.player = vlc.MediaListPlayer()
            medialist = vlc.MediaList()
            medialist.add_media(url)
            self.player.set_media_list(medialist)
        else:
            logging.debug(f"Creating media_player...")
            self.player = vlc.MediaPlayer()
            media = vlc.Media(url)
            self.player.set_media(media)

        self.player.play()
        # self.set_audio("UE BOOM 2")

    def stop(self):
        if self.player.is_playing:
            self.player.stop()

    def update_volume(self, cmd: str):
        """Set volume up or down"""
        volume = self.volume
        if cmd == "up":
            volume += VOLUME_INCREMENT
        else:  # down
            volume -= VOLUME_INCREMENT
        if volume >= 100:
            volume = 100
        elif volume <= 0:
            volume = 0
        if isinstance(self.player, vlc.MediaListPlayer):
            # Get the media play associated with this MediaListPlayer
            player = self.player.get_media_player()
        self.player.audio_set_volume(volume)
        # Unfortunately MediaListPlayer doesn't have a volume control so this is a hack
        # command = ["amixer", "sset", "-c", "{}".format(AUDIO_CARD), "{}".format(MIXER_CONTROL), "{}%".format(volume)]
        # logging.debug(f"Command: {command}")
        # subprocess.run(command)
        self.volume = volume
        logging.debug(f"Setting volume: {volume}%")


if __name__ == "__main__":
    """python python_vlc_streaming.py ../json/london-stations-test.json"""
    import sys
    import files

    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")
    logging.getLogger().setLevel(logging.DEBUG)

    clip_duration = 10

    stations_file = sys.argv[1]
    stations = files.load_stations(stations_file)

    # Get list of stations
    stations_list = []
    for k, v in stations.items():
        for v in v['urls']:
            stations_list.append(v)

    # logging.debug(stations_list)
    logging.info(f"Station list length: {len(stations_list)} URLs")

    player = Streamer()
    for i, station in enumerate(stations_list):
        url = station['url']
        logging.info(f"Playing URL {i}, {station['name']}, {url}")
        player.play(url)
        time.sleep(clip_duration)

    logging.info("End of list")
