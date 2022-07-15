import logging
from dataclasses import dataclass


@dataclass
class Config:
    """Globals configuration vars. Threat as read-only..."""
    # audio
    AUDIO_DEVICE = 'alsa/hw:CARD=sndrpihifiberry'  # to check hw devices -> aplay -L
    TIMEOUT = 30

    # lcd
    SCROLL_DELAY = 0.75  # SET SPEED OF SCROLLING TEXT (1=1sec/hop)

    # rpi pins
    PIN_BTN_TOGGLE = 24
    PIN_BTN_ROTARY = 25
    PIN_ROTARY_DT = 5  # Momentary encoder DT
    PIN_ROTARY_CLK = 6  # Momentary encoder CLK
    BTN_BOUNCE = 0.05  # Button debounce time in seconds
    LCD_POWER_PIN = 16

    # log
    LOG_LEVEL = logging.INFO
    LOG_FILE = 'piradio.log'
    LOG_FORMATTER = logging.Formatter(
        fmt='[%(asctime)s.%(msecs)03d] [%(module)s] %(levelname)s: %(message)s',
        datefmt='%D %H:%M:%S',
    )
    SAVED_STATION = 'last_station.txt'  # save last opened station
