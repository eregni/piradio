#!/usr/bin/python3
"""
Script to play radio streams on a raspberrypi.
Controlled by two buttons. 1 to play next station and 1 to start/stop playing
It should be runned as a systemd service.
For playing the media the script uses the python-mpv module to interact with mpv player.
A small display is used to show the current played track.
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
        'https://radios.rtbf.be/laprem1ere-128.mp3',  # aac not available in 128 bit quality
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
    """Log handler for the python-mpv.MPV instance. It just prints the log message"""
    print('[python-mpv] [{}] {}: {}'.format(loglevel, component, message))


def main():
    """Main loop"""
    btn_toggle = False
    btn_next = False
    LOG.info("start radio")
    player = mpv.MPV(log_handler=my_log)
    player.set_loglevel('error')

    index = get_saved_station()
    player.playlist_clear()
    player.loop_playlist = True
    for url in RADIO:
        player.playlist_append(url)

    player.playlist_play_index(index)
    playing = True
    current_playing = ""

    while True:  # todo -> btn 'stop' || btn 'next' == False. update metadata with interval
        if btn_toggle:
            playing = not playing
            if playing:
                player.stop()
            else:
                player.playlist_play_index(player.playlist_current_pos)
        if btn_next:
            player.playlist_next()
            save_last_station(player)
        if current_playing != player.metadata['icy-title']:
            update_metadata(player)
            current_playing = player.metadata['icy-title']


def update_metadata(player: mpv.MPV) -> None:
    """
    Send metadata to lcd screen
    :param player: python-mpv MPV instance
    """
    # todo: choose hardware...
    name = player.metadata['icy-name']
    title = player.metadata['icy-title']
    LOG.debug("New metadata: {} {}".format(name, title))


def get_saved_station() -> int:
    """
    get saved playlist index nr
    :return: int: index nr
    """
    try:
        with open(SAVED_STATION, 'r') as f:
            index = int(f.readline())
        LOG.debug("Retrieving saved index nr: {}".format(index))
    except (FileNotFoundError, BaseException):
        index = 0
        LOG.warning("Error while reading saved playlist index nr. "
                    "Getting first item in playlist instead")

    return index


def save_last_station(player: mpv.MPV):
    """
    Save station playlist index to file
    :param player: python-mpv MPV instance
    """
    with open(SAVED_STATION, 'w') as f:
        f.write(str(player.playlist_current_pos))
    LOG.debug("Saved station playlist index to file")


def signal_exit_program(sig_nr, *args):
    """
    handler for SIGINT, SIGTERM, SIGHUP
    :param sig_nr: int
    """
    LOG.info("Signal received %s. Exit radio program", sig_nr)
    SystemExit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_exit_program)
    signal.signal(signal.SIGTERM, signal_exit_program)
    signal.signal(signal.SIGHUP, signal_exit_program)
    main()
