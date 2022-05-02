"""
Control module for lcd screen RC1602B5-LLH-JWV
Datasheet: https://www.tme.eu/Document/d73e6686c34bcab5ca8e82176393a587/RC1602B5-LLH-JWV.pdf
The module can just display text. It fetches the string on 16x2 lines and the 2nd line starts scrolling when the string
is longer than 32 chars.
ORIGINAL SOURCE: https://github.com/the-raspberry-pi-guy/lcd.git
"""
import logging
import textwrap
from time import sleep
from threading import Thread
from typing import List
from smbus import SMBus

LOG = logging.getLogger(__name__)

BUS = 1 # SET TO I2C BUS NR
ADDR = 0x3c  # SET THE I2C ADDRESS HERE
SCROLL_DELAY = 0.75 # SET SPEED OF SCROLLING TEXT (1=1sec/hop)

# Instructions -> datasheet p29
LCD_CLEARDISPLAY = 0x01
LCD_RETURNHOME = 0x02
LCD_ENTRYMODESET = 0x04
LCD_DISPLAYCONTROL = 0x08
LCD_CURSORSHIFT = 0x10
LCD_FUNCTIONSET = 0x20
LCD_SETCGRAMADDR = 0x40
LCD_SETDDRAMADDR = 0x80

# flags for display entry mode
LCD_ENTRYRIGHT = 0x00
LCD_ENTRYLEFT = 0x02
LCD_ENTRYSHIFTINCREMENT = 0x01
LCD_ENTRYSHIFTDECREMENT = 0x00

# flags for display on/off control
LCD_DISPLAYON = 0x04
LCD_DISPLAYOFF = 0x00
LCD_CURSORON = 0x02
LCD_CURSOROFF = 0x00
LCD_BLINKON = 0x01
LCD_BLINKOFF = 0x00

# flags for display/cursor shift
LCD_DISPLAYMOVE = 0x08
LCD_CURSORMOVE = 0x00
LCD_MOVERIGHT = 0x04
LCD_MOVELEFT = 0x00

# flags for function set
LCD_8BITMODE = 0x10
LCD_4BITMODE = 0x00
LCD_2LINE = 0x08
LCD_1LINE = 0x00
LCD_5x11DOTS = 0x04
LCD_5x8DOTS = 0x00

# Control bytes -> datasheet p38
CTRLBYTE_DATA = 0x40  # write to DDRAM/CGRAM
CTRLBYTE_COMMAND = 0x00  # write to IR

class Lcd:
    """
    Class to write strings to lcd display. Writing a string always clears the lcd and start at the first character in
    the upper left. When the string doesn't fit on the display, the 2nd line will start scrolling.
    """
    def __init__(self, addr: int = ADDR, bus: int = BUS):
        self._scroll_text = ""
        self._addr = addr
        self._bus = SMBus(bus)
        self._set_up_scroll_thread()

        # initialize -> datasheet p42
        sleep(0.02)
        self._write_command(LCD_FUNCTIONSET | LCD_8BITMODE | LCD_2LINE | LCD_5x8DOTS)
        self._write_command(LCD_DISPLAYCONTROL | LCD_DISPLAYON | LCD_CURSOROFF | LCD_BLINKOFF)
        self._write_command(LCD_CLEARDISPLAY)
        sleep(0.01)
        self._write_command(LCD_ENTRYMODESET | LCD_ENTRYLEFT)

    def display_text(self, text: str):
        """
        Display text. Activate scrolling in separate thread when the text on the second line > 16 characters.
        @param text: str
        """
        lines = textwrap.wrap(text, 16)
        self.clear()
        self._display_string(lines[0], 1)
        if len(lines) == 2:
            self._display_string(lines[1], 2)
        elif len(lines) > 2:
            scroll_lines = []
            # concat lines except the first one (is printed on line 1)
            for i in range(1, len(lines)):
                scroll_lines.append(lines[i])
            self._scroll_text = " ".join(scroll_lines)
            self._set_up_scroll_thread()
            self._scroll_thread.start()

    def clear(self):
        """Clear lcd and set to home"""
        self._stop_scrolling()
        self._write_command(LCD_CLEARDISPLAY)
        sleep(0.001)
        self._write_command(LCD_RETURNHOME)
        sleep(0.001)

    def _display_string(self, string: str, line: int):
        """
        Print string on lcd screen
        @param string: str
        @param line: put string on specified line nr (1 or 2)
        """
        if line == 1:
            self._write_command(LCD_SETDDRAMADDR)
        elif line == 2:
            self._write_command(LCD_SETDDRAMADDR + 0x40)
        else:
            return

        self._write_block_data([ord(item) for item in string])

    def _scroll(self):
        """Scroll text on lcd. To be run in separate thread"""
        scroll_index = 0
        while self._scroll_text:
            text = self._scroll_text[scroll_index: scroll_index + 16]
            self._display_string(text, 2)

            if scroll_index in [0, len(self._scroll_text) - 16]:
                # add two seconds delay at start and end of the text line. Otherwise, it's harder to read
                sleep(SCROLL_DELAY + 2)
            else:
                sleep(SCROLL_DELAY)

            if scroll_index >= len(self._scroll_text) - 16:
                scroll_index = 0
            else:
                scroll_index += 1

    def _stop_scrolling(self):
        self._scroll_text = ""
        if isinstance(self._scroll_thread, Thread) and self._scroll_thread.is_alive():
            self._scroll_thread.join()

    def _set_up_scroll_thread(self):
        self._scroll_thread = Thread(target=self._scroll, name="scroll_thread")

    def _write_command(self, cmd: int):
        """
        Write value to Instruction register (IR)
        @type cmd: command from instruction table -> datasheet p29s
        """
        self._bus.write_byte_data(self._addr, CTRLBYTE_COMMAND, cmd)
        sleep(0.0001)

    def _write_data(self, data: int):
        """
        Write value to DDRAM/CGRAM
        @type data: int
        """
        self._bus.write_byte_data(self._addr, CTRLBYTE_DATA, data)
        sleep(0.0001)

    def _write_block_data(self, data: List[int]):
        """
        Write list of values to DDRAM/CGRAM
        @type data: List[int]
        """
        self._bus.write_i2c_block_data(self._addr, CTRLBYTE_DATA, data)
        sleep(0.0001)
