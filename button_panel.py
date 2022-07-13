import logging
from datetime import datetime
from functools import partial
from threading import Event

from gpiozero import Button, RotaryEncoder
from config import Config
from models.enums import Direction, States
from models.stations import STATION_LIST
from radio import Radio

LOG = logging.getLogger(__name__)


# Button handlers
def btn_toggle_handler():
    """Handler for the 'toggle radio' button"""
    LOG.debug("Button toggle radio pressed")
    if Radio.state is States.OFF:
        Radio.start()
    else:
        Radio.stop()


def btn_select_handler():
    """Handler for push button from rotary encoder -> play next radio station"""
    LOG.debug("Btn_select pressed %s", datetime.now().strftime("%H:%M:%S"))
    if Radio.state is States.SELECT_STATION:
        ButtonPanel.button_select_event.set()
    elif Radio.state is States.PLAYING:
        # todo add delay of 3 sec?
        Radio.set_display_text(Radio.station.name)


def btn_rotary_handler(direction: Direction):
    """Handler -> play next radio station"""
    LOG.debug("Rotary encoder turned %s. counter = %s", direction.name, ButtonPanel.button_rotary.steps)
    if Radio.state in [States.MAIN, States.PLAYING]:
        Radio.select_station(direction)

# End Button handlers


class ButtonPanel:
    button_toggle_radio: Button = Button(Config.PIN_BTN_TOGGLE, pull_up=True, bounce_time=Config.BTN_BOUNCE)
    button_toggle_radio.when_pressed = btn_toggle_handler  # always enabled
    button_select: Button = Button(Config.PIN_BTN_ROTARY, pull_up=True, bounce_time=Config.BTN_BOUNCE)
    button_rotary: RotaryEncoder = RotaryEncoder(Config.PIN_ROTARY_DT, Config.PIN_ROTARY_CLK, bounce_time=Config.BTN_BOUNCE,
                                                 max_steps=len(STATION_LIST) - 1)
    button_rotary.steps = 0
    button_select_event = Event()

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
