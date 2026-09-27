from machine import Pin
import time

BUTTON_PIN = 32
LED_PIN = 13
DEBOUNCE_MS = 30

# Button connects GPIO32 to GND when pressed.
# LED is active high: GPIO13 -> resistor -> LED -> GND.
# Released = LED ON; pressed = LED OFF.
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
button.irq(handler=None)
led = Pin(LED_PIN, Pin.OUT, value=1)
time.sleep_ms(DEBOUNCE_MS)

stable_state = button.value()
led.value(stable_state)
pending = False


def button_irq(pin):
    global pending

    # Disable button interrupts while debouncing.
    button.irq(handler=None)
    pending = True


def enable_button_irq():
    button.irq(
        trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
        handler=button_irq
    )


print("Button test started. Hold = LED OFF; release = LED ON.")

try:
    enable_button_irq()
    if button.value() != stable_state:
        button_irq(button)

    while True:
        if pending:
            pending = False

            # Wait until the input remains unchanged for 30 ms.
            candidate = button.value()
            stable_since = time.ticks_ms()

            while True:
                current = button.value()
                now = time.ticks_ms()

                if current != candidate:
                    candidate = current
                    stable_since = now

                if time.ticks_diff(now, stable_since) >= DEBOUNCE_MS:
                    break

                time.sleep_ms(1)

            # Update LED and print only confirmed state changes.
            if candidate != stable_state:
                stable_state = candidate
                led.value(stable_state)
                if stable_state == 0:
                    print("Button pressed:", stable_state, "- LED OFF")
                else:
                    print("Button released:", stable_state, "- LED ON")

            # Resume interrupts for the next transition.
            enable_button_irq()

            # Catch a change that occurred just before re-enabling.
            if button.value() != stable_state:
                button_irq(button)

        time.sleep_ms(1)

except KeyboardInterrupt:
    print("Stopped")

finally:
    button.irq(handler=None)
    led.off()