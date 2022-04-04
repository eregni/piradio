#  Collection with selectable radio stations
from dataclasses import dataclass

@dataclass
class Radio:
    name: str  # displayed on lcd screen
    url: str


RADIO_LIST = (
    Radio('Vrt NWS', 'http://progressive-audio.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3'),
    Radio('Radio 1', 'http://icecast.vrtcdn.be/radio1.aac'),
    Radio('Radio 1 Classics', 'http://icecast.vrtcdn.be/radio1_classics.aac'),
    Radio('Radio 1 De Lage Landenlijst', 'http://icecast.vrtcdn.be/radio1_lagelanden.aac'),
    Radio('Radio 2 Antwerpen', 'http://icecast.vrtcdn.be/ra2ant.aac'),
    Radio('Radio 2 Bene Bene', 'http://icecast.vrtcdn.be/radio2_benebene.aac'),
    Radio('Radio 2 Unwind', 'http://icecast.vrtcdn.be/radio2_unwind.aac'),
    Radio('Klara', 'http://icecast.vrtcdn.be/klara.aac'),
    Radio('Klara Continuo', 'http://icecast.vrtcdn.be/klaracontinuo.aac'),
    Radio('La premiere', 'https://radios.rtbf.be/laprem1ere-128.mp3'),  # aac not available in 128 bit quality for now
    Radio('Musique 3', 'https://radios.rtbf.be/musiq3-128.aac'),
    Radio('Venice Classic radio', 'https://uk2.streamingpulse.com/ssl/vcr1')
)
