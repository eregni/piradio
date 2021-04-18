#!/usr/bin/python3
"""
Script to play radio streams on a raspberrypi pimped with an audiophonics sabre dac v3
Controlled by two buttons. 1 to play next station and 1 to start/stop playing
It should be runned as a systemd service.
A small display is used to show the current played track.   # todo: choose hardware...

Usefull sources:
    arch arm config: https://archlinuxarm.org/platforms/armv7/broadcom/raspberry-pi-2
    run gpio as non-root: https://arcanesciencelab.wordpress.com/2016/03/31/running-rpi3-applications-that-use-gpio-without-being-root/
    radio stream url's: https://hendrikjansen.nl/henk/streaming1.html#wl
    python-mpv: https://github.com/jaseg/python-mpv
    audiophonics sabre dac v3: https://www.audiophonics.fr/en/index.php?controller=attachment&id_attachment=208
        THERE IS AN ERROR WITH THE NUMBERING OF THE PINS IN THE DAC DOCUMENTATION.
        HALFWAY, IT SWITCHES FROM BCM TO PHYSICAL PIN NUMBERING
        the dac occupies the following rpi pins (bcm numbering):
            4, 17, 22 (software shutdown, button shutdown, bootOk)
            18, 19, 21 (dac audio, DOCUMENTATION REFERS TO PHYSICAL PIN NRS 12, 35, 40)

SET-UP
The raspberrypi needs following packages (arch linux):
    mpv
    alsa-utils
    python-raspberry-gpio (from AUR -> yay is a usefull program to install aur packages)

python modules (use pip to install):
    python-mpv
    gpiozero

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
todo: choose mpv volume -> volume=[0-100] (default 100) -> mpv.conf
"""
import logging
import signal
import gpiozero
import mpv
AUDIO_DEVICE = 'alsa/default:CARD=sndrpihifiberry'
RADIO = (
        'http://icecast.vrtcdn.be/radio1.aac',
        'http://icecast.vrtcdn.be/radio1_classics.aac',
        'http://icecast.vrtcdn.be/ra2ant.aac',
        'http://icecast.vrtcdn.be/klara.aac',
        'http://icecast.vrtcdn.be/klaracontinuo.aac',
        'https://radios.rtbf.be/laprem1ere-128.mp3',  # aac not available in 128 bit quality for now
        'https://radios.rtbf.be/musiq3-128.aac',
        'http://progressive-audio.lwc.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'
)
SAVED_STATION = 'last_station.txt'
BTN1_PIN = 25
BTN2_PIN = 24

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
    if LEVEL == logging.DEBUG:
        print('[python-mpv] [{}] {}: {}'.format(loglevel, component, message))


def main():
    """Main loop"""
    player = mpv.MPV(log_handler=my_log, audio_device=AUDIO_DEVICE)
    player.set_loglevel('error')

    def btn_toggle_handler():
        if player.is_playing:
            player.stop()
        else:
            player.playlist_play_index(player.playlist_current_pos)

    def btn_next_handler():
        player.playlist_next()
        save_last_station(player)

    LOG.info("start radio")
    btn_toggle = gpiozero.Button(BTN1_PIN, pull_up=True, bounce_time=0.1)
    btn_toggle.when_pressed = btn_toggle_handler
    btn_next = gpiozero.Button(BTN2_PIN, pull_up=True, bounce_time=0.1)
    btn_next.when_pressed = btn_next_handler

    index = get_saved_station()
    player.playlist_clear()
    player.loop_playlist = True
    for url in RADIO:
        player.playlist_append(url)

    player.playlist_play_index(index)
    current_playing = ""

    while True:  # todo -> btn 'stop' || btn 'next' == False. update metadata with interval
        pass
        try:
            if current_playing != player.metadata['icy-title']:
                update_metadata(player)
                current_playing = player.metadata['icy-title']
                print("Current playlist index: {}".format(player.playlist_current_pos))
        except (TypeError, KeyError):
            LOG.debug("No (icy) metadata available")
            pass


def update_metadata(player: mpv.MPV) -> None:
    """
    Send metadata to lcd screen
    :param player: python-mpv MPV instance
    """
    name = player.metadata['icy-name']
    title = player.metadata['icy-title']
    if LEVEL == logging.DEBUG:
        print("icy-name: {}\nicy-title: {}".format(name, title))
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


def save_last_station(player: mpv.MPV) -> None:
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
