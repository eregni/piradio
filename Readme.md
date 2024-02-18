# Piradio
---
## Description  
Script to play radio streams on a raspberrypi, pimped with an "audiophonics sabre dac" audio card.  
The radio is controlled by two buttons: 1 Rotary encoder with push button to select stations, and one push button to start/stop the radio.  
An 16x2 lcd-display is used to show the radio name and track information.  
The script runs as a systemd service.

Useful sources:
- arch arm config: https://archlinuxarm.org/platforms/armv7/broadcom/raspberry-pi-2  
- run [gpio as non-root](https://arcanesciencelab.wordpress.com/2016/03/31/running-rpi3-applications-that-use-gpio-without-being-root/)
- radio stream url's: https://hendrikjansen.nl/henk/streaming1.html#wl
- python-mpv: https://github.com/jaseg/python-mpv
- audiophonics sabre dac v3: https://www.audiophonics.fr/en/index.php?controller=attachment&id_attachment=208
THERE IS AN ERROR WITH THE NUMBERING OF THE PINS IN THE DAC DOCUMENTATION.
HALFWAY, IT SWITCHES FROM BCM TO PHYSICAL PIN NUMBERING  
the dac occupies the following rpi pins (bcm numbering):
4, 17, 22 (software shutdown, button shutdown, bootOk) 18, 19, 21 (dac audio, DOCUMENTATION REFERS TO PHYSICAL PIN NRS 12, 35, 40)

Hardware:
gpio buttons:  
 - Rotary encoder with a push button ["Bourns PEC11R-4015F-S0024"](https://datasheet.octopart.com/PEC11R-4015F-S0024-Bourns-datasheet-68303416.pdf). The rotary encoder is used to select radio stations.  
 - NO push button to toggle the radio on/off. 
 - 16x2 lcd screen to display radio station names and icecast-info.

## SETUP:
The raspberrypi needs following packages (arch linux):
- mpv
- alsa-utils
- python-raspberry-gpio (from AUR -> yay is a useful program to install aur packages)
- lm_sensors
- i2c-tools

python modules:
- python-mpv
- gpiozero
- smbus

gpio permissions:  
    create file '99-gpio.rules' in /etc/udev/rules.d/ and add following config:  
```
SUBSYSTEM=="bcm2835-gpiomem", KERNEL=="gpiomem", GROUP="gpio", MODE="0660"
SUBSYSTEM=="gpio", KERNEL=="gpiochip*", ACTION=="add", PROGRAM="/bin/sh -c 'chown root:gpio /sys/class/gpio/export /sys/class/gpio/unexport ; chmod 220 /sys/class/gpio/export /sys/class/gpio/unexport'"
SUBSYSTEM=="gpio", KERNEL=="gpio*", ACTION=="add", PROGRAM="/bin/sh -c 'chown root:gpio /sys%p/active_low /sys%p/direction /sys%p/edge /sys%p/value ; chmod 660 /sys%p/active_low /sys%p/direction /sys%p/edge /sys%p/value'"
```

drivers:
- enable spi/i2c: "device_tree_param=spi=on"/"dtparam=i2c_arm=on" -> /boot/config.txt
enable sabre dac: "dtoverlay=hifiberry-dac" -> /boot/config.txt

The user running the piradio service needs to be added in group 'gpio' and 'audio' group

i2c group and permission settings ([source](https://arcanesciencelab.wordpress.com/2014/02/02/bringing-up-i2c-on-the-raspberry-pi-with-arch-linux/))
```
    # groupadd i2c
    # usermod -aG i2c [username]
    # echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c"' >> /etc/udev/rules.d/raspberrypi.rules
```

Check the 'config.py' file and change parameters where necessary.  
Test the script by running 'main.py'.  
Enable the service after successful test.  
The file 'models/stations.py' contains the list of selectable radio stations.

## OPTIONAL
i2c speed: dtparam=i2c_arm=on,i2c_arm_baudrate=400000 -> /boot/config.txt

atexit module catches SIGINT.
You need to specify the kill signal in the systemd service since it sends by default SIGTERM -> KillSignal=SIGINT