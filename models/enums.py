from enum import Enum


class Direction(Enum):
    """Directions for RotaryEncoder"""
    CLOCKWISE = True
    COUNTERCLOCKWISE = False


class States(Enum):
    """Radio states"""
    OFF = 0
    MAIN = 1
    START_STREAM = 2
    PLAYING = 3
    SELECT_STATION = 4
