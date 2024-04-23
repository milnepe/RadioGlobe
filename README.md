# Radioglobe
First, install Raspberry Pi OS Bookworm (recommended) or Bullseye (legacy) onto a 16MB microSD card and make sure you have a working OS.

If using Raspberry Pi Imager use the configure cog to set SSH ON and set your default user/password. 

If flashing the OS manually, you will need to add a couple of configuration files to setup SSH and configure the username / password:
1. Insert the microSD card containing the Raspberry Pi OS installation into a Mac or PC.
2. Open the 'BOOT' volume in My Computer (Windows), Files (Ubuntu) or Finder (macOS).
3. Create a new text file and name it "ssh".  On Windows, don't forget to remove the file extension (.txt).
4. Alternatively in Linux or macOS cd to the 'BOOT' volume and run `touch ssh`
5. Add a file named `userconf.txt` containing a single line with username:encrypted-password - for more details see `https://www.raspberrypi.com/documentation/computers/configuration.html#setting-up-a-headless-raspberry-pi`
6. Unmount the microSD card and insert it into the Raspberry Pi.
7. Plug the Raspberry Pi into your router using an Ethernet cable and power it on.
8. Allow it time to fully boot up. Once it has booted, open an SSH session on your PC. (You can use cmd on Windows, or a terminal on MacOS or Linux) run `ssh username@raspberrypi.local` (replace `username` with your default user and `raspberrypi` with your hostname if you changed it).

## Update system
Once you are in the SSH session update the system and perform a reboot before installing the RadioGlobe software. Fix any issues before proceeding.
1. Run `sudo apt update`
2. Run `sudo apt upgrade`
3. Run `sudo reboot`

Now SSH in again.

## Installation
For initial tests we recommend connecting to your network with an Ethernet cable. WiFi can be configured once everything is tested.

The installer supports Bookworm and Bullseye OS versions.

The install script no longer relies on username pi. It will install the Python scripts into your default users home directory and configure the systemd services according to your chosen username.

From an SSH terminal:
1. Run `sudo raspi-config`
2. In 'Interfacing Options' enable SPI and I2C.
3. Install git: `sudo apt install git`
4. Make sure you are in your home home directory: `cd ~`
5. Clone the software by running `git clone https://github.com/DesignSparkrs/RadioGlobe.git`
6. Change into the RadioGlobe dir `cd RadioGlobe`
7. Run the install script to install dependencies and setup the services `./install.sh`
At this point the RadioGlobe should start automatically.

## Upgrading
1. From users home directory copy the current installation so you can restore if necessary
```
$ cd ~
$ cp RadioGlobe RadioGlobe.old
```
2. Follow installation instructions above. The installer supports Bookworm and Bullseye OS versions.

## Calibration
1. When starting for the first time the RadioGlobe encoders need to be calibrated. Set the reticule cross-hairs to the intersection of the 0 latitude and 0 longitude lines then press and hold the middle button until the LED flashes Green and the display shows "Calibrated".

The system will retain the calibration for future reboots or you can calibrate it at any time. 

## WiFi
Use `raspi-config` from an SSH session to configure WiFi once everything is working.

1. If you want to use WiFi, go to 'Localisation Options', then 'Enter WLAN Country' where you can select your country.
   HINT: United Kingdom is GB!  Press Esc to return to the main menu then go to 'Network Options' > 'Wireless LAN' and
   enter your SSID (network name) and WiFi password.

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
Once the default card is set you should hear 'pink noise' by running `speaker-test` which will output to the default card. Use Ctl-C to exit

5. Set debugging on in `radio_config.py` and follow the journal - note there are pulse errors which can be ignored:
```
$ sudo journalctl -u radioglobe.service -f
```
6. Turn it off and on again :) - use `sudo poweroff`

