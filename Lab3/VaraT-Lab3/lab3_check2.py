from machine import RTC, I2C, Pin, ADC
import ssd1306
import utime

i2c = I2C(scl=Pin(20), sda=Pin(22))
oled = ssd1306.SSD1306_I2C(128, 32, i2c)

rtc = RTC()
rtc.datetime((2026, 9, 30, 2, 9, 0, 0, 0))

# button a increments the hour gpio15
# button b increments the minute gpio33
# button c resets seconds to 0 gpio14

button_a = Pin(15, Pin.IN, Pin.PULL_UP)
button_b = Pin(33, Pin.IN, Pin.PULL_UP)
button_c = Pin(14, Pin.IN, Pin.PULL_UP)

last_press_a = 0
last_press_b = 0
last_press_c = 0
debounce_ms = 200

light_sensor = ADC(Pin(39))
light_sensor.atten(ADC.ATTN_11DB)
LIGHT_MAX = 100

def button_handler(pin):
    global last_press_a, last_press_b,last_press_c
    current_time = utime.ticks_ms()
    if pin == button_a:
        if current_time - last_press_a > debounce_ms:
            last_press_a = current_time
            if pin.value() == 0:
                now = rtc.datetime()
                new_hour = (now[4] + 1) % 24
                rtc.datetime((now[0], now[1], now[2], now[3], new_hour, now[5], now[6], 0))
    elif pin == button_b:
        if current_time - last_press_b > debounce_ms:
            last_press_b = current_time
            if pin.value() == 0:
                now = rtc.datetime()
                new_minute = (now[5] + 1) % 60
                rtc.datetime((now[0], now[1], now[2], now[3], now[4], new_minute, now[6], 0))
    else:
        if current_time - last_press_c > debounce_ms:
            last_press_c = current_time
            if pin.value() == 0:
                now = rtc.datetime()
                rtc.datetime((now[0], now[1], now[2], now[3], now[4], now[5], 0, 0))

button_a.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
button_b.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
button_c.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

while True:
    now = rtc.datetime()
    hour = now[4]
    minute = now[5]
    second = now[6]
    time_string = f"{hour:02d}:{minute:02d}:{second:02d}"

    value = light_sensor.read()
    value_string = str(value)
    level = min(value, LIGHT_MAX)
    contrast_value = 5 + int(level * 250 / LIGHT_MAX)
    oled.contrast(contrast_value)

    oled.fill(0)
    oled.text(time_string, 0, 0)
    oled.text(value_string, 0, 10)
    oled.show()
    utime.sleep(0.2)