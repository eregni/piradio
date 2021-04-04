#!/usr/bin/python3
import logging
import signal
import vlc
import urllib.request
import icyparser

SAVED_STATION = 'last_station.txt'
RADIO = (
        'http://icecast.vrtcdn.be/radio1.aac',
        'http://icecast.vrtcdn.be/radio1_classics.aac',
        'http://icecast.vrtcdn.be/ra2ant.aac',
        'http://icecast.vrtcdn.be/klara.aac',
        'http://icecast.vrtcdn.be/klaracontinuo.aac',
        'https://radios.rtbf.be/laprem1ere-128.mp3',
        'https://radios.rtbf.be/musiq3-128.mp3',
        'http://progressive-audio.lwc.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'
)

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


def main():
    """Main loop"""
    LOG.debug("start radio")
    instance = vlc.Instance()
    player = instance.media_player_new()
    try:
        with open(SAVED_STATION, 'r') as f:
            station = f.readline()
    except FileNotFoundError:
        station = get_next_station()
        save_last_station(station)

    # todo -> try the icyparser fro the metadata
    icy = icyparser.IcyParser()
    icy.get_icy_information(RADIO[0])

    station = RADIO[1]  # DEBUG
    media = instance.media_new(station)
    player.set_media(media)
    player.play()

    while True:  # todo -> btn 'stop' || btn 'next' == False
        pass


def get_next_station(current_station=RADIO[-1]):
    """
    Get next station from list
    :param current_station: list with station url's
    :return: str. Radio url
    """
    LOG.debug("Getting next station")
    if current_station == RADIO[-1]:
        return RADIO[0]
    else:
        return RADIO[RADIO.index(current_station) + 1]


def get_radio_metadata(url):
    """
    Get icy-data from radio station
    :param url: str. Stream url
    :return: dict with icy metadata
    """
    LOG.debug("Getting metadata")
    request = urllib.request.Request(url, headers={"icy-metadata": "1"})
    response = urllib.request.urlopen(request, timeout=6)
    return dict(response.info())


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
