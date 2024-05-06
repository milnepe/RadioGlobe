#! /usr/bin/bash

# Install all dependencies and setup radioglobe service to run under default user

sudo apt install vlc-bin vlc-plugin-base python3-venv python3-dev pulseaudio-module-bluetooth
# sudo apt install vlc pulseaudio python3-pip python3-smbus python3-dev python3-rpi.gpio

# Create python virtual environment and activate it so python packages can be installed in it
echo "Creating virtual environment..."
python -m venv venv
source ./venv/bin/activate

# Install python dependencies
pip install spidev
pip install smbus
pip install python-vlc
pip install https://github.com/pl31/python-liquidcrystal_i2c/archive/master.zip

# Install appropriate GPIO support
source /etc/os-release
echo "$VERSION_CODENAME"
case $VERSION_CODENAME in
    bullseye)
    # Legacy support
    pip install RPi.GPIO
    ;;
    bookworm)
    # Bookworm compatibility with RPi.GPIO
    pip install lgpio
    pip install rpi-lgpio
    ;;
    *)
    echo "Debian version unknown"
    exit
    ;;
esac

# Remove any old radioglobe service
FILE=/etc/systemd/system/radioglobe.service
if [[ -f "$FILE" ]]; then
    sudo systemctl stop radioglobe.service
    sudo systemctl disable radioglobe.service
    sudo systemctl daemon-reload
    sudo rm $FILE
fi

# Set paths according to username
sed -i "s/USER/${USER}/g" services/radioglobe.service
# Start radioglobe as the default user, NOT root so pulseaudio can manage audio
sudo cp services/radioglobe.service /etc/systemd/user/
systemctl --user daemon-reload
systemctl --user enable pulseaudio
systemctl --user enable radioglobe.service
systemctl --user start pulseaudio

sudo reboot

