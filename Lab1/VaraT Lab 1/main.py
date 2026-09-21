from machine import Pin
import utime
import neopixel
# Power-enable for NeoPixel
pwr = Pin(2, Pin.OUT)
pwr.value(1) # turn on power
builtin_led = Pin(13, Pin.OUT)
np_led = neopixel.NeoPixel(Pin(0, Pin.OUT), 1)
builtin_led.value(1) # Built in LED - 1 is on
np_led[0] = (0, 0, 0) # NeoPixel LED - (0,0,0) is off
np_led.write()
while True:
    builtin_led.value(not builtin_led.value())
    if np_led[0] == (0, 0 ,0):
        np_led[0] = (255, 255, 255)
    else:
        np_led[0] = (0, 0, 0)
        
    np_led.write()
    utime.sleep(1)