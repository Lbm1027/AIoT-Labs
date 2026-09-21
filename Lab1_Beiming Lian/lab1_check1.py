from machine import Pin
import utime

led = Pin(13, Pin.OUT)
led.value(0)

def blink(duration):
    led.value(1)          
    utime.sleep(duration)
    led.value(0)          # 熄灭

while True:
    for letter in ("...", "---", "..."):  # S、O、S
        for symbol in letter:
            if symbol == ".":
                blink(0.2)   
            else:
                blink(0.4)   

            utime.sleep(0.2)  # There is a 0.2 second pause between each dot or dash

        utime.sleep(0.4)      # The pause between letters is 0.4 seconds

    utime.sleep(0.8)          # The pause after each SOS sequence is 0.8 seconds