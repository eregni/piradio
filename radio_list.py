"""Collection with selectable radio stations"""
from dataclasses import dataclass

@dataclass
class Station:
    name: str  # displayed on lcd screen
    url: str


RADIO_LIST = (
    Station('Vrt NWS', 'http://progressive-audio.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'),
    Station('Radio 1', 'http://icecast.vrtcdn.be/radio1.aac'),
    Station('Radio 1 Classics', 'http://icecast.vrtcdn.be/radio1_classics.aac'),
    Station('Radio 1 De Lage Landenlijst', 'http://icecast.vrtcdn.be/radio1_lagelanden.aac'),
    Station('Radio 2 Antwerpen', 'http://icecast.vrtcdn.be/ra2ant.aac'),
    Station('Radio 2 Bene Bene', 'http://icecast.vrtcdn.be/radio2_benebene.aac'),
    Station('Radio 2 Unwind', 'http://icecast.vrtcdn.be/radio2_unwind.aac'),
    Station('Klara', 'http://icecast.vrtcdn.be/klara.aac'),
    Station('Klara Continuo', 'http://icecast.vrtcdn.be/klaracontinuo.aac'),
    Station('La premiere', 'https://radios.rtbf.be/laprem1ere-128.mp3'),  # aac not available in 128 bit quality for now
    Station('Musique 3', 'https://radios.rtbf.be/musiq3-128.aac'),
    Station('Venice Classic radio', 'https://uk2.streamingpulse.com/ssl/vcr1')
)
