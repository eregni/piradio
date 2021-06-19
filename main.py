#!/usr/bin/python3
"""
Script to play radio streams on a raspberrypi pimped with an audiophonics sabre dac v3
Controlled by two buttons. 1 to play next station and 1 to start/stop playing
It runs as a systemd service and is started/stopped by polling a gpio pin in a separate bash script. (it's not the only pin being polled)
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

i2c speed
    dtparam=i2c_arm=on,i2c_arm_baudrate=400000 -> /boot/config.txt
"""
# todo profiling and optimization
# todo solder transistor to control the power supply of the lcd
# todo check header soldering

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
    ('Radio1', 'http://icecast.vrtcdn.be/radio1.aac'),
    ('Radio1 Classics', 'http://icecast.vrtcdn.be/radio1_classics.aac'),
    ('Radio2', 'http://icecast.vrtcdn.be/ra2ant.aac'),
    ('Klara', 'http://icecast.vrtcdn.be/klara.aac'),
    ('Klara Continuo', 'http://icecast.vrtcdn.be/klaracontinuo.aac'),
    ('La premiere', 'https://radios.rtbf.be/laprem1ere-128.mp3'),  # aac not available in 128 bit quality for now
    ('Musique 3', 'https://radios.rtbf.be/musiq3-128.aac'),
    ('Vrt NWS', 'http://progressive-audio.lwc.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3')
)
SAVED_STATION = 'last_station.txt'
BTN1_PIN = 25
# End config ################################################################################

# Logging config ############################################################################
LOG_LEVEL = logging.DEBUG
LOG_FORMATTER = logging.Formatter(
    fmt='[%(asctime)s.%(msecs)03d] [%(module)s] %(levelname)s: %(message)s',
    datefmt='%D %H:%M:%S',
)
LOG_FORMATTER.default_msec_format = '%s.%03d'
LOG_HANDLER_FILE = logging.FileHandler(filename='piradio.log')
LOG_HANDLER_FILE.setFormatter(LOG_FORMATTER)
LOG_HANDLER_FILE.setLevel(LOG_LEVEL)
LOG_HANDLER_CONSOLE = logging.StreamHandler()
LOG_HANDLER_CONSOLE.setFormatter(LOG_FORMATTER)
LOG_HANDLER_CONSOLE.setLevel(LOG_LEVEL)
LOG = logging.getLogger()
LOG.addHandler(LOG_HANDLER_FILE)
if LOG_LEVEL == logging.DEBUG:
    LOG.addHandler(LOG_HANDLER_CONSOLE)
LOG.setLevel(LOG_LEVEL)
# End logging config #######################################################################


def mpv_log(loglevel, component, message):
    """Log handler for the python-mpv.MPV instance"""
    LOG.warning('[python-mpv] [{}] {}: {}'.format(loglevel, component, message))


# Global vars
PLAYER = mpv.MPV(log_handler=mpv_log, audio_device=AUDIO_DEVICE)
PLAYER.set_loglevel('error')
LCD = Lcd()
CURRENT_STATION = "-"  # if the icy-name is empty make the program use the name from the RADIO list
CURRENT_PLAYING = ""
LCD_LOCK = time.time()
LCD_SCROLL = False
SCROLL_INDEX = 0
SCROLL_TEXT = ""
SCROLL_LOCK = time.time()
BTN_NEXT = Button(BTN1_PIN, pull_up=True, bounce_time=0.05)
# ##########################################################################################


def get_saved_station() -> int:
    """
    get saved playlist index nr
    :return: int: index nr
    """
    try:
        with open(SAVED_STATION, 'r') as f:
            index = int(f.readline())
        LOG.info(f"Retrieving saved last radio: {RADIO[index][0]}")
    except (FileNotFoundError, BaseException):
        index = 0
        LOG.warning("Error while reading saved playlist index nr. Getting first item in playlist instead")

    return index


def save_last_station() -> None:
    """Save station playlist index to file"""
    with open(SAVED_STATION, 'w') as f:
        f.write(str(PLAYER.playlist_current_pos))
    LOG.debug("Saved station playlist index to file")


def exit_program():
    """handler for atexit -> stop mpv player. clear lcd screen"""
    line = "#" * 75
    LOG.info(f"Atexit handler triggered. Exit program\n{line}\n")
    LCD.lcd_clear()
    PLAYER.stop()
    PLAYER.terminate()
    exit(0)


def display_radio_name():
    """Display radio name"""
    global LCD_SCROLL, CURRENT_STATION
    if PLAYER.metadata['icy-name'] == '':  # some stations give an empty str
        raise KeyError
    LCD.lcd_clear()
    CURRENT_STATION = PLAYER.metadata['icy-name']
    lines = textwrap.wrap(CURRENT_STATION, 16)
    LCD.lcd_display_string(lines[0], 1)
    LOG.debug(f"New icy-name: {CURRENT_STATION}")
    if len(lines) > 1:
        LCD.lcd_display_string(lines[1], 2)  # todo scroll text when len(lines) > 2 ???


def display_icy_title():
    """Display icy-title. Activate scrolling when there are more than 2 lines to be displayed"""
    global LCD_SCROLL, SCROLL_TEXT, CURRENT_PLAYING
    LCD_SCROLL = False
    CURRENT_PLAYING = PLAYER.metadata['icy-title']
    if CURRENT_PLAYING == "":
        return
    lines = textwrap.wrap(CURRENT_PLAYING, 16)
    LCD.lcd_clear()
    LCD.lcd_display_string(lines[0], 1)
    LOG.debug(f"New icy-title: {CURRENT_PLAYING}")
    if len(lines) == 2:
        LCD.lcd_display_string(lines[1], 2)
    elif len(lines) > 2:
        set_up_scrolling(lines)


def set_up_scrolling(lines: list[str]):
    """Activate scrolling and set up the SCROLL_TEXT"""
    global LCD_SCROLL, SCROLL_TEXT
    LCD_SCROLL = True
    scroll_lines = []
    for i in range(1, len(lines)):
        scroll_lines.append(lines[i])
    SCROLL_TEXT = " ".join(scroll_lines)  # concat lines except the first item (is printed on line 1)


def display_scroll_text():
    """Display substring from SCROLL_TEXT"""
    global SCROLL_INDEX, SCROLL_TEXT
    LCD.lcd_display_string(SCROLL_TEXT[SCROLL_INDEX: SCROLL_INDEX + 16], 2)
    SCROLL_INDEX = 0 if SCROLL_INDEX >= len(SCROLL_TEXT) - 16 else SCROLL_INDEX + 1


def btn_next_handler():
    """Handler -> play next radio station"""
    global CURRENT_STATION
    LOG.debug("Btn_next pressed {0}".format(datetime.now().strftime("%H:%M:%S")))
    PLAYER.playlist_next()
    PLAYER.wait_until_playing()
    save_last_station()
    CURRENT_STATION = "-"


BTN_NEXT.when_pressed = btn_next_handler
atexit.register(exit_program)

PLAYER.playlist_clear()
PLAYER.loop_playlist = True
for item in RADIO:
    PLAYER.playlist_append(item[1])
PLAYER.playlist_play_index(get_saved_station())
PLAYER.wait_until_playing()
LOG.info("Radio stream started")


while True:
    try:
        if LCD_SCROLL and time.time() - SCROLL_LOCK > 0.5:
            SCROLL_LOCK = time.time()
            display_scroll_text()
            # add one second delay at start and end of the text line. Otherwise it's harder to read
            if SCROLL_INDEX == 0 or SCROLL_INDEX == len(SCROLL_TEXT) - 16:
                SCROLL_LOCK += 1
        if CURRENT_STATION != PLAYER.metadata['icy-name']:
            LCD_SCROLL = False
            display_radio_name()
            LCD_LOCK = time.time()
        if CURRENT_PLAYING != PLAYER.metadata['icy-title'] and time.time() - LCD_LOCK > 5:
            LCD_SCROLL = False
            display_icy_title()

    except (IndexError, KeyError):
        # no icy data. Just display the name from RADIO list if not already done so
        # IndexError could be triggered when 'icy-name' == ''
        # KeyError could be triggered when 'icy-title' doesn't exists
        if CURRENT_STATION == "-":
            CURRENT_STATION = RADIO[PLAYER.playlist_current_pos][0]
            LCD.lcd_clear()
            LCD.lcd_display_string(CURRENT_STATION, 1)
            LOG.debug(f"New station (no icy data): {CURRENT_STATION}")
    except TypeError:
        pass  # triggered when switching stations. PLAYER.metadata needs to be updated from mpv thead
    except mpv.ShutdownError:
        LOG.warning("ShutdownError")
        exit_program()

    time.sleep(0.001)  # 10 times less cpu usage
