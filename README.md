# RadioGlobe
RadioGlobe is an internet radio player originally by Jude Pullen (Hey Jude), Donald Robson and Peter Milne. A globe is used to locate radio stations by moving a cursor around and scanning for stations in the area around large cities. Once a city is found, you can select playable stations from a list with the jog wheel. 

Full details of how to 3D print and build RadioGlobe were published on Instructables and DesignSpark. It runs on a Raspberry Pi and the Open Source code is written Code is written in Python  and available on GitHub. The music player is based on VLC and used pulseaudio. License is Apache License 2.0
[Instructables build](https://github.com/DesignSparkRS/RadioGlobe)
[DesignSpark articles](https://www.rs-online.com/designspark/how-to-build-a-3d-printed-radio-globe-to-tune-into-radio-stations-from-around-the-world-1)
[GitHub stable repository](https://github.com/DesignSparkRS/RadioGlobe)
[GitHub development repository](https://github.com/milnepe/RadioGlobe)

![RadioGlobe image](/img/radioglobe.webp)

## Installation
RadioGlobe python packages have been tested on a Raspberry Pi 4 model B with 2MB RAM and a speaker connected to the audio jack. Bluetooth speakers are supported, tested with a UE Boom 2.

Most of the installation is handled for you with an installation script `install.sh`. It does the bare minimum to get RadioGlobe up and running. This is in case you have a nonstandard setup. It assumes you have a working system based on Raspberry Pi OS Lite that you can SSH into remotely and can plays audio through the audio jack.

SPI and I2C interfaces are required for the electronics and setting auto-login for the default user for use with the audio. You can do this with `raspi-conf`.

If you want to use a BT speaker, you will can configure that with `bluetoothctl`.

### Step 1 - Raspberry Pi OS Lite
Get your Raspberry Pi up and running.
Flash `Raspberry Pi OS Lite Bookworm` to a 16GB SD card using Raspberry Pi Imager from the `Raspberry Pi Other` section. [Raspberry Pi OS installation](https://www.raspberrypi.com/software/) 
Note: Use `OS Customisations` to set the hostname, default user, optional WiFi, timezone and SSH access. If you don't do this here, you will have a hard time getting SSH access! 

### Step 2 - SSH access
Insert the SD card, power on the system and let the Pi connect to your network, either via an Ethernet cable (Best) or via WiFi. It can take a couple of minutes on first boot.
Use your routers admin page to find the Raspberry Pi hostname and IP address.
From your PC / Laptop (Windows / Mac / Linux) open a terminal and login remotely, for example where the default user is `pete` and the hostname is `radioglobe`:
```
ssh pete@radioglobe.local
```
[Raspberry Pi Remote Access](https://www.raspberrypi.com/documentation/computers/remote-access.html#introduction-to-remote-access)

### Step 3 - Update system
Bring your system up-to-date:
```
sudo apt update
sudo apt upgrade
sudo reboot
```

### Step 4 - raspi-config
Once logged in, open `sudo raspi-config` as root and setup the interfaces and auto-login:
1. Enable `SPI` in `Interfacing Options` - used by the encoders.
2. Enable `I2C` in `Interfacing Options` - used by the jog wheel, etc.
3. Enable `Auto Login` in `System Options`, choose `Console Auto Login` used to enable the sound system

### Step 5 - RadioGlobe download
Install Git and download the RadioGlobe source from GitHub:
```
cd ~
sudo apt install git
git clone https://github.com/DesignSparkRS/RadioGlobe
```
Or the development system:
```
git clone https://github.com/milnepe/RadioGlobe
```

### Step 6 - Run installer
The installation script `install.sh` will pull in all the software packages (quite a few) and setup a virtual environment for Python (required in Bookworm) and setup systemd services to start RadioGlobe on startup.

The startup template service `services/radioglobe.service` assumes RadioGlobe is installed into the default users home directory. If not you will need to edit the template accordingly.  

You can run the installer multiple times if you have any issues.
```
cd RadioGlobe
bash -x install.sh
```
The system will reboot after completing and if all went well RadioGlobe will start with the welcome screen.

### Step 7 - Calibration
1. When starting for the first time the RadioGlobe encoders need to be calibrated. Set the reticule cross-hairs to the intersection of the 0 latitude and 0 longitude lines then press and hold the middle button until the LED flashes `GRENN` and the display shows `Calibrated`.

The system will retain the calibration for future reboots or you can calibrate it at any time. 

### Step 8 - Play
Once calibrated, move the reticule near to a large city, for example London GB (51.51N, 0.13W). When a city is close, the LED will flash `RED` and the first station should start playing. You can change stations using the jog wheel and set the sound up or down with the `top` and `bottom` buttons. 

### Step 9 - Power off
It is important to shut the Pi down correctly so that the SD card is not corrupted. Press and hold the `Jog` wheel until the shutdown message appears, the press the `middle` button to shut down. Wait more than 10 seconds before disconnecting the power.


## Upgrading
If you have an existing system based on `Bullseye` or `Bookworm` you can try upgrading. This may not work depending on how much custom config you have on your system.
Make a copy of your `stations.json` file if you have made any custom changes to this. It can be copied back to the new installation.
Follow the above from `Step 5`.

## Bluetooth Speakers
Once RadioGlobe is working with powered speakers you can try adding `Bluetooth` speakers or headphones. These can be setup with 'bluetoothctl`:

## Configuration 




## Audio
Audio settings are now in `RadioGlobe/streaming/python_vlc_streaming.py` which uses python-vlc. Audio settings seem to move about with different OS versions so we don't try to detect the audio settings.
Edit the settings at the top of the file to suit your audio settings. On a default Raspi OS Bookworm the Headphone card is `2` and the asound.conf settings are required to make this the default alsa output device (See `Troubleshooting`) 
```
AUDIO_CARD = 2
MIXER_CONTROL = "PCM"
```

## Troubleshooting
SSH in to your device or open Terminal on the desktop.
1. Re-run the installer with -x to see any installation issues:
```
$ bash -x install.sh
```
2. Check SPI and I2C are enabled in raspi-config - this can be changed by updates!
3. Check radioglobe.service for clues: `systemctl status radioglobe.service`
4. No audio output
The default sound card is usually card 0. This may need setting to a different device depending on your setup.
List the sound card numbers with:
```
$ aplay -l
**** List of PLAYBACK Hardware Devices ****
card 0: vc4hdmi0 [vc4-hdmi-0], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: vc4hdmi1 [vc4-hdmi-1], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 2: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
  Subdevices: 7/8
  Subdevice #0: subdevice #0
  Subdevice #1: subdevice #1
  Subdevice #2: subdevice #2
  Subdevice #3: subdevice #3
  Subdevice #4: subdevice #4
  Subdevice #5: subdevice #5
  Subdevice #6: subdevice #6
  Subdevice #7: subdevice #7
```

To output audio to the headphone socket in this case, set the default to card 2
Edit or create a file `/etc/asound.conf` or `~/.asound.conf` containing the following settings according to which card you want as default, then reboot:
```
defaults.pcm.card 2
defaults.pcm.device 2
```
Once the default card is set you should hear 'pink noise' by running `speaker-test` which will output to the default card. Use Ctrl-C to exit

5. Set debugging on in `radio_config.py` and follow the journal - note there are pulse errors which can be ignored:
```
$ sudo journalctl -u radioglobe.service -f
```
6. Turn it off and on again :) - use `sudo poweroff`

