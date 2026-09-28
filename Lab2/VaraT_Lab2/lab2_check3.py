from machine import Pin, PWM, ADC
import utime

last_press_time = 0
debounce_ms = 30
system_on = False
light_sensor = ADC(Pin(39))
light_sensor.atten(ADC.ATTN_11DB)
button = Pin(32, Pin.IN, Pin.PULL_UP)
led_pwm = PWM(Pin(13))
led_pwm.duty_u16(0)
piezo_pwm = PWM(Pin(27))
piezo_pwm.freq(440)
piezo_pwm.duty_u16(0)

def button_handler(pin):
    global last_press_time, system_on
    current_time = utime.ticks_ms()
    if current_time - last_press_time > debounce_ms:
            last_press_time = current_time
            if pin.value() == 0:
                system_on = True
            else:
                system_on = False
button.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=button_handler)

while True:
    if system_on:
        value = light_sensor.read()
        led_pwm.duty_u16(int(value * 16))
        if value < 50:
            piezo_pwm.duty_u16(0)
        else:
            piezo_pwm.freq(int(100 + (value)*(1900) / 4095))
            piezo_pwm.duty_u16(32768)
    else:
        led_pwm.duty_u16(0)
        piezo_pwm.duty_u16(0)
    utime.sleep(0.01)