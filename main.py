#!/usr/bin/python3
"""
Script to play radio streams on a raspberrypi pimped with an audiophonics sabre dac v3
Controlled by two buttons. 1 to play next station and 1 to start/stop playing
It should be runned as a systemd service.
A small display is used to show the current played track.

Usefull sources:
    arch arm config: https://archlinuxarm.org/platforms/armv7/broadcom/raspberry-pi-2
    run gpio as non-root: https://arcanesciencelab.wordpress.com/2016/03/31/running-rpi3-applications-that-use-gpio-without-being-root/
    radio stream url's: https://hendrikjansen.nl/henk/streaming1.html#wl
    python-mpv: https://github.com/jaseg/python-mpv
    audiophonics sabre dac v3: https://www.audiophonics.fr/en/index.php?controller=attachment&id_attachment=208
        THERE IS AN ERROR WITH THE NUMBERING OF THE PINS IN THE DAC DOCUMENTATION.
        HALFWAY, IT SWITCHES FROM BCM TO PHYSICAL PIN NUMBERING
        the dac occupies the following rpi pins (bcm numbering):
            4, 17, 22 (software shutdown, button shutdown, bootOk)
            18, 19, 21 (dac audio, DOCUMENTATION REFERS TO PHYSICAL PIN NRS 12, 35, 40)

SET-UP
The raspberrypi needs following packages (arch linux):
    mpv
    alsa-utils
    python-raspberry-gpio (from AUR -> yay is a usefull program to install aur packages)
    lm_sensors
    i2c-tools

python modules (use pip to install):
    python-mpv
    gpiozero
    smbus

gpio permissions:
    create file '99-gpio.rules' in /etc/udev/rules.d/ and add following config:
    SUBSYSTEM=="bcm2835-gpiomem", KERNEL=="gpiomem", GROUP="gpio", MODE="0660"
    SUBSYSTEM=="gpio", KERNEL=="gpiochip*", ACTION=="add", PROGRAM="/bin/sh -c 'chown root:gpio /sys/class/gpio/export /sys/class/gpio/unexport ; chmod 220 /sys/class/gpio/export /sys/class/gpio/unexport'"
    SUBSYSTEM=="gpio", KERNEL=="gpio*", ACTION=="add", PROGRAM="/bin/sh -c 'chown root:gpio /sys%p/active_low /sys%p/direction /sys%p/edge /sys%p/value ; chmod 660 /sys%p/active_low /sys%p/direction /sys%p/edge /sys%p/value'"
    add user to (new) group 'gpio'

drivers:
    enable spi/i2c: "device_tree_param=spi=on"/"dtparam=i2c_arm=on" -> /boot/config.txt
    enable sabre dac: "dtoverlay=hifiberry-dac" -> /boot/config.txt

the user needs to be in the 'audio' group

i2c group and permission settings (https://arcanesciencelab.wordpress.com/2014/02/02/bringing-up-i2c-on-the-raspberry-pi-with-arch-linux/)
    # groupadd i2c
    # usermod -aG i2c [myusername]
    # echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c"' >> /etc/udev/rules.d/raspberrypi.rules
"""
# todo solder transistor to control the power supply of the lcd

import logging
import atexit
import time
from sys import exit
import textwrap

from gpiozero import Button
import mpv
from datetime import datetime
from i2c_dev import Lcd

# Config ################################################################################
AUDIO_DEVICE = 'alsa/default:CARD=sndrpihifiberry'
RADIO = (
        'http://icecast.vrtcdn.be/radio1.aac',
        'http://icecast.vrtcdn.be/radio1_classics.aac',
        'http://icecast.vrtcdn.be/ra2ant.aac',
        'http://icecast.vrtcdn.be/klara.aac',
        'http://icecast.vrtcdn.be/klaracontinuo.aac',
        'https://radios.rtbf.be/laprem1ere-128.mp3',  # aac not available in 128 bit quality for now
        'https://radios.rtbf.be/musiq3-128.aac',
        'http://progressive-audio.lwc.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'
)
SAVED_STATION = 'last_station.txt'
BTN1_PIN = 25
BTN2_PIN = 24
# End config ################################################################################

# Logging config ##############################################################################
LOG_LEVEL = logging.DEBUG
LOG_FORMATTER = logging.Formatter(
    fmt='[%(asctime)s.%(msecs)03d] [%(module)s] %(levelname)s: %(message)s',
    datefmt='%D %H:%M:%S',
)
LOG_FORMATTER.default_msec_format = '%s.%03d'
LOG_HANDLER_FILE = logging.FileHandler(filename='piradio.log')
LOG_HANDLER_FILE.setFormatter(LOG_FORMATTER)
LOG_HANDLER_FILE.setLevel(LOG_LEVEL)
# todo stream logger not printing to console
LOG_HANDLER_CONSOLE = logging.StreamHandler()
LOG_HANDLER_CONSOLE.setFormatter(LOG_FORMATTER)
LOG_HANDLER_CONSOLE.setLevel(LOG_LEVEL)
LOG = logging.getLogger()
LOG.addHandler(LOG_HANDLER_FILE)
LOG.setLevel(LOG_LEVEL)
# End logging config #######################################################################


def mpv_log(loglevel, component, message):
    """Log handler for the python-mpv.MPV instance"""
    LOG.debug('[python-mpv] [{}] {}: {}'.format(loglevel, component, message))


PLAYER = mpv.MPV(log_handler=mpv_log, audio_device=AUDIO_DEVICE)
PLAYER.set_loglevel('error')
LCD = Lcd()


def lcd_update(text: str) -> None:
    """
    Send metadata to lcd screen
    :param text: str to display on lcd. If the string is longer than 16 chars if will be wrapped upon two lines
    """
    text = textwrap.wrap(text, 16)
    LCD.lcd_clear()
    try:
        LCD.lcd_display_string(text[0], 1)
        if len(text) > 1:
            LCD.lcd_display_string(text[1], 2)
    except IndexError:
        LOG.warning("Problem while sending text to the lcd screen")


def get_saved_station() -> int:
    """
    get saved playlist index nr
    :return: int: index nr
    """
    try:
        with open(SAVED_STATION, 'r') as f:
            index = int(f.readline())
        LOG.debug("Retrieving saved index nr: {}".format(index))
    except (FileNotFoundError, BaseException):
        index = 0
        LOG.warning("Error while reading saved playlist index nr. "
                    "Getting first item in playlist instead")

    return index

# todo: use constants instead of parameters. (No OO programing here)
def save_last_station(player: mpv.MPV) -> None:
    """
    Save station playlist index to file
    :param player: python-mpv MPV instance
    """
    with open(SAVED_STATION, 'w') as f:
        f.write(str(player.playlist_current_pos))
    LOG.debug("Saved station playlist index to file")


def signal_exit_program():
    """
    handler for atexit
    """
    LOG.info("Atexit handler triggered. Exit program")
    LCD.lcd_clear()
    PLAYER.stop()
    PLAYER.quit()
    exit(0)

# Todo: button handling
def btn_toggle_handler():
    LOG.debug("Btn toggle pressed at {0}".format(datetime.now().strftime("%H:%M:%S")))
    # playing = not playing
    # player.playlist_play_index(player.playlist_current_pos) if not playing else player.stop()


def btn_next_handler():
    LOG.debug("Btn next pressed {0}".format(datetime.now().strftime("%H:%M:%S")))
    # player.playlist_next()
    # save_last_station(player)


atexit.register(signal_exit_program)

LOG.info("start radio")
btn_toggle = Button(BTN1_PIN, pull_up=True, bounce_time=0.1)
btn_toggle.when_pressed = btn_toggle_handler
btn_next = Button(BTN2_PIN, pull_up=True, bounce_time=0.1)
btn_next.when_pressed = btn_next_handler

PLAYER.playlist_clear()
PLAYER.loop_playlist = True
for url in RADIO:
    PLAYER.playlist_append(url)

PLAYER.playlist_play_index(get_saved_station())
playing = True
current_station = ""
current_playing = ""
lcd_lock = time.time()

while True:
    try:
        # todo scroll text if necessary
        if playing and current_station != PLAYER.metadata['icy-name']:
            current_station =PLAYER.metadata['icy-name']
            LOG.debug(f"New icy-name: {current_station}")
            lcd_update(current_station)
            lcd_lock = time.time()
        elif playing and current_playing != PLAYER.metadata['icy-title'] and time.time() - lcd_lock > 5:
            current_playing = PLAYER.metadata['icy-title']
            LOG.debug(f"New icy-title: {current_playing}")
            lcd_update(current_playing)
    except (TypeError, KeyError):
        LOG.debug("No (icy) metadata available")
    except mpv.ShutdownError:
        LOG.debug("ShutdownError")
        LCD.lcd_clear()
        exit(0)

    time.sleep(0.001)  # 10 times less cpu usage
