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
        self.mp = vlc.MediaPlayer()
        self.mlp = vlc.MediaListPlayer()
        print_audio_devices(self.mp)
        self.p = self.mp  # Cache current player
        self.v = 80  # Volume cache
        logging.debug(f"MediaPlayer player ID: {id(self.mp)}")
        logging.debug(f"MediaListPlayer player ID: {id(self.mlp.get_media_player())}")
        logging.debug(f"Current player ID: {id(self.p)}")

    def stop(self):
        '''Force a stop'''
        if self.mp:
            self.mp.stop()
        if self.mlp:
            self.mlp.stop()

    def play(self, url):
        playlists = ('m3u', 'pls')
        url = url.strip()
        # We need a different type of media instance for urls containing playlists
        extension = (url.rpartition(".")[2])[:3]
        logging.debug(f"URL extension: {extension}")

        if extension in playlists:
            self.p = self.mlp  # Cache player
            # self.mlp.set_media_player(self.mp)  # Use MediaPlayer!
            ml = vlc.MediaList()
            ml.add_media(url)
            self.mlp.set_media_list(ml)
            logging.debug(f"MediaListPlayer ID: {id(self.p)}, {url}")
        else:
            self.p = self.mp
            m = vlc.Media(url)
            self.mp.set_media(m)
            logging.debug(f"MediaPlayer ID: {id(self.p)}, {url}")

        self.stop()  # Must stop before moving on
        self.p.play()

    def set_volume(self, vol):
        if self.v != vol:
            if isinstance(self.p, vlc.MediaListPlayer):
                p = self.mlp.get_media_player()
            else:
                p = self.p
            logging.debug(f"Player ID: {id(p)}, Volume: {p.audio_get_volume()}")
            p.audio_set_volume(vol)
            self.v = vol


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
