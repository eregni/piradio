#!/usr/bin/python3
import logging
import signal
import vlc

SAVED_STATION = 'last_station.txt'
RADIO = [
        'http://icecast.vrtcdn.be/klara-high.mp3',
        'http://icecast.vrtcdn.be/ra2ant-high.mp3',
        'http://icecast.vrtcdn.be/klara-high.mp3',
        'http://icecast.vrtcdn.be/klaracontinuo-high.mp3',
        'http://progressive-audio.lwc.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'
    ]

# Logging config
LEVEL = logging.DEBUG
LOG_FORMATTER = logging.Formatter(
    fmt='[%(asctime)s.%(msecs)03d] [%(module)s] %(levelname)s: %(message)s',
    datefmt='%D %H:%M:%S',
)
LOG_FORMATTER.default_msec_format = '%s.%03d'
LOG_HANDLER = logging.FileHandler(filename='piradio.log')
LOG_HANDLER.setFormatter(LOG_FORMATTER)
LOG_HANDLER.setLevel(LEVEL)
LOG = logging.getLogger()
LOG.addHandler(LOG_HANDLER)
LOG.setLevel(LEVEL)
# End logging config


def main():
    LOG.debug("start radio")
    instance = vlc.Instance()
    player = vlc.MediaPlayer()
    try:
        with open(SAVED_STATION, 'r') as f:
            station = f.readline()
    except FileNotFoundError:
        station = get_next_station()
        save_last_station(station)

    player.set_mrl(station)
    player.play()
    media = player.get_media()
    vlc.libvlc_media_parse(media)
    test = vlc.libvlc_media_get_meta(media, vlc.Meta().Date)
    while True:  # todo -> btn 'stop' || btn 'next' == False
        pass


def get_next_station(current_station=RADIO[-1]):
    if current_station == RADIO[-1]:
        return RADIO[0]
    else:
        return RADIO[RADIO.index(current_station) + 1]


def save_last_station(station):
    with open(SAVED_STATION, 'w') as f:
        f.write(station)


def signal_exit_program(sig_nr, *args):
    """
    handler for SIGINT, SIGTERM, SIGHUP
    :param sig_nr: int
    """
    LOG.debug("Signal received %s. Exit radio program", sig_nr)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_exit_program)
    signal.signal(signal.SIGTERM, signal_exit_program)
    signal.signal(signal.SIGHUP, signal_exit_program)
    main()
