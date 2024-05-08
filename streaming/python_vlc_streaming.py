# Thanks to Peter Milne!
import time
import logging
import vlc


def print_audio_devices(p):
    '''Print the available audio outputs'''
    if isinstance(p, vlc.MediaListPlayer):
        p = p.get_media_player()
    device = p.audio_output_device_enum()
    logging.info("Audio devices available")
    while device:
        logging.info(f"Name: {device.contents.description.decode('utf-8')}, Device: {device.contents.device.decode('utf-8')}")
        device = device.contents.next


class Streamer:
    '''Streamer that handles audio media and playlists'''
    def __init__(self):
        self.player = None  # Cache current player
        self.volume = 80  # Volume cache

    def set_player(self, url):
        playlists = ('m3u', 'pls')
        url = url.strip()
        extension = (url.rpartition(".")[2])[:3]
        logging.debug(f"URL extension: {extension}")

        try:
            # We need a different type of media instance for urls containing playlists
            if extension in playlists:
                self.player = vlc.MediaListPlayer()
                medialist = vlc.MediaList()
                medialist.add_media(url)
                self.player.set_media_list(medialist)
                logging.debug(f"MediaListPlayer ID: {id(self.player)}, {url}")
            else:
                self.player = vlc.MediaPlayer()
                media = vlc.Media(url)
                self.player.set_media(media)
                logging.debug(f"MediaPlayer ID: {id(self.player)}, {url}")
        except (AttributeError, NameError) as e:
            logging.debug('%s: %s (%s %s vs LibVLC %s)' % (e.__class__.__name__, e,
                                                           sys.argv[0], __version__,
                                                           libvlc_get_version()))

    def stop(self):
        if self.player:
            self.player.stop()

    def play(self, url):
        self.stop()  # Must stop existing player first
        self.set_player(url)
        self.player.play()

    def set_volume(self, volume):
        if self.volume != volume:
            if isinstance(self.player, vlc.MediaListPlayer):
                player = self.player.get_media_player()
            else:
                player = self.player
            logging.debug(f"Player ID: {id(player)}, Volume: {player.audio_get_volume()}")
            player.audio_set_volume(volume)
            self.volume = volume

    def get_volume(self):
        return self.volume


if __name__ == "__main__":
    """venv/bin/python streaming/python_vlc_streaming.py json/london-stations-test.json"""
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
