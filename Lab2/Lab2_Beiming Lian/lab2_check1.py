from machine import Pin, ADC, PWM
import time

# Pin assignments
LIGHT_PIN = 39   # A3: analog light sensor
LED_PIN = 4      # A5: external LED
PIEZO_PIN = 27   # Confirm this matches the piezo wiring

# Configure the ADC for 12-bit readings
light_sensor = ADC(Pin(LIGHT_PIN))
light_sensor.atten(ADC.ATTN_11DB)
light_sensor.width(ADC.WIDTH_12BIT)

# Temporary light range based on observed readings
# Replace with measured values under dark and bright conditions
LIGHT_MIN = 80
LIGHT_MAX = 200

# Configure PWM outputs
led = PWM(Pin(LED_PIN), freq=5000, duty_u16=0)
piezo = PWM(Pin(PIEZO_PIN), freq=500, duty_u16=0)

MIN_FREQ = 500
MAX_FREQ = 3000

print("LAB2 CHECK1 - ADC AND PWM")

try:
    while True:
        # 1. Read the analog light sensor
        value = light_sensor.read()

        # 2. Normalize the reading to the range 0.0 to 1.0
        level = (value - LIGHT_MIN) / (LIGHT_MAX - LIGHT_MIN)

        if level < 0:
            level = 0
        elif level > 1:
            level = 1

        # 3. Control LED brightness using PWM duty cycle
        duty = int(level * 65535)
        led.duty_u16(duty)

        # 4. Control piezo pitch using PWM frequency
        frequency = int(MIN_FREQ + level * (MAX_FREQ - MIN_FREQ))
        piezo.freq(frequency)

        if level > 0:
            piezo.duty_u16(32768)  # Approximately 50% duty cycle
        else:
            piezo.duty_u16(0)      # Silence at the minimum level

        # Display the input and output settings
        print("Light:", value, "LED duty:", duty,
              "Piezo frequency:", frequency)

        # Poll approximately 20 times per second
        time.sleep_ms(50)

except KeyboardInterrupt:
    print("Stopped")

finally:
    # Disable both outputs when the program exits
    led.duty_u16(0)
    piezo.duty_u16(0)
    led.deinit()
    piezo.deinit()
    Pin(LED_PIN, Pin.OUT).value(0)
    Pin(PIEZO_PIN, Pin.OUT).value(0)