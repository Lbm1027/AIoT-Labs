from machine import Pin, ADC, PWM
import utime

light_sensor = ADC(Pin(39))
light_sensor.atten(ADC.ATTN_11DB)

led_pwm = PWM(Pin(4))
led_pwm.freq(1000)
led_pwm.duty_u16(0)

piezo_pwm = PWM(Pin(14))
piezo_pwm.freq(440)
piezo_pwm.duty_u16(32768)

while True:
    value = light_sensor.read()
    led_pwm.duty_u16(int(value * 16))
    piezo_pwm.freq(int(100 + (value)*(1900) / 4095))
    print(value)
    utime.sleep(0.01)
