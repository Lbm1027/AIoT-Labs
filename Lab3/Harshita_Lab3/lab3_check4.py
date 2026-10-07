from machine import Pin, I2C, RTC, ADC, PWM
import time
import ssd1306

# Pin Declarations
SCL_PIN = 22
SDA_PIN = 23
BTN_A_PIN = 15  # Hour adjust
BTN_B_PIN = 32  # Minute adjust
BTN_C_PIN = 14  # Alarm mode / Dismiss
LIGHT_PIN = 39  # LDR ADC
PIEZO_PIN = 27  # Audio alert

# Hardware Initialization
i2c = I2C(0, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

adc = ADC(Pin(LIGHT_PIN))
adc.atten(ADC.ATTN_11DB)

piezo = PWM(Pin(PIEZO_PIN), freq=1000, duty=0)

btn_a = Pin(BTN_A_PIN, Pin.IN, Pin.PULL_UP)
btn_b = Pin(BTN_B_PIN, Pin.IN, Pin.PULL_UP)
btn_c = Pin(BTN_C_PIN, Pin.IN, Pin.PULL_UP)

rtc = RTC()
rtc.datetime((2026, 10, 7, 3, 12, 0, 0, 0))

alarm_hour = 12
alarm_min = 1
alarm_active = False
setting_alarm = False

last_a = last_b = last_c = 0
DEBOUNCE_MS = 200

def adjust_brightness():
    light_val = adc.read()
    contrast = int((light_val / 4095.0) * 254) + 1
    contrast = max(1, min(255, contrast))
    oled.contrast(contrast)

def trigger_audio():
    piezo.freq(2000)
    piezo.duty(512)

def stop_audio():
    piezo.duty(0)

def main():
    global last_a, last_b, last_c, alarm_hour, alarm_min, setting_alarm, alarm_active
    
    flash_state = False
    
    while True:
        now = time.ticks_ms()
        adjust_brightness()
        
        y, m, d, _, hour, minute, second, _ = rtc.datetime()

        # Handle Button C (Toggle Alarm Edit / Dismiss Alarm)
        if btn_c.value() == 0 and time.ticks_diff(now, last_c) > DEBOUNCE_MS:
            if alarm_active:
                alarm_active = False
                stop_audio()
            else:
                setting_alarm = not setting_alarm
            last_c = now

        # Handle Buttons A and B
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

        # Trigger Alarm Condition
        if hour == alarm_hour and minute == alarm_min and second == 0:
            alarm_active = True

        oled.fill(0)
        
        if alarm_active:
            trigger_audio()
            flash_state = not flash_state
            if flash_state:
                oled.text("!! ALARM ALERT !!", 0, 15)
                oled.text(" {:02d}:{:02d} ".format(hour, minute), 30, 35)
            oled.text("Press C to stop", 5, 52)
        elif setting_alarm:
            stop_audio()
            oled.text("SET ALARM TIME", 8, 5)
            oled.text("----------------", 0, 18)
            oled.text("Alarm: {:02d}:{:02d}".format(alarm_hour, alarm_min), 20, 35)
            oled.text("A:+Hr B:+Min C:Done", 0, 52)
        else:
            stop_audio()
            oled.text("SMARTWATCH", 24, 2)
            oled.text("----------------", 0, 14)
            oled.text("{:02d}:{:02d}:{:02d}".format(hour, minute, second), 30, 28)
            oled.text("Alarm: {:02d}:{:02d}".format(alarm_hour, alarm_min), 10, 46)
            oled.text("C: Set Alarm", 15, 56)

        oled.show()
        time.sleep_ms(100)

if __name__ == "__main__":
    main()