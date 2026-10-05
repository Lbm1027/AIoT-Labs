from machine import Pin, I2C, RTC, ADC, PWM
import time
import ssd1306

CHECKPOINT = 3
AUTO_BRIGHTNESS = False
SDA_PIN = 22
SCL_PIN = 20
BUTTON_A_PIN = 15
BUTTON_B_PIN = 33
BUTTON_C_PIN = 14
LIGHT_PIN = 39  # A3
LED_PIN = 13
PIEZO_PIN = 27

OLED_WIDTH = 128
OLED_HEIGHT = 32
OLED_ADDR = 0x3C
I2C_FREQ = 400000
DEBOUNCE_MS = 30
DISPLAY_MS = 100
LIGHT_SAMPLE_MS = 50
LIGHT_PRINT_MS = 500
ALARM_CHECK_MS = 50
ALARM_PULSE_MS = 250
ALARM_FREQ = 2000
ALARM_DUTY = 32768
ALARM_HOUR = 9
ALARM_MINUTE = 1
FIXED_CONTRAST = 180

# Provisional Check2 calibration; replace with measured dark/bright readings.
LIGHT_DARK = 0
LIGHT_BRIGHT = 350
CONTRAST_MIN = 8
CONTRAST_MAX = 255
SMOOTHING_ALPHA = 0.25

# Fixed group setting: Wednesday, 2026-09-30, 09:00:00 on every startup.
START_TIME = (2026, 9, 30, 2, 9, 0, 0, 0)


def date_text(current):
    return "%04d-%02d-%02d" % (current[0], current[1], current[2])


def time_text(current):
    return "%02d:%02d:%02d" % (current[4], current[5], current[6])


class DebouncedButton:
    """Confirm a stable input in the main loop after a GPIO interrupt."""

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
        # Keep the callback short; do all timing and actions in the main loop.
        if not self.pending:
            self.pending = True
            pin.irq(handler=None)

    def _arm(self):
        self.pin.irq(
            trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
            handler=self.callback
        )
        # Recover an edge that occurred while this pin's interrupt was masked.
        if self.pin.value() != self.state:
            self.callback(self.pin)

    def update(self, now):
        # Return 0 for a confirmed press, 1 for release, or None for no event.
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

        # Establish the initial state without treating a held startup button
        # as a new press. Release it and press again to perform an action.
        self.state = self.candidate
        self.initializing = False
        self.debouncing = False
        self.pending = False
        self._arm()
        return event

    def close(self):
        self.pin.irq(handler=None)


class AmbientLight:
    """Read the light sensor and smoothly adjust the OLED contrast."""

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

        # Also supports sensors whose reading decreases in brighter light:
        # enter the actual dark/bright readings, even if DARK > BRIGHT.
        level = (self.filtered - LIGHT_DARK) / (LIGHT_BRIGHT - LIGHT_DARK)
        level = max(0.0, min(1.0, level))
        target = int(CONTRAST_MIN + level * (CONTRAST_MAX - CONTRAST_MIN) + 0.5)
        if target != self.contrast:
            self.display.contrast(target)
            self.contrast = target


def rtc_seconds(current):
    # RTC.datetime and time.mktime use different tuple field orders.
    return time.mktime((current[0], current[1], current[2],
                        current[4], current[5], current[6], current[3], 0))


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
            day = "tomorrow"
        else:
            day = "today"
        self.enabled = True
        print("Alarm ON: %02d:%02d:00 (%s)" % (self.hour, self.minute, day))

    def clock_changed(self, current):
        # An intentional clock adjustment is not elapsed time.
        if self.enabled:
            self.arm(current)

    def update(self, current, now):
        # Crossing a deadline still triggers if I2C delayed an iteration.
        if self.enabled and rtc_seconds(current) >= self.due:
            self.enabled = False
            self.due = None
            self.ringing = True
            self._outputs(True)
            self.next_pulse = time.ticks_add(now, ALARM_PULSE_MS)
            print("ALARM! Press any OLED button to stop.")
            return True

        if self.ringing and time.ticks_diff(now, self.next_pulse) >= 0:
            self._outputs(not self.on_phase)
            self.next_pulse = time.ticks_add(now, ALARM_PULSE_MS)
        return False


class Watch:
    def __init__(self, rtc, display, alarm, ambient=None):
        self.rtc = rtc
        self.display = display
        self.alarm = alarm
        self.ambient = ambient
        self.editing = False
        self.last_frame = None
        self.last_printed_time = None

    def on_press(self, name):
        if name not in ("A", "B", "C"):
            return False

        if self.alarm.ringing:
            self.alarm.stop()
            self.editing = False
            print("Alarm stopped; OFF. Open the editor to set it again.")
            return True  # Consume this press; do not also change the clock.

        if name == "C":
            if self.editing:
                self.alarm.arm(self.rtc.datetime())
                self.editing = False
            else:
                # Pause a previously armed alarm while changing its time.
                self.alarm.stop()
                self.editing = True
                print("SET ALARM - A: hour +1; B: minute +1; C: save/ON")
            return True

        if self.editing:
            if name == "A":
                self.alarm.hour = (self.alarm.hour + 1) % 24
            else:
                self.alarm.minute = (self.alarm.minute + 1) % 60
            print("Alarm setting: %02d:%02d" % (self.alarm.hour, self.alarm.minute))
            return True

        current = list(self.rtc.datetime())
        field, limit = (4, 24) if name == "A" else (5, 60)
        current[field] = (current[field] + 1) % limit
        self.rtc.datetime(tuple(current))
        self.alarm.clock_changed(self.rtc.datetime())
        print("Time adjusted:", time_text(current))
        return True

    def draw(self):
        current = self.rtc.datetime()
        light = (self.ambient.raw, self.ambient.contrast) if self.ambient else ()
        frame = current[:7] + (self.editing, self.alarm.hour, self.alarm.minute,
                               self.alarm.enabled, self.alarm.ringing) + light
        if frame == self.last_frame:
            return False

        self.display.fill(0)
        if self.alarm.ringing:
            self.display.text("ALARM!", 40, 0, 1)
            self.display.text(time_text(current), 32, 8, 1)
            self.display.text("Set %02d:%02d" %
                              (self.alarm.hour, self.alarm.minute), 0, 16, 1)
            self.display.text("Any key: stop", 0, 24, 1)
        elif self.editing:
            self.display.text("SET ALARM", 0, 0, 1)
            self.display.text("%02d:%02d" %
                              (self.alarm.hour, self.alarm.minute), 44, 8, 1)
            self.display.text("Now " + time_text(current), 0, 16, 1)
            self.display.text("A:H+ B:M+ C:OK", 0, 24, 1)
        else:
            self.display.text(time_text(current), 32, 0, 1)
            self.display.text("AL %02d:%02d %s" %
                              (self.alarm.hour, self.alarm.minute,
                               "ON" if self.alarm.enabled else "OFF"), 0, 8, 1)
            if self.ambient:
                self.display.text("L:%4d Br:%3d" %
                                  (self.ambient.raw, self.ambient.contrast), 0, 16, 1)
            else:
                self.display.text(date_text(current), 0, 16, 1)
            self.display.text("A:H+ B:M+ C:AL", 0, 24, 1)
        self.display.show()
        self.last_frame = frame
        if current[:7] != self.last_printed_time:
            print("Time:", date_text(current), time_text(current))
            self.last_printed_time = current[:7]
        return True


def main():
    used_pins = (SDA_PIN, SCL_PIN, BUTTON_A_PIN, BUTTON_B_PIN, BUTTON_C_PIN,
                 LED_PIN, PIEZO_PIN)
    if AUTO_BRIGHTNESS:
        used_pins += (LIGHT_PIN,)
    if len(set(used_pins)) != len(used_pins):
        raise ValueError("Screen, buttons, light sensor and alarm need separate GPIOs")
    if AUTO_BRIGHTNESS and LIGHT_DARK == LIGHT_BRIGHT:
        raise ValueError("LIGHT_DARK and LIGHT_BRIGHT must be different")
    if AUTO_BRIGHTNESS and not 0 <= CONTRAST_MIN < CONTRAST_MAX <= 255:
        raise ValueError("Contrast settings must satisfy 0 <= MIN < MAX <= 255")

    buttons = []
    piezo = None
    led = Pin(LED_PIN, Pin.OUT, value=0)
    try:
        piezo = PWM(Pin(PIEZO_PIN), freq=ALARM_FREQ, duty_u16=0)
        rtc = RTC()
        rtc.datetime(START_TIME)
        i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)
        devices = i2c.scan()
        print("I2C devices:", [hex(address) for address in devices])
        if OLED_ADDR not in devices:
            raise OSError("OLED 0x3C not found; check power, SDA=22 and SCL=20")
        display = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)
        ambient = None
        if AUTO_BRIGHTNESS:
            sensor = ADC(Pin(LIGHT_PIN))
            sensor.atten(ADC.ATTN_11DB)
            sensor.width(ADC.WIDTH_12BIT)
            ambient = AmbientLight(sensor, display)
            ambient.update()
        else:
            display.contrast(FIXED_CONTRAST)

        alarm = Alarm(led, piezo)
        watch = Watch(rtc, display, alarm, ambient)
        for name, number in (("A", BUTTON_A_PIN),
                             ("B", BUTTON_B_PIN), ("C", BUTTON_C_PIN)):
            buttons.append(DebouncedButton(name, number))

        print("LAB3 CHECK%d - Clock and OLED alarm" % CHECKPOINT)
        print("CLOCK: A hour+; B minute+; C alarm editor")
        print("ALARM: A hour+; B minute+; C save/ON; any button stops ringing")
        if ambient:
            print("Auto brightness: GPIO%d; dark=%d, bright=%d" %
                  (LIGHT_PIN, LIGHT_DARK, LIGHT_BRIGHT))

        now = time.ticks_ms()
        next_draw = next_alarm_check = next_print = now
        next_sample = time.ticks_add(now, LIGHT_SAMPLE_MS)
        while True:
            now = time.ticks_ms()
            was_ringing = alarm.ringing
            for button in buttons:
                event = button.update(now)
                if event is not None:
                    if event == 0:
                        print("Button %s pressed: 0" % button.name)
                        # Simultaneous stop presses must not also edit time.
                        if was_ringing and not alarm.ringing:
                            continue
                        if watch.on_press(button.name):
                            next_draw = now
                    else:
                        print("Button %s released: 1" % button.name)

            now = time.ticks_ms()
            if ambient and time.ticks_diff(now, next_sample) >= 0:
                next_sample = time.ticks_add(now, LIGHT_SAMPLE_MS)
                ambient.update()
            if time.ticks_diff(now, next_alarm_check) >= 0:
                next_alarm_check = time.ticks_add(now, ALARM_CHECK_MS)
                if alarm.update(rtc.datetime(), now):
                    next_draw = now
            if time.ticks_diff(now, next_draw) >= 0:
                next_draw = time.ticks_add(now, DISPLAY_MS)
                watch.draw()
            if ambient and time.ticks_diff(now, next_print) >= 0:
                next_print = time.ticks_add(now, LIGHT_PRINT_MS)
                print("Light:", ambient.raw, "Contrast:", ambient.contrast)
            time.sleep_ms(2)
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        for button in buttons:
            button.close()
        led.value(0)
        if piezo is not None:
            piezo.duty_u16(0)
            piezo.deinit()
        Pin(PIEZO_PIN, Pin.OUT, value=0)


# main.py starts the program with just one import.
main()
