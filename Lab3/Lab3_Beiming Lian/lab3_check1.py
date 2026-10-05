from machine import Pin, I2C, RTC
import time
import ssd1306

# Match these numbers to the actual wiring and MicroPython firmware.
SDA_PIN = 22
SCL_PIN = 20  # From the slides; verify support on the actual board.
BUTTON_A_PIN = 15
BUTTON_B_PIN = 33
BUTTON_C_PIN = 14

OLED_WIDTH = 128
OLED_HEIGHT = 32
OLED_ADDR = 0x3C
I2C_FREQ = 400000
DEBOUNCE_MS = 30
DISPLAY_MS = 100

# (year, month, day, weekday, hour, minute, second, subseconds)
# Fixed group setting, reset on every boot: Wednesday, 2026-09-30, 09:00:00.
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


class Watch:
    def __init__(self, rtc, display):
        self.rtc = rtc
        self.display = display
        self.last_frame = None
        self.last_printed_time = None

    def on_press(self, name):
        if name not in ("A", "B", "C"):
            return False

        # Read the RTC NOW, so editing never restores an old screen snapshot.
        current = list(self.rtc.datetime())
        if name == "A":
            current[4] = (current[4] + 1) % 24
        elif name == "B":
            current[5] = (current[5] + 1) % 60
        else:
            current[6] = 0
            current[7] = 0  # Start the next second from a whole-second boundary.

        # Manual hour/minute adjustment does not carry into other fields.
        self.rtc.datetime(tuple(current))
        print("Time adjusted:", time_text(current))
        return True

    def draw(self):
        current = self.rtc.datetime()
        frame = current[:7]
        if frame == self.last_frame:
            return False

        self.display.fill(0)
        self.display.text(date_text(current), 0, 0, 1)
        self.display.text(time_text(current), 32, 8, 1)
        self.display.text("A:H+ B:M+ C:S=0", 0, 24, 1)

        self.display.show()
        self.last_frame = frame

        if current[:7] != self.last_printed_time:
            print("Time:", date_text(current), time_text(current))
            self.last_printed_time = current[:7]
        return True


def main():
    used_pins = (SDA_PIN, SCL_PIN, BUTTON_A_PIN, BUTTON_B_PIN, BUTTON_C_PIN)
    if len(set(used_pins)) != len(used_pins):
        raise ValueError("OLED and buttons must use different GPIO pins")

    # Task 1: set the fixed starting time once on program startup.
    rtc = RTC()
    rtc.datetime(START_TIME)

    # Task 2: initialise the I2C screen and check that it answers.
    try:
        i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)
        devices = i2c.scan()
    except (ValueError, OSError):
        print("I2C setup/scan failed: SDA=%d, SCL=%d" % (SDA_PIN, SCL_PIN))
        print("Check wiring and whether this firmware supports these pins.")
        if SCL_PIN == 20:
            print("Some ESP32 MicroPython firmware cannot use SCL=20.")
            print("Button C uses GPIO14; do not also use GPIO14 for SCL.")
        raise
    print("I2C devices:", [hex(address) for address in devices])
    if OLED_ADDR not in devices:
        raise OSError(
            "OLED 0x%02X not found; check 3V/GND, SDA=%d and SCL=%d"
            % (OLED_ADDR, SDA_PIN, SCL_PIN)
        )

    display = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)
    watch = Watch(rtc, display)
    buttons = []

    print("LAB3 CHECK1 - RTC, OLED, three debounced buttons")
    print("A: hour +1; B: minute +1; C: seconds = 0")

    try:
        # Task 3: each button has its own interrupt and debounce state.
        for name, number in (("A", BUTTON_A_PIN),
                             ("B", BUTTON_B_PIN),
                             ("C", BUTTON_C_PIN)):
            buttons.append(DebouncedButton(name, number))

        next_draw = time.ticks_ms()
        while True:
            now = time.ticks_ms()
            for button in buttons:
                event = button.update(now)
                if event is not None:
                    if event == 0:
                        print("Button %s pressed: 0" % button.name)
                        if watch.on_press(button.name):
                            next_draw = now
                    else:
                        print("Button %s released: 1" % button.name)

            now = time.ticks_ms()
            if time.ticks_diff(now, next_draw) >= 0:
                next_draw = time.ticks_add(now, DISPLAY_MS)
                watch.draw()

            # Debouncing never waits in an inner loop; the clock keeps drawing.
            time.sleep_ms(2)

    except KeyboardInterrupt:
        print("Stopped")
    finally:
        for button in buttons:
            button.close()


# main.py starts the program with just: import lab3_check1
main()