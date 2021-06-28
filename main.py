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
    # usermod -aG i2c [username]
    # echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c"' >> /etc/udev/rules.d/raspberrypi.rules

i2c speed
    dtparam=i2c_arm=on,i2c_arm_baudrate=400000 -> /boot/config.txt

atexit module catches SIGINT. You need to specify the kill signal in the systemd service since it sends by default SIGTERM
    -> KillSignal=SIGINT
"""
import logging
from logging.handlers import RotatingFileHandler
import atexit
import time
from sys import exit
import textwrap
from gpiozero import Button, OutputDevice
import mpv
from datetime import datetime
from i2c_dev import Lcd

# Config ################################################################################
# List with radio station: Tuples with name as it should appear on the lcd screen + URL
RADIO = (
    ('Radio 1', 'http://icecast.vrtcdn.be/radio1.aac'),
    ('Radio 1 Classics', 'http://icecast.vrtcdn.be/radio1_classics.aac'),
    ('Radio 2', 'http://icecast.vrtcdn.be/ra2ant.aac'),
    ('Klara', 'http://icecast.vrtcdn.be/klara.aac'),
    ('Klara Continuo', 'http://icecast.vrtcdn.be/klaracontinuo.aac'),
    ('La premiere', 'https://radios.rtbf.be/laprem1ere-128.mp3'),  # aac not available in 128 bit quality for now
    ('Musique 3', 'https://radios.rtbf.be/musiq3-128.aac'),
    ('Vrt NWS', 'http://progressive-audio.lwc.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'),
    ('Venice Classic radio', 'https://uk2.streamingpulse.com/ssl/vcr1')
)
AUDIO_DEVICE = 'alsa/default:CARD=sndrpihifiberry'
SAVED_STATION = 'last_station.txt'  # save last opened station
BTN1_PIN = 25
LCD_POWER_PIN = 16
LOG_LEVEL = logging.INFO
# End config ################################################################################

# Logging config ############################################################################
LOG_FORMATTER = logging.Formatter(
    fmt='[%(asctime)s.%(msecs)03d] [%(module)s] %(levelname)s: %(message)s',
    datefmt='%D %H:%M:%S',
)
LOG_FORMATTER.default_msec_format = '%s.%03d'
LOG_HANDLER_FILE = RotatingFileHandler(filename='piradio.log', maxBytes=2000, backupCount=1)
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


# turn on lcd
LCD_POWER = OutputDevice(LCD_POWER_PIN)
LCD_POWER.on()

# Global vars
PLAYER = mpv.MPV(log_handler=mpv_log, audio_device=AUDIO_DEVICE)
PLAYER.set_loglevel('error')
LCD = Lcd()
CURRENT_STATION = 0
CURRENT_PLAYING = ""
LCD_SCROLL = False
SCROLL_INDEX = 0
SCROLL_TEXT = ""
SCROLL_LOCK = time.time()
BTN_NEXT = Button(BTN1_PIN, pull_up=True, bounce_time=0.05)
SELECTOR_FLAG = False
# ##########################################################################################


def get_saved_station():
    """
    get saved playlist index nr
    :return: int: index nr to use with RADIO
    """
    try:
        with open(SAVED_STATION, 'r') as f:
            index = int(f.readline())
        LOG.debug(f"Retrieving saved last radio: {RADIO[index][0]}")
    except (FileNotFoundError, BaseException):
        index = 0
        LOG.warning("Error while reading saved playlist index nr. Getting first item in playlist instead")

    return index


def save_last_station():
    """Save station playlist index to file"""
    with open(SAVED_STATION, 'w') as f:
        f.write(str(CURRENT_STATION))
    LOG.debug("Saved station playlist index to file")


@atexit.register
def exit_program():
    """handler for atexit -> stop mpv player. clear lcd screen"""
    line = "#" * 75
    LOG.info(f"Atexit handler triggered. Exit program\n{line}\n")
    LCD.lcd_clear()
    LCD_POWER.off()
    PLAYER.stop()
    PLAYER.terminate()
    exit(0)


def display_radio_name(name):
    """
    Display radio name on lcd
    :param name: string to display
    """
    LCD.lcd_clear()
    LCD.lcd_display_string(name, 1)
    LOG.debug(f"New station: {name}")


def display_icy_title(title):
    """
    Display icy-title on lcd. Activate scrolling when there are more than 2 lines to be displayed
    :param title: string title to display
    """
    lines = textwrap.wrap(title, 16)
    LCD.lcd_clear()
    LCD.lcd_display_string(lines[0], 1)
    LOG.debug(f"New icy-title: {title}")
    if len(lines) == 2:
        LCD.lcd_display_string(lines[1], 2)
    elif len(lines) > 2:
        set_up_scrolling(lines)


def set_up_scrolling(lines):
    """Activate scrolling and set up the SCROLL_TEXT
    :type lines: List[str] -> textwrap.wrap()
    """
    global LCD_SCROLL, SCROLL_TEXT
    LCD_SCROLL = True
    scroll_lines = []
    # concat lines except the first item (is printed on line 1)
    for i in range(1, len(lines)):
        scroll_lines.append(lines[i])
    SCROLL_TEXT = " ".join(scroll_lines)


def select_new_station():
    """
    Display the current station on lcd.
    If you the select button again the display will loop over the the names in RADIO.
    """
    global CURRENT_STATION
    current_selection = CURRENT_STATION
    display_radio_name(RADIO[CURRENT_STATION][0])
    CURRENT_STATION = 0 if CURRENT_STATION == len(RADIO) - 1 else CURRENT_STATION + 1
    while time.time() - SELECTOR_FLAG <= 3:
        if current_selection != CURRENT_STATION:
            display_radio_name(RADIO[CURRENT_STATION][0])


def btn_next_handler():
    """Handler -> play next radio station"""
    global SELECTOR_FLAG
    SELECTOR_FLAG = True
    LOG.debug("Btn_next pressed {0}".format(datetime.now().strftime("%H:%M:%S")))


def play_radio(url):
    """
    Start playing url. Display error message when PLAYER is still idle after 10 seconds
    :param url: str
    """
    timestamp = time.time()
    PLAYER.play(url)
    while PLAYER.core_idle:
        if time.time() - timestamp >= 10:
            LOG.error("Cannot start radio")
            LCD.lcd_display_string("ERROR: cannot", 1)
            LCD.lcd_display_string("start playing", 2)
            break

    if not PLAYER.core_idle:
        LOG.info(f"Radio stream started: {url}")


BTN_NEXT.when_pressed = btn_next_handler
LCD.lcd_display_string(RADIO[CURRENT_STATION][0], 1)
play_radio(RADIO[CURRENT_STATION][1])
time.sleep(2)  # leave the radio name for 2 sec
while True:
    try:
        if SELECTOR_FLAG:
            SELECTOR_FLAG = False
            LCD_SCROLL, SCROLL_TEXT, CURRENT_PLAYING = False, "", ""
            selector = time.time()
            currently_selected = CURRENT_STATION
            display_radio_name(RADIO[CURRENT_STATION][0])
            while time.time() - selector <= 3:
                if SELECTOR_FLAG:
                    SELECTOR_FLAG, selector = False, time.time()
                    CURRENT_STATION = 0 if CURRENT_STATION == len(RADIO) - 1 else CURRENT_STATION + 1
                    display_radio_name(RADIO[CURRENT_STATION][0])

            if CURRENT_STATION != currently_selected:
                PLAYER.play(RADIO[CURRENT_STATION][1])
                PLAYER.wait_until_playing()
                save_last_station()
                SELECTOR_FLAG = 0

        if LCD_SCROLL and time.time() - SCROLL_LOCK > 0.5:
            SCROLL_LOCK = time.time()
            if SCROLL_INDEX == 0 or SCROLL_INDEX == len(SCROLL_TEXT) - 16:
                # add two seconds delay at start and end of the text line. Otherwise it's harder to read
                SCROLL_LOCK += 2
            LCD.lcd_display_string(SCROLL_TEXT[SCROLL_INDEX: SCROLL_INDEX + 16], 2)
            SCROLL_INDEX = 0 if SCROLL_INDEX >= len(SCROLL_TEXT) - 16 else SCROLL_INDEX + 1

        if CURRENT_PLAYING != PLAYER.metadata['icy-title']:
            LCD_SCROLL, SCROLL_TEXT = False, ""
            CURRENT_PLAYING = PLAYER.metadata['icy-title']
            if CURRENT_PLAYING != "":
                display_icy_title(CURRENT_PLAYING)

    except KeyError:
        # KeyError could be triggered when 'icy-title' doesn't exists (no station is playing)
        pass
    except mpv.ShutdownError:
        LOG.error("ShutdownError from mpv")
        exit_program()

    time.sleep(0.001)  # 10 times less cpu usage
