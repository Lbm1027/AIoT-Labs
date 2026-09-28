from machine import Pin, ADC, PWM
import time

# Same pins as Checkpoints 1 and 2.
LIGHT_PIN = 39 
LED_PIN = 13
BUTTON_PIN = 32
PIEZO_PIN = 27
DEBOUNCE_MS = 30

SAMPLE_MS = 50          # Target: 20 samples per second while active
PRINT_MS = 250          # Print less often than we sample

# Keep the Checkpoint 1 calibration; adjust using your measured readings.
LIGHT_MIN = 0
LIGHT_MAX = 100
MIN_FREQ = 500
MAX_FREQ = 3000

if LIGHT_MAX <= LIGHT_MIN:
    raise ValueError("LIGHT_MAX must be greater than LIGHT_MIN")

# Button connects GPIO32 to GND when pressed: 0=pressed, 1=released.
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(handler=None)

light_sensor = ADC(Pin(LIGHT_PIN))
light_sensor.atten(ADC.ATTN_11DB)
light_sensor.width(ADC.WIDTH_12BIT)

# Start with both outputs off. GPIO13 remains a PWM output throughout.
led = PWM(Pin(LED_PIN), freq=5000, duty_u16=0)
piezo = PWM(Pin(PIEZO_PIN), freq=MIN_FREQ, duty_u16=0)

stable_state = 1
active = False
pending = True         # Confirm the initial button state too
debouncing = False
candidate = button.value()
stable_since = time.ticks_ms()
next_sample = stable_since
next_print = stable_since


def outputs_off():
    led.duty_u16(0)
    piezo.duty_u16(0)


def button_irq(pin):
    global pending

    # Mask this pin while the main loop confirms a stable button state.
    if not pending:
        pending = True
        pin.irq(handler=None)


def enable_button_irq():
    button.irq(
        trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
        handler=button_irq
    )

    # Catch a change that occurred just before interrupts were re-enabled.
    if button.value() != stable_state:
        button_irq(button)


print("LAB2 CHECK3 - Hold = SYSTEM ON; release = SYSTEM OFF.")

try:
    while True:
        now = time.ticks_ms()

        # Same debounce idea as Checkpoint 2, without a waiting inner loop.
        # This lets sensor sampling continue while a button edge settles.
        if pending:
            current = button.value()

            if not debouncing:
                candidate = current
                stable_since = now
                debouncing = True
            elif current != candidate:
                candidate = current
                stable_since = now

            if time.ticks_diff(now, stable_since) >= DEBOUNCE_MS:
                changed = candidate != stable_state
                stable_state = candidate
                active = (stable_state == 0)

                if active and changed:
                    next_sample = now   # Sample immediately after activation
                    next_print = now
                elif not active:
                    outputs_off()

                debouncing = False
                pending = False
                enable_button_irq()

                if changed:
                    if active:
                        print("Button pressed:", stable_state, "- SYSTEM ON")
                    else:
                        print("Button released:", stable_state, "- SYSTEM OFF")

        # Only read the light sensor while the confirmed button state is pressed.
        now = time.ticks_ms()
        if active and time.ticks_diff(now, next_sample) >= 0:
            next_sample = time.ticks_add(now, SAMPLE_MS)
            value = light_sensor.read()

            # Reuse the light-to-output mapping from Checkpoint 1.
            level = (value - LIGHT_MIN) / (LIGHT_MAX - LIGHT_MIN)
            if level < 0:
                level = 0
            elif level > 1:
                level = 1

            duty = int(level * 65535)
            led.duty_u16(duty)

            frequency = int(MIN_FREQ + level * (MAX_FREQ - MIN_FREQ))
            piezo.freq(frequency)
            if level > 0:
                piezo.duty_u16(32768)  # Approximately 50% duty cycle
            else:
                piezo.duty_u16(0)     # Silence at the minimum light level

            if time.ticks_diff(now, next_print) >= 0:
                next_print = time.ticks_add(now, PRINT_MS)
                # Display 0 Hz when the piezo is silent.
                audible_frequency = frequency if level > 0 else 0
                print("Light:", value, "LED duty:", duty,
                      "Piezo frequency:", audible_frequency)

        time.sleep_ms(1)

except KeyboardInterrupt:
    print("Stopped")

finally:
    button.irq(handler=None)
    outputs_off()
    led.deinit()
    piezo.deinit()
    Pin(LED_PIN, Pin.OUT, value=0)
    Pin(PIEZO_PIN, Pin.OUT, value=0)
