from machine import Pin
import utime

button = Pin(32, Pin.IN, Pin.PULL_UP)

last_press_time = 0
debounce_ms = 200

def button_handler(pin):
    global last_press_time
    current_time = utime.ticks_ms()
    if current_time - last_press_time > debounce_ms:
        last_press_time = current_time
        if pin.value() == 0:
            print("Button pressed")
        else:
            print("Button released")
    else:
        pass

button.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=button_handler)

while True:
    utime.sleep(1)