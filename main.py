#!/usr/bin/python3
# todo use lcd_backlight function from lcd_screen
"""
Script to play radio streams on a raspberrypi, pimped with an "audiophonics sabre dac v3" audio card
Controlled by two buttons: 1 Rotary encoder with push button to select stations and one push button start/stop the radio
An 16x2 lcd-display is used to show the radio name and track information.
It runs as a systemd service.

Useful sources:
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

HARDWARE:
gpio buttons:
    There is one rotary encoder with a push button (Bourns PEC11R-4015F-S0024) and one regular push button.
    The rotary encoder is used to select radio stations and the push button to toggle the radio.
    https://datasheet.octopart.com/PEC11R-4015F-S0024-Bourns-datasheet-68303416.pdf
Lcd screen:
    A 16x2 lcd screen to display radio station names and icecast-info.

SETUP:
The raspberrypi needs following packages (arch linux):
    mpv
    alsa-utils
    python-raspberry-gpio (from AUR -> yay is a useful program to install aur packages)
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
from gpiozero import Button, OutputDevice, RotaryEncoder
import mpv
from datetime import datetime
from lcd_screen import Lcd
from radio_list import RADIO_LIST, Radio

# Config ################################################################################
AUDIO_DEVICE = 'alsa/hw:CARD=sndrpihifiberry'  # to check hw devices -> aplay -L
SAVED_STATION = 'last_station.txt'  # save last opened station
PIN_BTN_TOGGLE = 24
PIN_BTN_ROTARY = 25
PIN_ROTARY_DT = 5      # Momentary encoder DT
PIN_ROTARY_CLK = 6     # Momentary encoder CLK
LCD_POWER_PIN = 16
LOG_LEVEL = logging.INFO
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


def mpv_log(loglevel, component, message):
    """Log handler for the python-mpv.MPV instance"""
    LOG.warning('[python-mpv] [{}] {}: {}'.format(loglevel, component, message))


def get_saved_station(filename):
    """
    Get saved RADIO index nr
    @param filename: str, file name
    @return: Radio
    """
    try:
        with open(filename, 'r') as f:
            index = int(f.readline())
        LOG.debug(f"Retrieving saved last radio index: {index}")
    except (FileNotFoundError, BaseException):
        index = 0
        LOG.warning("Error while reading saved playlist index nr. Getting first item instead")

    return RADIO_LIST[index]


def save_last_station(filename, radio):
    """
    Save station RADIO index to file
    @param filename: str, file name
    @param radio: Radio
    """
    index = RADIO_LIST.index(radio)
    with open(filename, 'w') as f:
        f.write(str(index))
    LOG.debug(f"Saved RADIO index {index} to file")


@atexit.register
def exit_program():
    """handler for atexit -> stop mpv player. clear lcd screen"""
    Radio.stop()
    line = "#" * 75
    LOG.info(f"Atexit handler triggered. Exit program\n{line}\n")
    exit(0)


# Button handlers
def btn_toggle_handler():
    """Handler for the 'toggle radio' button"""
    LOG.debug("Button toggle radio pressed")
    Radio.active = not Radio.active
    Radio.start() if Radio.active else Radio.stop()


def btn_select_handler():
    """Handler for push button from rotary encoder -> play next radio station"""
    LOG.debug("Btn_select pressed {0}".format(datetime.now().strftime("%H:%M:%S")))
    ButtonPanel.btn_select_flag = True


def activate_station_selector(direction):
    """
    Activate ButtonPanel.rotary_twist_flag. Set the detected input from the rotary encoder into
    ButtonPanel.rotary_direction.
    @param direction: bool, True is clockwise, False counter-clockwise
    """
    ButtonPanel.rotary_direction = direction
    ButtonPanel.rotary_twist_flag = True


def btn_rotary_clockwise_handler():
    """Handler -> play next radio station"""
    LOG.debug(f"Rotary encoder turned clockwise. counter = {ButtonPanel.button_rotary.steps}")
    activate_station_selector(direction=True)


def btn_rotary_counter_clockwise_handler():
    """Handler -> play next radio station"""
    LOG.debug(
        f"Rotary encoder turned counter-clockwise. counter = {ButtonPanel.button_rotary.steps}")
    activate_station_selector(direction=False)
# End Button handlers


LCD_POWER = OutputDevice(LCD_POWER_PIN)
LCD_POWER.on()  # turn on lcd

# Global vars
PLAYER = mpv.MPV(log_handler=mpv_log, audio_device=AUDIO_DEVICE, ytdl=False)
PLAYER.set_loglevel('error')
LCD = Lcd()

class Radio:
    active = False
    station = get_saved_station(SAVED_STATION)
    metadata = ""

    @staticmethod
    def stop():
        """Stop the radio"""
        LOG.info("Stop player")
        LCD.clear()
        PLAYER.stop()
        ButtonPanel.disable()

    @staticmethod
    def start():
        """Start the radio"""
        LOG.info("Start player")
        ButtonPanel.enable()
        Radio.play(Radio.station)

    @staticmethod
    def select_station():
        """
        This function should be called by the rotary encoder (ButtonPanel.btn_select_flag raised).
        Display the next (or previous) station name on lcd.
        If you push the rotary encoder OR wait for 3 seconds, the current displayed station will start playing.
        new value will be set in CURRENT_STATION.
        @return: bool, True if the value of CURRENT_STATION has changed. Should only return False when the user selects the
        same station as CURRENT_STATION -> Don't start a stream if it's already playing...
        """
        timestamp = time.time()
        new_station = Radio.switch_station()
        LCD.display_radio_name(new_station.name)
        new_station_selected = True
        while time.time() - timestamp <= 3:
            if ButtonPanel.btn_select_flag:
                ButtonPanel.btn_select_flag, timestamp = False, time.time()
                new_station = Radio.switch_station()
                LCD.display_radio_name(new_station[0])
                new_station_selected = True if new_station != Radio.station else False
            if ButtonPanel.btn_select_flag:
                ButtonPanel.btn_select_flag = False
                break

        return new_station_selected

    @staticmethod
    def switch_station():
        """
        Switch station. Update Radio.station based on the value from ButtonPanel.rotary_direction
        @return: Radio from RADIO_LIST
        """
        index = RADIO_LIST.index(Radio.station)
        if ButtonPanel.rotary_direction:
            index = 0 if index == len(RADIO_LIST) - 1 else index + 1
        else:
            index = len(RADIO_LIST) - 1 if index == 0 else index - 1

        Radio.station = RADIO_LIST[index]
        return RADIO_LIST[index]

    @staticmethod
    def play(radio):
        """
        Start playing. Display error message when PLAYER is still idle after n seconds
        @param radio: Radio
        """
        timestamp = time.time()
        PLAYER.play(radio.url)
        LCD.clear()
        LCD.lcd_display_string("Tuning...", 1)
        while PLAYER.core_idle:
            if time.time() - timestamp >= 60:
                LOG.error("Cannot start radio")
                LCD.lcd_display_string("ERROR: cannot", 1)
                LCD.lcd_display_string("start playing", 2)
                break

        if not PLAYER.core_idle:
            LCD.display_radio_name(radio.name)
            save_last_station(SAVED_STATION, Radio.station)
            LOG.info(f"Radio stream started: {radio.name} - {radio.url}")


class ButtonPanel:
    button_toggle_radio = Button(PIN_BTN_TOGGLE, pull_up=True, bounce_time=BTN_BOUNCE)
    button_toggle_radio.when_pressed = btn_toggle_handler  # always enabled
    button_select = Button(PIN_BTN_ROTARY, pull_up=True, bounce_time=BTN_BOUNCE)
    button_rotary = RotaryEncoder(PIN_ROTARY_DT, PIN_ROTARY_CLK, bounce_time=BTN_BOUNCE, max_steps=len(RADIO_LIST) - 1)
    button_rotary.steps = 0
    rotary_direction = True  # True is clockwise, False is counterclockwise
    rotary_twist_flag = False
    btn_select_flag = False

    @staticmethod
    def enable():
        ButtonPanel.button_rotary.when_rotated_clockwise = btn_rotary_clockwise_handler
        ButtonPanel.button_rotary.when_rotated_counter_clockwise = btn_rotary_counter_clockwise_handler
        ButtonPanel.button_select.when_pressed = btn_select_handler

    @staticmethod
    def disable():
        ButtonPanel.when_rotated_clockwise = None
        ButtonPanel.when_rotated_counter_clockwise = None
        ButtonPanel.button_select.when_pressed = None


# Program
LOG.info("Start program")
while True:
    if Radio.active:
        try:
            # handle button press from rotary encoder
            if ButtonPanel.btn_select_flag:
                ButtonPanel.btn_select_flag = False
                LCD.display_radio_name(Radio.station)

            # handle twist from rotary encoder
            if ButtonPanel.rotary_twist_flag:
                ButtonPanel.rotary_twist_flag = False
                LCD.disable_scrolling()
                Radio.metadata = ""
                station_changed = Radio.select_station()
                if station_changed:
                    Radio.play(Radio.station)

            # Update lcd text when scrolling is active
            if LCD.scroll_text:
                LCD.scroll()

            # Check metadata
            if Radio.metadata != PLAYER.metadata['icy-title']:
                LCD.scroll_text = ""
                Radio.metadata = PLAYER.metadata['icy-title']
                if Radio.metadata != "":
                    LCD.display_icy_title(Radio.metadata)

            # if, for any reason, MPV player stopped, restart it
            if PLAYER.core_idle:
                Radio.play(Radio.station)

        except (KeyError, TypeError):
            # KeyError or TypeError could be triggered when 'icy-title' doesn't exist (or no station is playing)
            pass
        except mpv.ShutdownError:
            LOG.error("ShutdownError from mpv")
            exit_program()

    time.sleep(0.0001)
