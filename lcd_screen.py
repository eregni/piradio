"""
Control module for the lcd screen
ORIGINAL SOURCE: https://github.com/the-raspberry-pi-guy/lcd.git
"""
import logging
import textwrap
from time import sleep, time
from typing import List
from smbus import SMBus
import threading

LOG = logging.getLogger(__name__)

BUS_NUMBER = 1 # SET TO I2C BUS NR
ADDR = 0x27  # SET THE I2C ADDRESS HERE

# other commands
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
LCD_5x10DOTS = 0x04
LCD_5x8DOTS = 0x00

# flags for backlight control
LCD_BACKLIGHT = 0x08
LCD_NOBACKLIGHT = 0x00

En = 0b00000100  # Enable bit
Rw = 0b00000010  # Read/Write bit
Rs = 0b00000001  # Register select bit


class I2CDevice:
    def __init__(self, addr: int, bus: int = BUS_NUMBER):
        self.addr = addr
        self.bus = SMBus(bus)

    # write a single command
    def write_cmd(self, cmd: int):
        self.bus.write_byte(self.addr, cmd)
        sleep(0.0001)

    # write a command and argument
    def write_cmd_arg(self, cmd: int, data: int):
        self.bus.write_byte_data(self.addr, cmd, data)
        sleep(0.0001)

    # write a block of data
    def write_block_data(self, cmd: int, data: int):
        self.bus.write_block_data(self.addr, cmd, data)
        sleep(0.0001)

    # read a single byte
    def read(self) -> int:
        return self.bus.read_byte(self.addr)

    # read
    def read_data(self, cmd: int) -> int:
        return self.bus.read_byte_data(self.addr, cmd)

    # read a block of data
    def read_block_data(self, cmd: int) -> int:
        return self.bus.read_block_data(self.addr, cmd)


class Lcd:
    def __init__(self):
        self.icy_title: str = ""
        self.scroll_text = ""
        self._scroll_index: int = 0
        self._scroll_lock: float = time()
        self._scroll_thread = threading.Thread(target=self._scroll, name="scroll_thread")
        self._lcd = I2CDevice(addr=ADDR)
        self._lcd_write(0x03)
        self._lcd_write(0x03)
        self._lcd_write(0x03)
        self._lcd_write(0x02)
        self._lcd_write(LCD_FUNCTIONSET | LCD_2LINE | LCD_5x8DOTS | LCD_4BITMODE)
        self._lcd_write(LCD_DISPLAYCONTROL | LCD_DISPLAYON)
        self._lcd_write(LCD_CLEARDISPLAY)
        self._lcd_write(LCD_ENTRYMODESET | LCD_ENTRYLEFT)
        sleep(0.2)

    def display_radio_name(self, name: str):
        """
        Display radio name on lcd
        @type name: string, radio name to print on display
        """
        LOG.debug("New radio_name: %s", name)
        lines = textwrap.wrap(name, 16)
        self.clear()
        self._lcd_display_string(lines[0], 1)
        if len(lines) > 1:
            self._lcd_display_string(lines[1], 2)

    def display_icy_title(self, title: str):
        """
        Display icy-title on lcd. Activate scrolling when there are more than 2 lines to be displayed
        @param title: string title to display
        """
        LOG.debug("New icy-title: %s", title)
        lines = textwrap.wrap(title, 16)
        self.clear()
        self._lcd_display_string(lines[0], 1)
        if len(lines) == 2:
            self._lcd_display_string(lines[1], 2)
        elif len(lines) > 2:
            self._set_up_scrolling(lines)

    def display_text(self, text: str, line: int):
        """
        Display text on specified line
        @param text: str
        @param line: int
        @return:
        """
        LOG.debug("New text: %s", text)
        lines = textwrap.wrap(text, 16)
        self.clear()
        self._lcd_display_string(lines[0], 1)
        if len(lines) > 1:
            self._lcd_display_string(lines[1], 2)

    def clear(self):
        """Clear lcd and set to home"""
        self.scroll_text = ""
        self._scroll_thread.join()  # todo TEST
        self._lcd_write(LCD_CLEARDISPLAY)
        self._lcd_write(LCD_RETURNHOME)

    def lcd_backlight(self, active: bool):
        """Activate/Deactivate backlight"""
        if active:
            self._lcd.write_cmd(LCD_BACKLIGHT)
        else:
            self._lcd.write_cmd(LCD_NOBACKLIGHT)

    def _lcd_display_string(self, string: str, line: int):
        """
        Print string on lcd screen
        @param string: str
        @param line: put string on specified line nr (1 or 2)
        """
        # if function is not called by scroll_thread terminate it
        if threading.currentThread() != self._scroll_thread:
            self.scroll_text = ""
            self._scroll_thread.join()

        if line == 1:
            self._lcd_write(0x80)
        elif line == 2:
            self._lcd_write(0xC0)
        else:
            return

        for char in string:
            self._lcd_write(ord(char), Rs)

    def _set_up_scrolling(self, lines: List[str]):
        """
        Activate scrolling in separate thread
        @param lines: List[str] -> textwrap.wrap()
        """
        scroll_lines = []
        # concat lines except the first item (is printed on line 1)
        for i in range(1, len(lines)):
            scroll_lines.append(lines[i])
        self.scroll_text = " ".join(scroll_lines)
        self._scroll_thread.start()

    def _scroll(self):
        """Scroll text on lcd. to be run in separate thread"""
        while self.scroll_text:
            if time() - self._scroll_lock < 0.5:
                return

            self._scroll_lock = time()
            if self._scroll_index in [0, len(self.scroll_text) - 16]:
                # add two seconds delay at start and end of the text line. Otherwise, it's harder to read
                self._scroll_lock += 2

            text = self.scroll_text[self._scroll_index: self._scroll_index + 16]
            self._lcd_display_string(text, 2)
            self._scroll_index = 0 if self._scroll_index >= len(self.scroll_text) - 16 else self._scroll_index + 1


    # clocks EN to latch command
    def _lcd_strobe(self, data: int):
        self._lcd.write_cmd(data | En | LCD_BACKLIGHT)
        sleep(.0005)
        self._lcd.write_cmd(((data & ~En) | LCD_BACKLIGHT))
        sleep(.0001)

    def _lcd_write_four_bits(self, data: int):
        self._lcd.write_cmd(data | LCD_BACKLIGHT)
        self._lcd_strobe(data)

    # write a command to lcd
    def _lcd_write(self, cmd: int, mode: int = 0):
        self._lcd_write_four_bits(mode | (cmd & 0xF0))
        self._lcd_write_four_bits(mode | ((cmd << 4) & 0xF0))
