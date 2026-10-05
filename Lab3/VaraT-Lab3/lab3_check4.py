from machine import RTC, I2C, Pin, PWM, ADC
import ssd1306
import utime

i2c = I2C(0, sda=Pin(22), scl=Pin(20), freq=400000)
oled = ssd1306.SSD1306_I2C(128, 32, i2c)

rtc = RTC()
rtc.datetime((2026, 9, 30, 2, 9, 0, 0, 0))

# button a: +1 hour, button b: +1 minute, button c: toggle clock/alarm mode
button_a = Pin(15, Pin.IN, Pin.PULL_UP)
button_b = Pin(33, Pin.IN, Pin.PULL_UP)
button_c = Pin(14, Pin.IN, Pin.PULL_UP)

last_press_a = 0
last_press_b = 0
last_press_c = 0
debounce_ms = 200

mode = "clock"
alarm_hour = 0
alarm_minute = 0
alarm_active = False
alarm_triggered = False

light_sensor = ADC(Pin(39))
light_sensor.atten(ADC.ATTN_11DB)
LIGHT_MAX = 100

piezo_pwm = PWM(Pin(27))
piezo_pwm.freq(440)
piezo_pwm.duty_u16(0)

def button_handler(pin):
    global last_press_a, last_press_b, last_press_c, mode, alarm_hour, alarm_minute, alarm_active
    current_time = utime.ticks_ms()
    if alarm_active:
        alarm_active = False
        return
    if pin == button_a:
        if current_time - last_press_a > debounce_ms:
            last_press_a = current_time
            if mode == "clock":
                now = rtc.datetime()
                new_hour = (now[4] + 1) % 24
                rtc.datetime((now[0], now[1], now[2], now[3], new_hour, now[5], now[6], 0))
            else:
                alarm_hour = (alarm_hour + 1) % 24
    elif pin == button_b:
        if current_time - last_press_b > debounce_ms:
            last_press_b = current_time
            if mode == "clock":
                now = rtc.datetime()
                new_minute = (now[5] + 1) % 60
                rtc.datetime((now[0], now[1], now[2], now[3], now[4], new_minute, now[6], 0))
            else:
                alarm_minute = (alarm_minute + 1) % 60
    else:
        if current_time - last_press_c > debounce_ms:
            last_press_c = current_time
            if mode == "clock":
                mode = "alarm"
            else:
                mode = "clock"

button_a.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
button_b.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
button_c.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

while True:
    now = rtc.datetime()
    time_string = f"{now[4]:02d}:{now[5]:02d}:{now[6]:02d}"
    alarm_string = f"Alarm {alarm_hour:02d}:{alarm_minute:02d}"

    value = light_sensor.read()
    level = min(value, LIGHT_MAX)
    oled.contrast(5 + int(level * 250 / LIGHT_MAX))

    oled.fill(0)
    oled.text(time_string, 0, 0)
    oled.text(str(value), 90, 0)
    oled.text(alarm_string, 0, 10)
    if mode == "alarm":
        oled.text("SET ALARM", 0, 20)

    if now[4] == alarm_hour and now[5] == alarm_minute:
        if not alarm_triggered:
            alarm_active = True
            alarm_triggered = True
    else:
        alarm_triggered = False

    if alarm_active:
        piezo_pwm.duty_u16(32768)
        oled.invert(1)
    else:
        piezo_pwm.duty_u16(0)
        oled.invert(0)

    oled.show()
    utime.sleep(0.2)