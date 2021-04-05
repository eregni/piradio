#!/usr/bin/python3
"""
Script to play radio streams on a raspberrypi.
Controlled by two buttons. 1 to play next station and 1 to stop playing
I should be runned as a systemd service.
For playing the media the script uses the python-mpv module to interact with mpv player.
A small display is used to show the current played track
Sources:
    radio stream url's: https://hendrikjansen.nl/henk/streaming1.html#wl
    python-mpv: https://github.com/jaseg/python-mpv
"""
import logging
import signal
import mpv

RADIO = (
        'http://icecast.vrtcdn.be/radio1.aac',
        'http://icecast.vrtcdn.be/radio1_classics.aac',
        'http://icecast.vrtcdn.be/ra2ant.aac',
        'http://icecast.vrtcdn.be/klara.aac',
        'http://icecast.vrtcdn.be/klaracontinuo.aac',
        'https://radios.rtbf.be/laprem1ere-128.mp3',
        'https://radios.rtbf.be/musiq3-128.aac',
        'http://progressive-audio.lwc.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'
)
SAVED_STATION = 'last_station.txt'

# ### Logging config ###
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
# ### End logging config ###


def my_log(loglevel, component, message):
    """Log handler for the python-mpv.MPV instance"""
    print('[python-mpv] [{}] {}: {}'.format(loglevel, component, message))


def main():
    """Main loop"""
    LOG.debug("start radio")
    player = mpv.MPV(log_handler=my_log)
    player.set_loglevel('info')

    try:
        with open(SAVED_STATION, 'r') as f:
            station = f.readline()
    except FileNotFoundError:
        station = get_next_station()
        save_last_station(station)
    player.playlist_clear()

    for url in RADIO:
        player.playlist_append(url)

    player.playlist_play_index(0)
    while True:  # todo -> btn 'stop' || btn 'next' == False. update metadate with interval
        pass


def get_next_station(current_station=RADIO[-1]):
    """
    Get next station from list
    :param current_station: list with station url's
    :return: str. Radio url
    """
    if current_station == RADIO[-1]:
        radio = RADIO[0]
    else:
        radio = RADIO[RADIO.index(current_station) + 1]

    LOG.info("Getting next station: {}".format(radio))
    return radio


def get_radio_metadata(player):
    """
    Get icy-data from radio station
    :param player: python-mpv.MPV.
    :return: dict with metadata
    """
    LOG.debug("Getting metadata")
    return player.metadata


def save_last_station(station):
    """
    Save radio url to file
    :param station: str. radio stream url
    """
    with open(SAVED_STATION, 'w') as f:
        f.write(station)
    LOG.debug("Saved station url to file")


def signal_exit_program(sig_nr, *args):
    """
    handler for SIGINT, SIGTERM, SIGHUP
    :param sig_nr: int
    """

    LOG.debug("Signal received %s. Exit radio program", sig_nr)
    SystemExit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_exit_program)
    signal.signal(signal.SIGTERM, signal_exit_program)
    signal.signal(signal.SIGHUP, signal_exit_program)
    main()
