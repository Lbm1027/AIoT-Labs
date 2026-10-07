from machine import Pin, I2C, RTC, ADC
import time
import ssd1306

SDA_PIN = 22
SCL_PIN = 20
BUTTON_A_PIN = 15
BUTTON_B_PIN = 33
BUTTON_C_PIN = 14
LIGHT_PIN = 39

OLED_WIDTH = 128
OLED_HEIGHT = 32
OLED_ADDR = 0x3C
I2C_FREQ = 400000
DEBOUNCE_MS = 30
DISPLAY_MS = 100
LIGHT_SAMPLE_MS = 50

LIGHT_DARK = 0
LIGHT_BRIGHT = 350
CONTRAST_MIN = 4
CONTRAST_MAX = 255
SMOOTHING_ALPHA = 0.25

START_TIME = (2026, 9, 30, 2, 9, 0, 0, 0)

def time_text(current):
    return "%02d:%02d:%02d" % (current[4], current[5], current[6])

class DebouncedButton:
    def __init__(self, name, number):
        self.name = name
        self.pin = Pin(number, Pin.IN, Pin.PULL_UP)
        self.pin.irq(handler=None)
        self.state = self.pin.value()
        self.candidate = self.state
        self.since = time.ticks_ms()
        self.pending = True
        self.debouncing = False
        self.initializing = True
        self.callback = self._on_edge

    def _on_edge(self, pin):
        if not self.pending:
            self.pending = True
            pin.irq(handler=None)

    def _arm(self):
        self.pin.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=self.callback)
        if self.pin.value() != self.state:
            self.callback(self.pin)

    def update(self, now):
        if not self.pending:
            return None
        current = self.pin.value()
        if not self.debouncing:
            self.candidate = current
            self.since = now
            self.debouncing = True
        elif current != self.candidate:
            self.candidate = current
            self.since = now

        if time.ticks_diff(now, self.since) < DEBOUNCE_MS:
            return None

        event = None
        if not self.initializing and self.candidate != self.state:
            event = self.candidate

        self.state = self.candidate
        self.initializing = False
        self.debouncing = False
        self.pending = False
        self._arm()
        return event

    def close(self):
        self.pin.irq(handler=None)

class AmbientLight:
    def __init__(self, sensor, display):
        self.sensor = sensor
        self.display = display
        self.raw = 0
        self.filtered = None
        self.contrast = None

    def update(self):
        self.raw = self.sensor.read()
        if self.filtered is None:
            self.filtered = self.raw
        else:
            self.filtered += SMOOTHING_ALPHA * (self.raw - self.filtered)

        level = (self.filtered - LIGHT_DARK) / (LIGHT_BRIGHT - LIGHT_DARK)
        level = max(0.0, min(1.0, level))
        target = int(CONTRAST_MIN + level * (CONTRAST_MAX - CONTRAST_MIN) + 0.5)
        if target != self.contrast:
            self.display.contrast(target)
            self.contrast = target

class Watch:
    def __init__(self, rtc, display, ambient):
        self.rtc = rtc
        self.display = display
        self.ambient = ambient

    def on_press(self, name):
        current = list(self.rtc.datetime())
        if name == "A":
            current[4] = (current[4] + 1) % 24
        elif name == "B":
            current[5] = (current[5] + 1) % 60
        else:
            current[6] = 0
            current[7] = 0
        self.rtc.datetime(tuple(current))
        return True

    def draw(self):
        current = self.rtc.datetime()
        self.display.fill(0)
        self.display.text(time_text(current), 32, 8, 1)
        self.display.text("Light:%4d Br:%3d" % (self.ambient.raw, self.ambient.contrast), 0, 16, 1)
        self.display.text("A:H+ B:M+ C:S=0", 0, 24, 1)
        self.display.show()
        return True

def main():
    rtc = RTC()
    rtc.datetime(START_TIME)

    i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)
    display = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)
    
    sensor = ADC(Pin(LIGHT_PIN))
    sensor.atten(ADC.ATTN_11DB)
    sensor.width(ADC.WIDTH_12BIT)
    ambient = AmbientLight(sensor, display)
    ambient.update()

    watch = Watch(rtc, display, ambient)
    buttons = [DebouncedButton("A", BUTTON_A_PIN), DebouncedButton("B", BUTTON_B_PIN), DebouncedButton("C", BUTTON_C_PIN)]

    now = time.ticks_ms()
    next_draw = now
    next_sample = time.ticks_add(now, LIGHT_SAMPLE_MS)

    try:
        while True:
            now = time.ticks_ms()
            for button in buttons:
                event = button.update(now)
                if event == 0:
                    if watch.on_press(button.name):
                        next_draw = now

            if time.ticks_diff(now, next_sample) >= 0:
                next_sample = time.ticks_add(now, LIGHT_SAMPLE_MS)
                ambient.update()

            if time.ticks_diff(now, next_draw) >= 0:
                next_draw = time.ticks_add(now, DISPLAY_MS)
                watch.draw()

            time.sleep_ms(2)
    finally:
        for button in buttons:
            button.close()

if __name__ == "__main__":
    main()