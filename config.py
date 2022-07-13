import logging


class Config:
    """Globals vars. Threat as read-only..."""
    # audio
    AUDIO_DEVICE = 'alsa/hw:CARD=sndrpihifiberry'  # to check hw devices -> aplay -L

    # rpi pins
    PIN_BTN_TOGGLE = 24
    PIN_BTN_ROTARY = 25
    PIN_ROTARY_DT = 5  # Momentary encoder DT
    PIN_ROTARY_CLK = 6  # Momentary encoder CLK
    BTN_BOUNCE = 0.05  # Button debounce time in seconds

    # log
    LOG_LEVEL = logging.INFO
    SAVED_STATION = 'last_station.txt'  # save last opened station