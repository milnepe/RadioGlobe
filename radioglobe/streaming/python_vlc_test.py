'''Find and Test attached audio devices with python-vlc
   https://www.olivieraubert.net/vlc/python-ctypes/doc/vlc-module.html
'''
import vlc
import time
import logging


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

    For example "UE BOOM 2" for BT speaker
    or "Built-in Audio Analog Stereo" for speaker connected to audio jack
    '''
    device = p.audio_output_device_enum()
    while device:
        if device.contents.description.decode('utf-8') == device_name:
            logging.debug(f"Audio: {device.contents.description.decode('utf-8')}, {device.contents.device.decode('utf-8')}")
            return device.contents.device

        device = device.contents.next


if __name__ == "__main__":
    '''Test your audio output

    If you have a "UE BOOM 2" BT speaker attached it will play through that as first choice,
    but will "fallback" to a speaker attached to the built-in audio jack.

    run: python test.py'''

    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")
    logging.getLogger().setLevel(logging.DEBUG)

    print("VLC media player test...")

    url = "http://lstn.lv/bbc.m3u8?station=bbc_radio_two&bitrate=320000"
    # MediaListPlayer required to play this media list
    mlp_url = "http://142.4.215.64:8116/listen.pls?sid=1"

    # Create a MediaPlayer and set media
    p = vlc.MediaPlayer()
    m = vlc.Media(url)
    p.set_media(m)
    logging.debug(url)

    # Create a MediaListPlayer and add playlist
    mlp = vlc.MediaListPlayer()
    ml = vlc.MediaList()
    ml.add_media(mlp_url)
    mlp.set_media_list(ml)
    logging.debug(mlp_url)

    # List attached audio devices
    print_audio_devices(p)

    # Play test urls
    players = [p, mlp]
    for p in players:
        p.play()

        if isinstance(p, vlc.MediaListPlayer):
            # Get the media play associated with this MediaListPlayer
            p = p.get_media_player()

        # Set primary audio output
        if device := get_audio(p, "UE BOOM 2"):
            p.audio_output_device_set(None, device)
        else:
            # Use as fallback
            device = get_audio(p, "Built-in Audio Analog Stereo")
            p.audio_output_device_set(None, device)

        # Increase volume gradually
        for v in range(50, 90, 10):
            p.audio_set_volume(v)
            time.sleep(2)
        p.stop()
        time.sleep(1)

    exit()
