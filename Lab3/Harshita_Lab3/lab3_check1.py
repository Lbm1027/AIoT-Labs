from machine import Pin, I2C, RTC
import time
import ssd1306

# Hardware Setup
i2c = I2C(0, scl=Pin(22), sda=Pin(23))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

btn_a = Pin(15, Pin.IN, Pin.PULL_UP)  # Increment Hour
btn_b = Pin(32, Pin.IN, Pin.PULL_UP)  # Increment Minute

rtc = RTC()
# Initial hardcoded time: 2026-10-07 12:00:00
rtc.datetime((2026, 10, 7, 3, 12, 0, 0, 0))

last_debounce_a = 0
last_debounce_b = 0
DEBOUNCE_MS = 200

def main():
    global last_debounce_a, last_debounce_b
    
    while True:
        now = time.ticks_ms()
        year, month, day, _, hour, minute, second, _ = rtc.datetime()
        
        # Button A: Increment Hour
        if btn_a.value() == 0 and time.ticks_diff(now, last_debounce_a) > DEBOUNCE_MS:
            hour = (hour + 1) % 24
            rtc.datetime((year, month, day, 0, hour, minute, second, 0))
            last_debounce_a = now

        # Button B: Increment Minute
        if btn_b.value() == 0 and time.ticks_diff(now, last_debounce_b) > DEBOUNCE_MS:
            minute = (minute + 1) % 60
            rtc.datetime((year, month, day, 0, hour, minute, second, 0))
            last_debounce_b = now

        # Refresh Display
        oled.fill(0)
        oled.text("SMARTWATCH", 24, 5)
        oled.text("----------------", 0, 18)
        time_str = "{:02d}:{:02d}:{:02d}".format(hour, minute, second)
        oled.text(time_str, 32, 35)
        oled.show()
        
        time.sleep_ms(100)

if __name__ == "__main__":
    main()