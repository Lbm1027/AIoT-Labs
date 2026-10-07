from machine import Pin, I2C, RTC, ADC, PWM
import time
import ssd1306

SDA_PIN = 22
SCL_PIN = 20
BUTTON_A_PIN = 15
BUTTON_B_PIN = 33
BUTTON_C_PIN = 14
LIGHT_PIN = 39
LED_PIN = 13
PIEZO_PIN = 27

OLED_WIDTH = 128
OLED_HEIGHT = 32
OLED_ADDR = 0x3C
I2C_FREQ = 400000
DEBOUNCE_MS = 30
DISPLAY_MS = 100
LIGHT_SAMPLE_MS = 50
ALARM_CHECK_MS = 50
ALARM_PULSE_MS = 250
ALARM_FREQ = 2000
ALARM_DUTY = 32768
ALARM_HOUR = 9
ALARM_MINUTE = 1

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

def rtc_seconds(current):
    return time.mktime((current[0], current[1], current[2], current[4], current[5], current[6], current[3], 0))

class Alarm:
    def __init__(self, led, piezo):
        self.led = led
        self.piezo = piezo
        self.hour = ALARM_HOUR
        self.minute = ALARM_MINUTE
        self.enabled = False
        self.ringing = False
        self.due = None
        self.on_phase = False
        self.next_pulse = 0
        self._outputs(False)

    def _outputs(self, active):
        self.led.value(1 if active else 0)
        self.piezo.duty_u16(ALARM_DUTY if active else 0)
        self.on_phase = active

    def stop(self):
        self.enabled = False
        self.ringing = False
        self.due = None
        self._outputs(False)

    def arm(self, current):
        self.stop()
        target = list(current)
        target[4], target[5], target[6], target[7] = self.hour, self.minute, 0, 0
        self.due = rtc_seconds(target)
        if self.due <= rtc_seconds(current):
            self.due += 24 * 60 * 60
        self.enabled = True

    def clock_changed(self, current):
        if self.enabled:
            self.arm(current)

    def update(self, current, now):
        if self.enabled and rtc_seconds(current) >= self.due:
            self.enabled = False
            self.due = None
            self.ringing = True
            self._outputs(True)
            self.next_pulse = time.ticks_add(now, ALARM_PULSE_MS)
            return True

        if self.ringing and time.ticks_diff(now, self.next_pulse) >= 0:
            self._outputs(not self.on_phase)
            self.next_pulse = time.ticks_add(now, ALARM_PULSE_MS)
        return False

class Watch:
    def __init__(self, rtc, display, alarm, ambient):
        self.rtc = rtc
        self.display = display
        self.alarm = alarm
        self.ambient = ambient
        self.editing = False

    def on_press(self, name):
        if self.alarm.ringing:
            self.alarm.stop()
            self.editing = False
            return True

        if name == "C":
            if self.editing:
                self.alarm.arm(self.rtc.datetime())
                self.editing = False
            else:
                self.alarm.stop()
                self.editing = True
            return True

        if self.editing:
            if name == "A":
                self.alarm.hour = (self.alarm.hour + 1) % 24
            else:
                self.alarm.minute = (self.alarm.minute + 1) % 60
            return True

        current = list(self.rtc.datetime())
        field, limit = (4, 24) if name == "A" else (5, 60)
        current[field] = (current[field] + 1) % limit
        self.rtc.datetime(tuple(current))
        self.alarm.clock_changed(self.rtc.datetime())
        return True

    def draw(self):
        current = self.rtc.datetime()
        self.display.fill(0)
        if self.alarm.ringing:
            self.display.text("ALARM!", 40, 0, 1)
            self.display.text(time_text(current), 32, 8, 1)
            self.display.text("Any key: stop", 0, 24, 1)
        elif self.editing:
            self.display.text("SET ALARM", 0, 0, 1)
            self.display.text("%02d:%02d" % (self.alarm.hour, self.alarm.minute), 44, 8, 1)
            self.display.text("A:H+ B:M+ C:OK", 0, 24, 1)
        else:
            self.display.text(time_text(current), 32, 0, 1)
            self.display.text("AL %02d:%02d %s" % (self.alarm.hour, self.alarm.minute, "ON" if self.alarm.enabled else "OFF"), 0, 8, 1)
            self.display.text("L:%4d Br:%3d" % (self.ambient.raw, self.ambient.contrast), 0, 16, 1)
            self.display.text("A:H+ B:M+ C:AL", 0, 24, 1)
        self.display.show()
        return True

def main():
    buttons = []
    led = Pin(LED_PIN, Pin.OUT, value=0)
    try:
        piezo = PWM(Pin(PIEZO_PIN), freq=ALARM_FREQ, duty_u16=0)
        rtc = RTC()
        rtc.datetime(START_TIME)
        i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)
        display = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)
        
        sensor = ADC(Pin(LIGHT_PIN))
        sensor.atten(ADC.ATTN_11DB)
        sensor.width(ADC.WIDTH_12BIT)
        ambient = AmbientLight(sensor, display)
        ambient.update()

        alarm = Alarm(led, piezo)
        watch = Watch(rtc, display, alarm, ambient)
        for name, number in (("A", BUTTON_A_PIN), ("B", BUTTON_B_PIN), ("C", BUTTON_C_PIN)):
            buttons.append(DebouncedButton(name, number))

        now = time.ticks_ms()
        next_draw = next_alarm_check = now
        next_sample = time.ticks_add(now, LIGHT_SAMPLE_MS)
        while True:
            now = time.ticks_ms()
            was_ringing = alarm.ringing
            for button in buttons:
                event = button.update(now)
                if event == 0:
                    if was_ringing and not alarm.ringing:
                        continue
                    if watch.on_press(button.name):
                        next_draw = now

            if time.ticks_diff(now, next_sample) >= 0:
                next_sample = time.ticks_add(now, LIGHT_SAMPLE_MS)
                ambient.update()
            if time.ticks_diff(now, next_alarm_check) >= 0:
                next_alarm_check = time.ticks_add(now, ALARM_CHECK_MS)
                if alarm.update(rtc.datetime(), now):
                    next_draw = now
            if time.ticks_diff(now, next_draw) >= 0:
                next_draw = time.ticks_add(now, DISPLAY_MS)
                watch.draw()
            time.sleep_ms(2)
    finally:
        for button in buttons:
            button.close()
        led.value(0)
        piezo.deinit()

if __name__ == "__main__":
    main()