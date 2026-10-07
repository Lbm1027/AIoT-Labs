from machine import Pin, I2C, ADC, RTC
import time
import ssd1306

# Hardware Setup
i2c = I2C(0, scl=Pin(22), sda=Pin(23))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

adc = ADC(Pin(39))
adc.atten(ADC.ATTN_11DB)  # Full range 0 - 3.3V

rtc = RTC()
rtc.datetime((2026, 10, 7, 3, 12, 0, 0, 0))

def main():
    while True:
        # Read light level (0 - 4095)
        light_val = adc.read()
        
        # Map ADC value (0-4095) to contrast (1-255)
        contrast = int((light_val / 4095.0) * 254) + 1
        contrast = max(1, min(255, contrast))
        
        oled.contrast(contrast)
        
        _, _, _, _, hour, minute, second, _ = rtc.datetime()
        
        oled.fill(0)
        oled.text("BRIGHTNESS ADJ", 10, 5)
        oled.text("----------------", 0, 18)
        oled.text("{:02d}:{:02d}:{:02d}".format(hour, minute, second), 32, 32)
        oled.text("Light ADC: {}".format(light_val), 10, 50)
        oled.show()
        
        time.sleep_ms(150)

if __name__ == "__main__":
    main()