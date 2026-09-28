from machine import Pin, ADC, PWM
import time

# pins for button, LED, piezo buzzer, and light sensor
BUTTON_PIN = 32
LED_PIN = 13
PIEZO_PIN = 27
LIGHT_SENSOR_PIN = 39

DEBOUNCE_MS = 30

# setup button with pull-up resistor
button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)

# pulse width modulation for LED brightness and piezo pitch
led = PWM(Pin(LED_PIN), freq=1000)
piezo = PWM(Pin(PIEZO_PIN), freq=440) # default starting pitch

# analog to digital converter for light sensor
light_sensor = ADC(Pin(LIGHT_SENSOR_PIN))
light_sensor.atten(ADC.ATTN_11DB)

# keep track of button state and if system is running
stable_state = button.value()
pending = False
system_active = False  # turns true when button is pressed and held


def button_irq(pin):
    global pending
    # turn off interrupt temporarily during debounce
    button.irq(handler=None)
    pending = True


def enable_button_irq():
    button.irq(
        trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
        handler=button_irq
    )


print("Checkpoint 3: Press and hold button to activate light/LED/piezo system.")

try:
    enable_button_irq()
    if button.value() != stable_state:
        button_irq(button)

    while True:
        # check if button was pressed/released to debounce
        if pending:
            pending = False

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

            # verify if the button state actually changed
            if candidate != stable_state:
                stable_state = candidate
                
                # 0 means button is pressed down, 1 means released
                if stable_state == 0:
                    print("Button PRESSED -> System ACTIVATED")
                    system_active = True
                else:
                    print("Button RELEASED -> System DEACTIVATED")
                    system_active = False
                    # turn off everything when letting go
                    led.duty(0)
                    piezo.duty(0)

            enable_button_irq()

            if button.value() != stable_state:
                button_irq(button)

        # while holding the button down, run the sensor loop
        if system_active:
            # read light level from sensor
            light_val = light_sensor.read()
            
            # if pressing the button, the LED should dim based on light
            led_duty = int((light_val / 4095) * 1023)
            led.duty(led_duty)
            
            # if blocking the sensor, the sound should be off
            if light_val < 50:
                piezo.duty(0)
            else:
                # change piezo pitch depending on how much light hits the sensor
                piezo_freq = int(200 + (light_val / 4095) * 1800)
                piezo.freq(piezo_freq)
                piezo.duty(512) # play sound

            # small delay so it doesn't spam readings
            time.sleep_ms(50)
        else:
            time.sleep_ms(10)

except KeyboardInterrupt:
    print("Stopped")

finally:
    button.irq(handler=None)
    led.deinit()
    piezo.deinit()