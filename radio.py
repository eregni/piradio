from time import time

import mpv

from button_panel import ButtonPanel
from lcd_screen import Lcd
from models.enums import States, Direction
from models.stations import Station, STATION_LIST
from config import *

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
    _lcd = Lcd()
    _state: States = States.OFF
    station: Station = _get_saved_station(SAVED_STATION)
    _player = mpv.MPV(log_handler=_mpv_log, audio_device=AUDIO_DEVICE, ytdl=False)
    _player.set_loglevel('error')
    _current_icy_title = ""

    @property
    def state(self):
        return self._state

    @classmethod
    def stop(cls):
        """Stop the radio"""
        cls._state = States.OFF
        LOG.info("Stop player")
        cls._lcd.clear()
        Radio._player.stop()
        ButtonPanel.disable()

    @classmethod
    def start(cls):
        """Start the radio"""
        LOG.info("Start player")
        cls._lcd.clear()
        ButtonPanel.enable()
        Radio.play()

    @classmethod
    def select_station(cls, direction: Direction):
        """
        This function should be called by the rotary encoder.
        Display the next (or previous) station name on lcd.
        If you push the rotary encoder OR wait for 3 seconds, the current displayed station will start playing.
        @return: bool, True if the value of Radio.station has changed.
        Should only return False when the user selects the station which is already playing.
        """
        cls._state = States.SELECT_STATION
        ButtonPanel.button_select_event.clear()
        timestamp = time()
        new_station = Radio.switch_station(direction)
        cls._lcd.display_text(new_station.name)
        new_station_selected = True
        counter = ButtonPanel.button_rotary.steps
        while time() - timestamp <= 3:
            if ButtonPanel.button_rotary.steps != counter:
                direction = Direction.CLOCKWISE if ButtonPanel.button_rotary.steps > counter else Direction.COUNTERCLOCKWISE
                timestamp = time()
                new_station = Radio.switch_station(direction)
                cls._lcd.display_text(new_station.name)
                new_station_selected = bool(new_station != Radio.station)

            elif ButtonPanel.button_select_event.isSet():
                ButtonPanel.button_select_event.clear()
                Radio.play()
                return

        if new_station_selected:
            Radio.play()

    @classmethod
    def switch_station(cls, direction: Direction) -> Station:
        """
        Switch station. Update Radio.station based on the value from ButtonPanel.rotary_direction
        @return: Station. New selected Station from STATION_LIST
        """
        index = STATION_LIST.index(Station.station)
        if direction == Direction.CLOCKWISE:
            index = 0 if index == len(STATION_LIST) - 1 else index + 1
        else:
            index = len(STATION_LIST) - 1 if index == 0 else index - 1

        Station.station = STATION_LIST[index]
        return STATION_LIST[index]

    @classmethod
    def play(cls):
        """
        Start playing current station. Display error message when PLAYER is still idle after n seconds
        """
        timeout = 60
        cls._state = States.START_STREAM
        timestamp = time()
        cls._lcd.clear()
        cls._lcd.display_text("Tuning...")
        Radio._player.play(Radio.station.url)
        while Radio._player.core_idle:
            if time() - timestamp >= timeout:
                LOG.error("Cannot start radio")
                cls._lcd.display_text("ERROR: cannot start playing")
                cls._state = States.MAIN
                break

        if not Radio._player.core_idle:
            cls._lcd.display_text(Radio.station.name)
            _save_last_station(SAVED_STATION, Radio.station)
            LOG.info("Radio stream started: %s - %s", Radio.station.name, Radio.station.url)
            cls._state = States.PLAYING

    @classmethod
    def check_metadata(cls):
        """Update the metadata on the lcd screen if necessary"""
        try:
            if cls._current_icy_title != Radio._player.metadata['icy-title']:
                cls._current_icy_title = Radio._player.metadata['icy-title']
                if cls._current_icy_title != "":
                    cls._lcd.display_text(cls._current_icy_title)
        except (AttributeError, KeyError):
            pass  # ignore exceptions raised because of missing 'metadata' attribute or missing 'icy-title' key

    @classmethod
    def set_display_text(cls, text: str):
        cls._lcd.display_text(text)
