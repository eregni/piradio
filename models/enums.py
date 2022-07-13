from enum import Enum


class Direction(Enum):
    CLOCKWISE = True
    COUNTERCLOCKWISE = False


class States(Enum):
    OFF = 0
    MAIN = 1
    START_STREAM = 2
    PLAYING = 3
    SELECT_STATION = 4
