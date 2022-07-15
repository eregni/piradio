import logging
from datetime import datetime
from functools import partial
from time import time

import mpv
from gpiozero import Button, RotaryEncoder

from config import Config
from lcd_screen import lcd
from models.enums import States, Direction
from models.stations import Station, STATION_LIST

LOG = logging.getLogger(__name__)


def _mpv_log(loglevel: str, component: str, message: str):
    """Log handler for the python-mpv.MPV instance"""
    LOG.warning('[python-mpv] [%s] %s: %s', loglevel, component, message)


def _save_last_station(filename: str, radio: Station):
    """
    Save station RADIO index to file
    @param filename: str, file name
    @param radio: Station
    """
    index = STATION_LIST.index(radio)
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(str(index))
    LOG.debug("Saved RADIO index %s to file", index)


def _get_saved_station(filename: str) -> Station:
    """
    Get saved RADIO index nr
    @param filename: str, file name
    @return: Station
    """
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            index = int(file.readline())
        LOG.debug("Retrieving saved last radio index: %s", index)
    except FileNotFoundError:
        index = 0
        LOG.warning("Error while reading saved playlist index nr. Getting first item instead")

    return STATION_LIST[index]


class Radio:
    """Global vars"""
    station: Station = _get_saved_station(Config.SAVED_STATION)
    new_station: Station = _get_saved_station(Config.SAVED_STATION)
    _state: States = States.OFF
    _player = mpv.MPV(log_handler=_mpv_log, audio_device=Config.AUDIO_DEVICE, ytdl=False)
    _player.set_loglevel('error')
    _current_lcd_text = ""
    _prior_timer: time = None

    @classmethod
    def state(cls):
        return cls._state

    @classmethod
    def stop(cls):
        """Stop the radio"""
        cls._state = States.OFF
        LOG.info("Stop player")
        lcd.lcd_backlight_toggle(on=False)
        Radio._player.stop()
        ButtonPanel.disable()

    @classmethod
    def start(cls):
        """Start the radio"""
        LOG.info("Start player")
        lcd.lcd_backlight_toggle(on=True)
        ButtonPanel.enable()
        Radio.play(cls.station)

    @classmethod
    def check_select_station(cls):
        """
        Check if a new station is selected.
        The new station will play when user waits 3 seconds or pressed the rotary select button
        """
        if Radio.new_station != Radio.station:
            if ButtonPanel.button_select.is_active or time() - ButtonPanel.button_rotary_timestamp > 3:
                cls.play(cls.new_station)

    @classmethod
    def select_station(cls, direction: Direction):
        """
        Set a new station ready in the Radio.new_station field based on the direction of the RotaryEncoder.
        Print selected station on lcd
        """
        cls._state = States.SELECT_STATION

        index = STATION_LIST.index(cls.new_station)
        if direction == Direction.CLOCKWISE:
            index = 0 if index == len(STATION_LIST) - 1 else index + 1
        else:
            index = len(STATION_LIST) - 1 if index == 0 else index - 1

        cls.new_station = STATION_LIST[index]
        cls.set_lcd_text(cls.new_station.name)

    @classmethod
    def play(cls, station: Station):
        """Start playing station. Display error message when PLAYER is still idle after n seconds"""
        cls._state = States.START_STREAM
        timestamp = time()
        lcd.clear()
        cls.set_lcd_text("Tuning...")
        cls.station = station
        Radio._player.play(Radio.station.url)
        while Radio._player.core_idle:
            if time() - timestamp >= Config.TIMEOUT:
                LOG.error("Cannot start radio")
                cls.set_lcd_text("ERROR: cannot start playing")
                cls._state = States.MAIN
                break

        if not Radio._player.core_idle:
            cls.set_lcd_text(Radio.station.name)
            _save_last_station(Config.SAVED_STATION, Radio.station)
            LOG.info("Radio stream started: %s - %s", Radio.station.name, Radio.station.url)
            cls._state = States.PLAYING

    @classmethod
    def check_metadata(cls):
        """Update the metadata on the lcd screen if necessary"""
        try:
            if cls._player.metadata is not None:
                if cls._current_lcd_text != cls._player.metadata['icy-title']:
                    cls.set_lcd_text(Radio._player.metadata['icy-title'], prior=False)
        except (KeyError, AttributeError):
            # ignore exceptions raised because of missing 'metadata' attribute or missing 'icy-title' key
            pass

    @classmethod
    def set_lcd_text(cls, text: str, prior: bool = True):
        """
        Put text on display.
        When text with prior=True will stay on the display for 3 seconds and other calls will be discarded, except
        new 'prior' calls. (So far only the icy data has no prior...)
        """
        if not prior and cls._prior_timer is not None:
            if time() - cls._prior_timer < 3:
                # a message will be dropped if not prior itself or passed with prior override
                return

            cls._prior_timer = None

        if prior:
            cls._prior_timer = time()

        lcd.display_text(text)
        cls._current_lcd_text = text
        LOG.debug(f"New text for lcd: '%s'. prior=%s", text, str(prior).upper())


# Button handlers
def btn_toggle_handler():
    """Handler for the 'toggle radio' button"""
    LOG.debug("Button toggle radio pressed")
    if Radio.state() is States.OFF:
        Radio.start()
    else:
        Radio.stop()


def btn_select_handler():
    """Handler for push button from rotary encoder -> play next radio station"""
    LOG.debug("Btn_select pressed %s", datetime.now().strftime("%H:%M:%S"))
    if Radio.state() is States.PLAYING:
        Radio.set_lcd_text(Radio.station.name)


def btn_rotary_handler(direction: Direction):
    """Handler -> play next radio station"""
    LOG.debug("Rotary encoder turned %s. direction = %s", direction.name, direction.name)
    ButtonPanel.button_rotary_timestamp = time()
    if Radio.state() in [States.MAIN, States.PLAYING, States.SELECT_STATION]:
        Radio.select_station(direction)


# End Button handlers


class ButtonPanel:
    button_toggle_radio: Button = Button(Config.PIN_BTN_TOGGLE, pull_up=True, bounce_time=Config.BTN_BOUNCE)
    button_toggle_radio.when_pressed = btn_toggle_handler  # always enabled
    button_select: Button = Button(Config.PIN_BTN_ROTARY, pull_up=True, bounce_time=Config.BTN_BOUNCE)
    button_rotary: RotaryEncoder = RotaryEncoder(Config.PIN_ROTARY_DT, Config.PIN_ROTARY_CLK,
                                                 bounce_time=Config.BTN_BOUNCE, max_steps=len(STATION_LIST) - 1,
                                                 wrap=True)
    button_rotary_timestamp: time = time()

    @staticmethod
    def enable():
        """Connect handlers to buttons"""
        ButtonPanel.button_rotary.when_rotated_clockwise = partial(btn_rotary_handler, Direction.CLOCKWISE)
        ButtonPanel.button_rotary.when_rotated_counter_clockwise = partial(btn_rotary_handler, Direction.COUNTERCLOCKWISE)
        ButtonPanel.button_select.when_pressed = btn_select_handler

    @staticmethod
    def disable():
        """Disconnect button handlers"""
        ButtonPanel.when_rotated_clockwise = None
        ButtonPanel.when_rotated_counter_clockwise = None
        ButtonPanel.button_select.when_pressed = None
