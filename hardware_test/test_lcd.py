from time import sleep

from lcd_screen import lcd

lcd.lcd_backlight_toggle(on=True)
lcd.display_text("bats bats bats baaats! bats bats bats!")

sleep(30)
lcd.display_text("Baaaaats")
sleep(100)
