from machine import Pin
import utime
import neopixel

# Power-enable for NeoPixel
pwr = Pin(2, Pin.OUT)
pwr.value(1)

builtin_led = Pin(13, Pin.OUT)
np_led = neopixel.NeoPixel(Pin(0, Pin.OUT), 1)
builtin_led.value(0)
np_led[0] = (0, 0, 0)
np_led.write()

count = 0
np_on = False

while True:
    utime.sleep_ms(100)

    builtin_led.value(not builtin_led.value())

    count += 1

    if count == 5:
        count = 0
        np_on = not np_on

        if np_on:
            np_led[0] = (255, 255, 255)
        else:
            np_led[0] = (0, 0, 0)

        np_led.write()