#!/usr/bin/python3
import vlc

SAVED_STATION = 'last_station.txt'
RADIO = [
        'http://icecast.vrtcdn.be/klara-high.mp3',
        'http://icecast.vrtcdn.be/ra2ant-high.mp3',
        'http://icecast.vrtcdn.be/klara-high.mp3',
        'http://icecast.vrtcdn.be/klaracontinuo-high.mp3',
        'http://progressive-audio.lwc.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'
    ]


def main():
    player = vlc.MediaPlayer()
    try:
        with open(SAVED_STATION, 'r') as f:
            station = f.readline()
    except FileNotFoundError:
        station = get_next_station()
        save_last_station(station)
    
    player.set_mrl(station)
    player.play()
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


if __name__ == '__main__':
    main()
