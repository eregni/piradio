#!/usr/bin/python

from RPi import GPIO
from time import sleep, time_ns

# Test script for testing 2 push buttons and a incremental encoder (Bourns PEC11R)
# https://datasheet.octopart.com/PEC11R-4015F-S0024-Bourns-datasheet-68303416.pdf
# The buttons are polled against a previous state.
# The rotary button is polled against a previous state.

# SETUP
rotary_delay = 0  # time in ns
clk = 6
dt = 5
btn_rotary = 25
btn_push = 24

print("START")

GPIO.setmode(GPIO.BCM)
GPIO.setup(clk, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(dt, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(btn_rotary, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(btn_push, GPIO.IN, pull_up_down=GPIO.PUD_UP)

rotaryTimer = time_ns()
counter = 0
clkLastState = GPIO.input(clk)
pushLastState = GPIO.input(btn_push)
rotaryPushLastState = GPIO.input(btn_rotary)

try:
        while True:
                if time_ns() - rotaryTimer < rotary_delay:
                        continue

                clkState = GPIO.input(clk)
                dtState = GPIO.input(dt)
                pushState = GPIO.input(btn_push)
                rotaryState = GPIO.input(btn_rotary)

                if clkState != clkLastState:
                        print("clkState: " + str(clkState))
                        print("dtState: " + str(dtState))
                        if dtState != clkState:
                                counter -= 1  # counter clockwise rotation detected
                        else:
                                counter += 1  # clockwise rotation detected
                        print(counter)
                        if counter in (100, -100):
                                counter = 0

                elif pushLastState != pushState:
                    print("btn push: " + str(pushState))
                    pushLastState = pushState

                elif rotaryPushLastState != rotaryState:
                    print("btn rotary: " + str(rotaryState))
                    rotaryPushLastState = rotaryState

                clkLastState = clkState
finally:
        GPIO.cleanup()
