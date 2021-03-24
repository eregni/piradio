#!/usr/bin/python3
import time
import vlc
url = 'http://icecast.vrtcdn.be/klara-high.mp3'

if __name__ == '__main__':
    instance = vlc.Instance()
    player = instance.media_player_new()
    media = instance.media_new_location(url)
    player.set_media(media)
    player.play()
    time.sleep(100)
