#!/usr/bin/python3
"""
Script to play radio streams on a raspberrypi, pimped with an "audiophonics sabre dac v3" audio card
Controlled by two buttons: 1 Rotary encoder with push button to select stations and one push button start/stop the radio
An 16x2 lcd-display is used to show the radio name and track information.
It runs as a systemd service.

Useful sources:
    arch arm config: https://archlinuxarm.org/platforms/armv7/broadcom/raspberry-pi-2
    run gpio as non-root:
        https://arcanesciencelab.wordpress.com/2016/03/31/running-rpi3-applications-that-use-gpio-without-being-root/
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

i2c group and permission settings
    (https://arcanesciencelab.wordpress.com/2014/02/02/bringing-up-i2c-on-the-raspberry-pi-with-arch-linux/)
    # groupadd i2c
    # usermod -aG i2c [username]
    # echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c"' >> /etc/udev/rules.d/raspberrypi.rules

i2c speed
    dtparam=i2c_arm=on,i2c_arm_baudrate=400000 -> /boot/config.txt

atexit module catches SIGINT.
    You need to specify the kill signal in the systemd service since it sends by default SIGTERM
    -> KillSignal=SIGINT
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
import atexit
from time import time, sleep
from enum import Enum
from datetime import datetime
from functools import partial
from threading import Event
from gpiozero import Button, OutputDevice, RotaryEncoder
import setproctitle
import mpv
from lcd_screen import Lcd
from station_list import STATION_LIST, Station

# Config ################################################################################
AUDIO_DEVICE = 'alsa/hw:CARD=sndrpihifiberry'  # to check hw devices -> aplay -L
SAVED_STATION = 'last_station.txt'  # save last opened station
PIN_BTN_TOGGLE = 24
PIN_BTN_ROTARY = 25
PIN_ROTARY_DT = 5  # Momentary encoder DT
PIN_ROTARY_CLK = 6  # Momentary encoder CLK
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

class Direction(Enum):
    CLOCKWISE = True
    COUNTERCLOCKWISE = False

def mpv_log(loglevel: str, component: str, message: str):
    """Log handler for the python-mpv.MPV instance"""
    LOG.warning('[python-mpv] [%s] %s: %s', loglevel, component, message)

def get_saved_station(filename: str) -> Station:
    """
    Get saved RADIO index nr
    @param filename: str, file name
    @return: Station
    """
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            index = int(file.readline())
        LOG.debug("Retrieving saved last radio index: %s",index)
    except FileNotFoundError:
        index = 0
        LOG.warning("Error while reading saved playlist index nr. Getting first item instead")

    return STATION_LIST[index]

def save_last_station(filename: str, radio: Station):
    """
    Save station RADIO index to file
    @param filename: str, file name
    @param radio: Station
    """
    index = STATION_LIST.index(radio)
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(str(index))
    LOG.debug("Saved RADIO index %s to file", index)

@atexit.register
def exit_program():
    """handler for atexit -> stop mpv player. clear lcd screen"""
    RADIO.stop()
    line = "#" * 75
    LOG.info("Atexit handler triggered. Exit program\n%s\n", line)
    sys.exit(0)

class States(Enum):
    OFF = 0
    MAIN = 1
    START_STREAM = 2
    PLAYING = 3
    SELECT_STATION = 4

class Radio:
    def __init__(self):
        self._station: Station = get_saved_station(SAVED_STATION)
        self._player:  mpv.MPV = mpv.MPV(log_handler=mpv_log, audio_device=AUDIO_DEVICE, ytdl=False)
        self._player.set_loglevel('error')
        self._icy_title: str = ""
        self._state: States = States.OFF

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value: States):
        self._state = value

    @property
    def station(self):
        return self._station

    def stop(self):
        """Stop the radio"""
        self._state = States.OFF
        LOG.info("Stop player")
        LCD.clear()
        self._player.stop()
        BUTTON_PANEL.disable()

    def start(self):
        """Start the radio"""
        LOG.info("Start player")
        LCD.clear()
        BUTTON_PANEL.enable()
        self.play()

    def select_station(self, direction: Direction):
        """
        This function should be called by the rotary encoder.
        Display the next (or previous) station name on lcd.
        If you push the rotary encoder OR wait for 3 seconds, the current displayed station will start playing.
        @return: bool, True if the value of Radio.station has changed.
        Should only return False when the user selects the station which is already playing.
        """
        self._state = States.SELECT_STATION
        BUTTON_PANEL.button_select_event.clear()
        timestamp = time()
        self.switch_station(direction)
        LCD.display_text(self.station.name)
        new_station_selected = True
        counter = BUTTON_PANEL.button_rotary.steps
        while time() - timestamp <= 3:
            if BUTTON_PANEL.button_rotary.steps != counter:
                direction = Direction.CLOCKWISE if BUTTON_PANEL.button_rotary.steps > counter else Direction.COUNTERCLOCKWISE
                timestamp = time()
                new_station = self.switch_station(direction)
                LCD.display_text(self._station.name)
                new_station_selected = bool(new_station != self._station)

            elif BUTTON_PANEL.button_select_event.isSet():
                BUTTON_PANEL.button_select_event.clear()
                self.play()
                return

        if new_station_selected:
            self.play()

    def switch_station(self, direction: Direction) -> Station:
        """
        Switch station. Update Radio.station based on the value from ButtonPanel.rotary_direction
        @return: Station. New selected Station from STATION_LIST
        """
        index = STATION_LIST.index(self._station)
        if direction == Direction.CLOCKWISE:
            index = 0 if index == len(STATION_LIST) - 1 else index + 1
        else:
            index = len(STATION_LIST) - 1 if index == 0 else index - 1

        self._station = STATION_LIST[index]
        return STATION_LIST[index]

    def play(self):
        """
        Start playing current station. Display error message when PLAYER is still idle after n seconds
        """
        timeout = 60
        Radio.state = States.START_STREAM
        timestamp = time()
        LCD.clear()
        LCD.display_text("Tuning...")
        self._player.play(self._station.url)
        while self._player.core_idle:
            if time() - timestamp >= timeout:
                LOG.error("Cannot start radio")
                LCD.display_text("ERROR: cannot start playing")
                Radio.state = States.MAIN
                return

        LCD.display_text(self._station.name)
        save_last_station(SAVED_STATION, self._station)
        LOG.info("Radio stream started: %s - %s", self._station.name, self._station.url)
        self._state = States.PLAYING

    def check_metadata(self):
        """Update the metadata on the lcd screen if necessary"""
        try:
            if self._icy_title != self._player.metadata['icy-title']:
                self._icy_title = self._player.metadata['icy-title']
                if self._icy_title == "":
                    LCD.display_text(self._station.name)
                else:
                    LCD.display_text(self._icy_title)
        except (AttributeError, KeyError):
            pass  # ignore exceptions raised because of missing 'metadata' attribute or missing 'icy-title' key

# Button handlers
def btn_toggle_handler():
    """Handler for the 'toggle radio' button"""
    LOG.debug("Button toggle radio pressed")
    if RADIO.state == States.OFF:
        RADIO.start()
    else:
        RADIO.stop()

def btn_select_handler():
    """Handler for push button from rotary encoder -> play next radio station"""
    LOG.debug("Btn_select pressed %s", datetime.now().strftime("%H:%M:%S"))
    if RADIO.state == States.SELECT_STATION:
        BUTTON_PANEL.button_select_event.set()
    elif RADIO.state == States.PLAYING:
        LCD.display_text(RADIO.station.name)

def btn_rotary_handler(direction: Direction):
    """Handler -> play next radio station"""
    LOG.debug("Rotary encoder turned %s. counter = %s", direction.name, BUTTON_PANEL.button_rotary.steps)
    if RADIO.state in [States.MAIN, States.PLAYING]:
        RADIO.state = States.SELECT_STATION
        RADIO.select_station(direction)
# End Button handlers

class ButtonPanel:
    def __init__(self):
        self.button_toggle_radio: Button = Button(PIN_BTN_TOGGLE, pull_up=True, bounce_time=BTN_BOUNCE)
        self.button_toggle_radio.when_pressed = btn_toggle_handler  # always enabled
        self.button_select: Button = Button(PIN_BTN_ROTARY, pull_up=True, bounce_time=BTN_BOUNCE)
        self.button_rotary: RotaryEncoder = RotaryEncoder(PIN_ROTARY_DT, PIN_ROTARY_CLK, bounce_time=BTN_BOUNCE,
                                                          max_steps=len(STATION_LIST) - 1)
        self.button_rotary.steps = 0
        self.button_select_event = Event()

    def enable(self):
        """Connect button handlers"""
        self.button_rotary.when_rotated_clockwise = partial(btn_rotary_handler, Direction.CLOCKWISE)
        self.button_rotary.when_rotated_counter_clockwise = partial(btn_rotary_handler, Direction.COUNTERCLOCKWISE)
        self.button_select.when_pressed = btn_select_handler

    def disable(self):
        """Disconnect button handlers"""
        self.button_rotary.when_rotated_clockwise = None
        self.button_rotary.when_rotated_counter_clockwise = None
        self.button_select.when_pressed = None

# Global vars (Radio, Lcd, ButtonPanel)
lcd_power = OutputDevice(LCD_POWER_PIN)
lcd_power.on()  # turn on lcd
LCD = Lcd()
BUTTON_PANEL = ButtonPanel()
RADIO = Radio()

if __name__ == "__main__":
    setproctitle.setproctitle("piradio")
    LOG.info("Start program")
    try:
        while True:
            if RADIO.state == States.PLAYING:
                RADIO.check_metadata()

            sleep(0.001)

    except mpv.ShutdownError:
        LOG.error("ShutdownError from mpv")
    finally:
        exit_program()
