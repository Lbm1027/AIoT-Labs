from machine import Pin
import utime
import neopixel

# power enable for neopixel
pwr = Pin(2, Pin.OUT)
pwr.value(1) # turn on power
builtin_led = Pin(13, Pin.OUT)
np_led = neopixel.NeoPixel(Pin(0, Pin.OUT), 1)

tick_count = 0
builtin_led.value(1)

while True:
    builtin_led.value(not builtin_led.value())
    if tick_count % 5 == 0:
        np_led[0] = (255, 255, 255)
    else:
        np_led[0] = (0, 0, 0)
    np_led.write()

    utime.sleep(0.1)
    tick_count += 1