from machine import RTC, I2C, Pin, PWM, ADC, SPI
import ssd1306
import struct
import utime

TILT_THRESHOLD = 100   # counts (256 = 1 g), roughly a 25 degree tilt
SCROLL_STEP = 4        # pixels moved per frame
SWAP_AXES = False      # True if left/right tilt shows up on the sensor's Y axis
INVERT_H = False       # True if left/right scrolls the wrong way
INVERT_V = False       # True if up/down scrolls the wrong way
LIGHT_MAX = 100

i2c = I2C(0, sda=Pin(22), scl=Pin(20), freq=400000)
oled = ssd1306.SSD1306_I2C(128, 32, i2c)

rtc = RTC()
rtc.datetime((2026, 9, 30, 2, 9, 0, 0, 0))

# accelerometer (SPI)
spi = SPI(1, baudrate=1000000, polarity=1, phase=1, sck=Pin(5), mosi=Pin(19), miso=Pin(21))
cs = Pin(4, Pin.OUT, value=1)   # A5

def write_reg(reg, value):
    cs.value(0)
    spi.write(bytearray([reg, value]))
    cs.value(1)

def read_axes():
    cs.value(0)
    spi.write(bytearray([0xF2]))     # read + multi-byte + start at 0x32
    data = spi.read(6)
    cs.value(1)
    return struct.unpack('<hhh', data)

write_reg(0x2C, 0x0A)   # 100 Hz data rate
write_reg(0x2E, 0x00)   # no interrupts
write_reg(0x38, 0x00)   # FIFO bypass
write_reg(0x31, 0x08)   # full resolution, +/-2 g
write_reg(0x2D, 0x08)   # measure mode (last)

def calibrate(samples=20):
    sx = sy = sz = 0
    for _ in range(samples):
        x, y, z = read_axes()
        sx += x
        sy += y
        sz += z
        utime.sleep_ms(20)
    return sx // samples, sy // samples, sz // samples

oled.fill(0)
oled.text("Calibrating...", 0, 0)
oled.text("Hold board still", 0, 10)
oled.show()
utime.sleep(2)
off_x, off_y, off_z = calibrate()
print("offsets:", off_x, off_y, off_z)

# buttons, alarm, light, piezo
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
                rtc.datetime((now[0], now[1], now[2], now[3], (now[4] + 1) % 24, now[5], now[6], 0))
            else:
                alarm_hour = (alarm_hour + 1) % 24
    elif pin == button_b:
        if current_time - last_press_b > debounce_ms:
            last_press_b = current_time
            if mode == "clock":
                now = rtc.datetime()
                rtc.datetime((now[0], now[1], now[2], now[3], now[4], (now[5] + 1) % 60, now[6], 0))
            else:
                alarm_minute = (alarm_minute + 1) % 60
    else:
        if current_time - last_press_c > debounce_ms:
            last_press_c = current_time
            mode = "alarm" if mode == "clock" else "clock"

button_a.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
button_b.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)
button_c.irq(trigger=Pin.IRQ_FALLING, handler=button_handler)

def draw_content(ox, oy, time_string, alarm_string, value):
    oled.text(time_string, ox, oy)
    oled.text(str(value), ox + 90, oy)
    oled.text(alarm_string, ox, oy + 10)
    if mode == "alarm":
        oled.text("SET ALARM", ox, oy + 20)

scroll_x = 0
scroll_y = 0
frame = 0

while True:
    now = rtc.datetime()
    time_string = f"{now[4]:02d}:{now[5]:02d}:{now[6]:02d}"
    alarm_string = f"Alarm {alarm_hour:02d}:{alarm_minute:02d}"

    # tilt -> scroll direction (the axis tilted furthest wins)
    x, y, z = read_axes()
    tx = x - off_x
    ty = y - off_y
    h, v = (ty, tx) if SWAP_AXES else (tx, ty)
    if INVERT_H:
        h = -h
    if INVERT_V:
        v = -v
    if abs(h) >= abs(v):
        if h > TILT_THRESHOLD:
            scroll_x = (scroll_x + SCROLL_STEP) % 128
        elif h < -TILT_THRESHOLD:
            scroll_x = (scroll_x - SCROLL_STEP) % 128
    else:
        if v > TILT_THRESHOLD:
            scroll_y = (scroll_y + SCROLL_STEP) % 32
        elif v < -TILT_THRESHOLD:
            scroll_y = (scroll_y - SCROLL_STEP) % 32

    value = light_sensor.read()
    oled.contrast(5 + int(min(value, LIGHT_MAX) * 250 / LIGHT_MAX))

    oled.fill(0)
    for a in (-128, 0):
        for b in (-32, 0):
            draw_content(scroll_x + a, scroll_y + b, time_string, alarm_string, value)

    # alarm
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

    frame += 1
    if frame % 20 == 0:
        print("tilt:", tx, ty, "scroll:", scroll_x, scroll_y)
    utime.sleep_ms(30)