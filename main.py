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

python modules:
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
from gpiozero import Button, OutputDevice, RotaryEncoder
import mpv
from datetime import datetime
from i2c_dev import Lcd
from radio_list import RADIO

# Config ################################################################################
AUDIO_DEVICE = 'alsa/hw:CARD=sndrpihifiberry'  # to check hw devices -> aplay -L
SAVED_STATION = 'last_station.txt'  # save last opened station
PIN_BTN_ROTARY = 25
PIN_ROTARY_DT = 5      # Momentary encoder A  TODO: what is the DT and CLK?
PIN_ROTARY_CLK = 6     # Momentary encoder B
LCD_POWER_PIN = 16
LOG_LEVEL = logging.DEBUG
BTN_BOUNCE = 0.05  # Button debounce time in seconds
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

# turn on lcd
LCD_POWER = OutputDevice(LCD_POWER_PIN)
LCD_POWER.on()


def mpv_log(loglevel, component, message):
    """Log handler for the python-mpv.MPV instance"""
    LOG.warning('[python-mpv] [{}] {}: {}'.format(loglevel, component, message))


def get_saved_station(filename):
    """
    get saved RADIO index nr
    :type filename: str, file name
    :return: int, index nr to use with RADIO
    """
    try:
        with open(filename, 'r') as f:
            index = int(f.readline())
        LOG.debug(f"Retrieving saved last radio index: {index}")
    except (FileNotFoundError, BaseException):
        index = 0
        LOG.warning("Error while reading saved playlist index nr. Getting first item instead")

    return index


def save_last_station(filename, index_nr):
    """Save station RADIO index to file
    :type filename: str,file name
    :param index_nr: int, index to be used in the RADIO list
    """
    with open(filename, 'w') as f:
        f.write(str(index_nr))
    LOG.debug(f"Saved RADIO index {index_nr} to file")


# Global vars
PLAYER = mpv.MPV(log_handler=mpv_log, audio_device=AUDIO_DEVICE)
PLAYER.set_loglevel('error')
LCD = Lcd()
CURRENT_STATION = get_saved_station(SAVED_STATION)
CURRENT_PLAYING = ""
LCD_SCROLL = False
SCROLL_INDEX = 0
SCROLL_TEXT = ""
SCROLL_LOCK = time.time()
BTN_SELECT = Button(PIN_BTN_ROTARY, pull_up=True, bounce_time=BTN_BOUNCE)
BTN_ROTARY = RotaryEncoder(PIN_ROTARY_DT, PIN_ROTARY_CLK, bounce_time=BTN_BOUNCE, max_steps=len(RADIO) - 1)
BTN_ROTARY.steps = 0
SELECTOR_FLAG = False
ROTARY_DIRECTION = True  # True is clockwise
BTN_SELECT_FLAG = False
# ##########################################################################################


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
    wrap = textwrap.wrap(name, 16)
    LCD.lcd_clear()
    LCD.lcd_display_string(wrap[0], 1)
    if len(wrap) > 1:
        LCD.lcd_display_string(wrap[1], 2)


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
    :param lines: List[str] -> textwrap.wrap()
    """
    global LCD_SCROLL, SCROLL_TEXT
    LCD_SCROLL = True
    scroll_lines = []
    # concat lines except the first item (is printed on line 1)
    for i in range(1, len(lines)):
        scroll_lines.append(lines[i])
    SCROLL_TEXT = " ".join(scroll_lines)


def select_station(direction_clockwise=True):
    """
    Display the current station on lcd.
    If you the press 'radio select' button again within 3 sec
    the display will loop over the the names in RADIO and the index
    value will be set in CURRENT_STATION.
    :return: bool, True if the value of CURRENT_STATION has changed
    """
    global CURRENT_STATION, SELECTOR_FLAG, BTN_SELECT_FLAG
    SELECTOR_FLAG = False
    timestamp = time.time()
    new_station = get_next_station() if direction_clockwise else get_previous_station()
    display_radio_name(new_station[0])
    new_station_selected = True
    while time.time() - timestamp <= 3:
        if SELECTOR_FLAG:
            SELECTOR_FLAG, timestamp = False, time.time()
            new_station = get_next_station() if direction_clockwise else get_previous_station()
            display_radio_name(new_station[0])
            new_station_selected = True  # todo select by waiting 3 sec or only with select button???
        if BTN_SELECT_FLAG:
            BTN_SELECT_FLAG = False
            break

    return new_station_selected


# todo documentation
def get_current_station():
    global CURRENT_STATION
    return RADIO[CURRENT_STATION]


# todo documentation
def get_next_station():
    global CURRENT_STATION
    CURRENT_STATION = 0 if CURRENT_STATION == len(RADIO) - 1 else CURRENT_STATION + 1
    return RADIO[CURRENT_STATION]


# todo documentation
def get_previous_station():
    global CURRENT_STATION
    CURRENT_STATION = len(RADIO) - 1 if CURRENT_STATION == 0 else CURRENT_STATION - 1
    return RADIO[CURRENT_STATION]


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
        save_last_station(SAVED_STATION, CURRENT_STATION)
        LOG.info(f"Radio stream started: {url}")


def activate_station_selector(direction=True):
    global SELECTOR_FLAG, ROTARY_DIRECTION
    ROTARY_DIRECTION = direction
    SELECTOR_FLAG = True


def btn_select_handler():
    """Handler -> play next radio station"""
    global BTN_SELECT_FLAG
    BTN_SELECT_FLAG = True
    LOG.debug("Btn_select pressed {0}".format(datetime.now().strftime("%H:%M:%S")))


def btn_rotary_clockwise_handler():
    """Handler -> play next radio station"""
    activate_station_selector()
    LOG.debug(f"Rotary encoder turned clockwise. counter = {BTN_ROTARY.steps} {datetime.now().strftime('%H:%M:%S')}")


def btn_rotary_counter_clockwise_handler():
    """Handler -> play next radio station"""
    activate_station_selector(direction=False)
    LOG.debug(f"Rotary encoder turned counter clockwise. counter = {BTN_ROTARY.steps} {datetime.now().strftime('%H:%M:%S')}")


BTN_SELECT.when_pressed = btn_select_handler
BTN_ROTARY.when_rotated_clockwise = btn_rotary_clockwise_handler
BTN_ROTARY.when_rotated_counter_clockwise = btn_rotary_counter_clockwise_handler

play_radio(get_current_station()[1])
display_radio_name(get_current_station()[0])
while True:
    try:
        if BTN_SELECT_FLAG:
            BTN_SELECT_FLAG = False
            display_radio_name(get_current_station()[0])

        if SELECTOR_FLAG:
            LCD_SCROLL, SCROLL_TEXT, CURRENT_PLAYING = False, "", ""

            station_changed = select_station(ROTARY_DIRECTION)
            if station_changed:
                play_radio(RADIO[CURRENT_STATION][1])

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

    except (KeyError, TypeError):
        # KeyError or TypeError could be triggered when 'icy-title' doesn't exist (or no station is playing)
        pass
    except mpv.ShutdownError:
        LOG.error("ShutdownError from mpv")
        exit_program()

    time.sleep(0.001)  # 10 times less cpu usage
