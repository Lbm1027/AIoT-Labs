from machine import Pin, I2C, RTC, PWM
import time
import ssd1306

i2c = I2C(0, scl=Pin(22), sda=Pin(23))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

btn_a = Pin(15, Pin.IN, Pin.PULL_UP)  # Hr adjust
btn_b = Pin(32, Pin.IN, Pin.PULL_UP)  # Min adjust
btn_c = Pin(14, Pin.IN, Pin.PULL_UP)  # Toggle Alarm Mode / Silence

piezo = PWM(Pin(27), freq=1000, duty=0)

rtc = RTC()
rtc.datetime((2026, 10, 7, 3, 12, 0, 0, 0))

alarm_hour = 12
alarm_min = 1
alarm_active = False
setting_alarm = False

last_a = last_b = last_c = 0
DEBOUNCE_MS = 200

def sound_alarm():
    piezo.freq(2000)
    piezo.duty(512)
    time.sleep_ms(100)
    piezo.duty(0)

def main():
    global last_a, last_b, last_c, alarm_hour, alarm_min, setting_alarm, alarm_active
    
    while True:
        now = time.ticks_ms()
        y, m, d, _, hour, minute, second, _ = rtc.datetime()

        # Mode Toggle (Button C)
        if btn_c.value() == 0 and time.ticks_diff(now, last_c) > DEBOUNCE_MS:
            if alarm_active:
                alarm_active = False  # Silence alarm
            else:
                setting_alarm = not setting_alarm  # Toggle edit mode
            last_c = now

        # Adjustment (Buttons A & B)
        if setting_alarm:
            if btn_a.value() == 0 and time.ticks_diff(now, last_a) > DEBOUNCE_MS:
                alarm_hour = (alarm_hour + 1) % 24
                last_a = now
            if btn_b.value() == 0 and time.ticks_diff(now, last_b) > DEBOUNCE_MS:
                alarm_min = (alarm_min + 1) % 60
                last_b = now
        else:
            if btn_a.value() == 0 and time.ticks_diff(now, last_a) > DEBOUNCE_MS:
                hour = (hour + 1) % 24
                rtc.datetime((y, m, d, 0, hour, minute, second, 0))
                last_a = now
            if btn_b.value() == 0 and time.ticks_diff(now, last_b) > DEBOUNCE_MS:
                minute = (minute + 1) % 60
                rtc.datetime((y, m, d, 0, hour, minute, second, 0))
                last_b = now

        # Check Alarm Trigger
        if hour == alarm_hour and minute == alarm_min and second == 0:
            alarm_active = True

        # Render Display
        oled.fill(0)
        if alarm_active:
            oled.text("*** ALARM! ***", 10, 10)
            oled.text("Press C to stop", 5, 35)
            sound_alarm()
        elif setting_alarm:
            oled.text("SET ALARM MODE", 8, 5)
            oled.text("----------------", 0, 18)
            oled.text("Alarm: {:02d}:{:02d}".format(alarm_hour, alarm_min), 20, 35)
            oled.text("A:+Hr  B:+Min", 10, 52)
        else:
            oled.text("CLOCK MODE", 24, 5)
            oled.text("----------------", 0, 18)
            oled.text("{:02d}:{:02d}:{:02d}".format(hour, minute, second), 32, 32)
            oled.text("Alarm set: {:02d}:{:02d}".format(alarm_hour, alarm_min), 5, 52)
            piezo.duty(0)

        oled.show()
        time.sleep_ms(100)

if __name__ == "__main__":
    main()