from machine import Pin
import utime

dot_time = 0.2
dash_time = 0.4 # 2x longer than dot time
down_time = 0.2 # pause between symbols

builtin_led = Pin(13, Pin.OUT)

def dot():
    builtin_led.value(1)
    utime.sleep(dot_time)
    builtin_led.value(0)
    utime.sleep(down_time)

def dash():
    builtin_led.value(1)
    utime.sleep(dash_time)
    builtin_led.value(0)
    utime.sleep(down_time)

def sos():
    for _ in range(3):
        dot()
    utime.sleep(down_time)

    for _ in range(3):
        dash()
    utime.sleep(dot_time)

    for _ in range(3):
        dot()
    utime.sleep(dash_time * 2)

while True:
    sos()