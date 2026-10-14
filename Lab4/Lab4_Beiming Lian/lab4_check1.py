from machine import Pin, I2C, RTC, ADC, PWM, SPI
import time
import ssd1306

CHECKPOINT = 1
AUTO_BRIGHTNESS = True
SDA_PIN = 22
SCL_PIN = 20
BUTTON_A_PIN = 15
BUTTON_B_PIN = 33
BUTTON_C_PIN = 14
LIGHT_PIN = 39  # A3
LED_PIN = 13
PIEZO_PIN = 27

# Your SPI wiring on Feather ESP32 V2.
SCK_PIN = 5    # ADXL345 SCL -> SCK
MOSI_PIN = 19  # ADXL345 SDA -> MO
MISO_PIN = 21  # ADXL345 SDO -> MI
CS_PIN = 4     # ADXL345 CS -> A5

TILT_SAMPLE_MS = 50
SCROLL_MS = 100
SCROLL_STEP_PX = 2
TILT_START_G = 0.30
TILT_STOP_G = 0.20
TILT_ALPHA = 0.25
# Axis 0 = sensor X, 1 = sensor Y. Match these to the physical mounting.
# Positive screen X moves right; positive screen Y moves down.
SCROLL_X_AXIS = 0
SCROLL_Y_AXIS = 1
SCROLL_X_SIGN = 1  # Set to -1 if left/right are reversed.
SCROLL_Y_SIGN = 1  # Set to -1 if up/down are reversed.

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
CONTRAST_MIN = 4
CONTRAST_MAX = 255
SMOOTHING_ALPHA = 0.25

# Fixed group setting: Wednesday, 2026-09-30, 09:00:00 on every startup.
START_TIME = (2026, 9, 30, 2, 9, 0, 0, 0)


def date_text(current):
    return "%04d-%02d-%02d" % (current[0], current[1], current[2])


def time_text(current):
    return "%02d:%02d:%02d" % (current[4], current[5], current[6])


class ADXL345:
    def __init__(self, spi, cs):
        self.spi = spi
        self.cs = cs
        self.cs.value(1)

    def write_register(self, address, value):
        # Bit 7 = 0 (write), bit 6 = 0 (single register).
        self.cs.value(0)
        try:
            self.spi.write(bytes((address & 0x3F, value)))
        finally:
            self.cs.value(1)

    def read_registers(self, address, count=1):
        command = 0x80 | (address & 0x3F)
        if count > 1:
            command |= 0x40
        self.cs.value(0)
        try:
            self.spi.write(bytes((command,)))
            return self.spi.read(count)
        finally:
            self.cs.value(1)

    def initialize(self):
        device_id = self.read_registers(0x00)[0]
        print("ADXL345 ID: 0x%02X (expected 0xE5)" % device_id)
        if device_id != 0xE5:
            raise RuntimeError("ADXL345 not detected. Check SPI pins and power.")

        self.write_register(0x2D, 0x00)  # Standby while configuring.
        settings = (
            (0x31, 0x08),  # Full resolution, +/-2 g, 4-wire SPI.
            (0x2C, 0x0A),  # Normal power, 100 Hz sensor output rate.
            (0x2E, 0x00),  # Disable interrupt outputs; use polling.
            (0x38, 0x00),  # FIFO bypass: read the latest sample.
            (0x2D, 0x08),  # Set Measure bit to start measuring.
        )
        for address, value in settings:
            self.write_register(address, value)
            actual = self.read_registers(address)[0]
            if actual != value:
                raise RuntimeError(
                    "Register 0x%02X: wrote 0x%02X, read 0x%02X"
                    % (address, value, actual)
                )
        time.sleep_ms(20)

    @staticmethod
    def signed16(low, high):
        value = low | (high << 8)
        return value - 65536 if value & 0x8000 else value

    def read_xyz(self):
        # 0x80 (read) | 0x40 (multiple bytes) | 0x32 = 0xF2.
        data = self.read_registers(0x32, 6)
        return (
            self.signed16(data[0], data[1]),
            self.signed16(data[2], data[3]),
            self.signed16(data[4], data[5]),
        )


class TiltScroll:
    """Filter gravity readings and move the screen without blocking other work."""

    def __init__(self, sensor):
        self.sensor = sensor
        self.xyz = (0.0, 0.0, 0.0)
        self.filtered = None
        self.dx = self.dy = 0
        self.x = self.y = 0

    @staticmethod
    def direction(value, previous):
        if value >= TILT_START_G:
            return 1
        if value <= -TILT_START_G:
            return -1
        # A smaller stop threshold prevents chatter around the start threshold.
        if previous == 1 and value > TILT_STOP_G:
            return 1
        if previous == -1 and value < -TILT_STOP_G:
            return -1
        return 0

    def update(self):
        raw = self.sensor.read_xyz()
        self.xyz = tuple(value / 256.0 for value in raw)
        if self.filtered is None:
            self.filtered = list(self.xyz)
        else:
            for index in range(3):
                self.filtered[index] += TILT_ALPHA * (self.xyz[index] - self.filtered[index])
        horizontal = self.filtered[SCROLL_X_AXIS] * SCROLL_X_SIGN
        vertical = self.filtered[SCROLL_Y_AXIS] * SCROLL_Y_SIGN
        self.dx = self.direction(horizontal, self.dx)
        self.dy = self.direction(vertical, self.dy)

    def step(self):
        self.x = (self.x + self.dx * SCROLL_STEP_PX) % OLED_WIDTH
        self.y = (self.y + self.dy * SCROLL_STEP_PX) % OLED_HEIGHT


class TextCanvas:
    """Store text commands for SSD1306 drivers with fill/text/show only."""

    def __init__(self):
        self.background = 0
        self.lines = []

    def fill(self, color):
        self.background = color
        self.lines = []

    def text(self, message, x, y, color=1):
        self.lines.append((message, x, y, color))


def show_wrapped(display, canvas, x, y):
    """Redraw text at wrapped positions without requiring display.blit()."""
    display.fill(canvas.background)
    for message, original_x, original_y, color in canvas.lines:
        left = (original_x + x) % OLED_WIDTH
        top = (original_y + y) % OLED_HEIGHT
        # The standard SSD1306 text font is 8x8. Negative coordinates clip
        # the overflow copy so that it reappears at the opposite edge.
        crosses_right = left + len(message) * 8 > OLED_WIDTH
        crosses_bottom = top + 8 > OLED_HEIGHT
        display.text(message, left, top, color)
        if crosses_right:
            display.text(message, left - OLED_WIDTH, top, color)
        if crosses_bottom:
            display.text(message, left, top - OLED_HEIGHT, color)
        if crosses_right and crosses_bottom:
            display.text(message, left - OLED_WIDTH, top - OLED_HEIGHT, color)
    display.show()


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
    def __init__(self, rtc, display, alarm, ambient=None, tilt=None):
        self.rtc = rtc
        self.display = display
        self.alarm = alarm
        self.ambient = ambient
        self.tilt = tilt
        self.canvas = TextCanvas()
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
        offset = (self.tilt.x, self.tilt.y) if self.tilt else (0, 0)
        frame = offset + current[:7] + (self.editing, self.alarm.hour, self.alarm.minute,
                               self.alarm.enabled, self.alarm.ringing) + light
        if frame == self.last_frame:
            return False

        self.canvas.fill(0)
        if self.alarm.ringing:
            self.canvas.text("ALARM!", 40, 0, 1)
            self.canvas.text(time_text(current), 32, 8, 1)
            self.canvas.text("Set %02d:%02d" %
                              (self.alarm.hour, self.alarm.minute), 0, 16, 1)
            self.canvas.text("Any key: stop", 0, 24, 1)
        elif self.editing:
            self.canvas.text("SET ALARM", 0, 0, 1)
            self.canvas.text("%02d:%02d" %
                              (self.alarm.hour, self.alarm.minute), 44, 8, 1)
            self.canvas.text("Now " + time_text(current), 0, 16, 1)
            self.canvas.text("A:H+ B:M+ C:OK", 0, 24, 1)
        else:
            self.canvas.text(time_text(current), 32, 0, 1)
            self.canvas.text("AL %02d:%02d %s" %
                              (self.alarm.hour, self.alarm.minute,
                               "ON" if self.alarm.enabled else "OFF"), 0, 8, 1)
            if self.ambient:
                self.canvas.text("L:%4d Br:%3d" %
                                  (self.ambient.raw, self.ambient.contrast), 0, 16, 1)
            else:
                self.canvas.text(date_text(current), 0, 16, 1)
            self.canvas.text("A:H+ B:M+ C:AL", 0, 24, 1)
        show_wrapped(self.display, self.canvas, *offset)
        self.last_frame = frame
        if current[:7] != self.last_printed_time:
            print("Time:", date_text(current), time_text(current))
            self.last_printed_time = current[:7]
        return True


def main():
    used_pins = (SDA_PIN, SCL_PIN, BUTTON_A_PIN, BUTTON_B_PIN, BUTTON_C_PIN,
                 LED_PIN, PIEZO_PIN, SCK_PIN, MOSI_PIN, MISO_PIN, CS_PIN)
    if AUTO_BRIGHTNESS:
        used_pins += (LIGHT_PIN,)
    if len(set(used_pins)) != len(used_pins):
        raise ValueError("OLED, buttons, light, alarm and SPI need separate GPIOs")
    if AUTO_BRIGHTNESS and LIGHT_DARK == LIGHT_BRIGHT:
        raise ValueError("LIGHT_DARK and LIGHT_BRIGHT must be different")
    if AUTO_BRIGHTNESS and not 0 <= CONTRAST_MIN < CONTRAST_MAX <= 255:
        raise ValueError("Contrast settings must satisfy 0 <= MIN < MAX <= 255")

    if {SCROLL_X_AXIS, SCROLL_Y_AXIS} != {0, 1}:
        raise ValueError("Scroll axes must be 0 and 1, in either order")
    if SCROLL_X_SIGN not in (-1, 1) or SCROLL_Y_SIGN not in (-1, 1):
        raise ValueError("Scroll signs must be +1 or -1")
    if not 0 <= TILT_STOP_G < TILT_START_G <= 1:
        raise ValueError("Tilt thresholds must satisfy 0 <= STOP < START <= 1")
    if not 0 < TILT_ALPHA <= 1 or SCROLL_STEP_PX <= 0:
        raise ValueError("Tilt smoothing and scroll step must be positive")

    buttons = []
    piezo = None
    spi = None
    accelerometer = None
    cs = None
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

        cs = Pin(CS_PIN, Pin.OUT, value=1)
        spi = SPI(1, baudrate=500000, polarity=1, phase=1, bits=8,
                  firstbit=SPI.MSB, sck=Pin(SCK_PIN),
                  mosi=Pin(MOSI_PIN), miso=Pin(MISO_PIN))
        accelerometer = ADXL345(spi, cs)
        accelerometer.initialize()
        tilt = TiltScroll(accelerometer)
        tilt.update()

        alarm = Alarm(led, piezo)
        watch = Watch(rtc, display, alarm, ambient, tilt)
        for name, number in (("A", BUTTON_A_PIN),
                             ("B", BUTTON_B_PIN), ("C", BUTTON_C_PIN)):
            buttons.append(DebouncedButton(name, number))

        print("LAB4 CHECK%d - Watch, alarm and tilt scrolling" % CHECKPOINT)
        print("TILT: move the whole screen; edges wrap; level stops scrolling")
        print("OLED renderer: text wrap (no blit required)")
        print("SPI: SCK=5 MO=19 MI=21 CS=A5/GPIO4")
        print("CLOCK: A hour+; B minute+; C alarm editor")
        print("ALARM: A hour+; B minute+; C save/ON; any button stops ringing")
        if ambient:
            print("Auto brightness: GPIO%d; dark=%d, bright=%d" %
                  (LIGHT_PIN, LIGHT_DARK, LIGHT_BRIGHT))

        now = time.ticks_ms()
        next_draw = next_alarm_check = next_print = now
        next_sample = time.ticks_add(now, LIGHT_SAMPLE_MS)
        next_tilt = time.ticks_add(now, TILT_SAMPLE_MS)
        next_scroll = time.ticks_add(now, SCROLL_MS)
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
            if time.ticks_diff(now, next_tilt) >= 0:
                next_tilt = time.ticks_add(now, TILT_SAMPLE_MS)
                tilt.update()
            if time.ticks_diff(now, next_scroll) >= 0:
                next_scroll = time.ticks_add(now, SCROLL_MS)
                tilt.step()
            if time.ticks_diff(now, next_draw) >= 0:
                next_draw = time.ticks_add(now, DISPLAY_MS)
                watch.draw()
            if time.ticks_diff(now, next_print) >= 0:
                next_print = time.ticks_add(now, LIGHT_PRINT_MS)
                if ambient:
                    print("Light:", ambient.raw, "Contrast:", ambient.contrast)
                print("Accel g: X=%+.2f Y=%+.2f Z=%+.2f | Scroll: %d,%d" %
                      (tilt.xyz[0], tilt.xyz[1], tilt.xyz[2], tilt.dx, tilt.dy))
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
        if accelerometer is not None:
            try:
                accelerometer.write_register(0x2D, 0x00)
            except OSError:
                pass  # Keep an earlier hardware error visible during cleanup.
        if cs is not None:
            cs.value(1)
        if spi is not None:
            spi.deinit()


# main.py starts the program with just one import.
main()