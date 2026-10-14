import network
import time
from machine import Pin, I2C
import ssd1306
import urequests
import ujson

WIFI_SSID = "Columbia University"
WIFI_PASS = ""
OPENWEATHER_API_KEY = ""

SDA_PIN = 22
SCL_PIN = 20
OLED_WIDTH = 128
OLED_HEIGHT = 32
OLED_ADDR = 0x3C
I2C_FREQ = 400000

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(0.5)

def main():
    connect_wifi()
    i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)
    display = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)

    try:
        # Get location first
        geo_res = urequests.get("http://ip-api.com/json")
        geo_data = geo_res.json()
        geo_res.close()
        lat, lon = geo_data.get("lat", 0.0), geo_data.get("lon", 0.0)

        # Query OpenWeatherMap
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_API_KEY}"
        w_res = urequests.get(weather_url)
        w_data = w_res.json()
        w_res.close()

        temp = w_data["main"]["temp"]
        desc = w_data["weather"][0]["description"]

        display.fill(0)
        display.text("Temp: %.1fC" % temp, 0, 0, 1)
        display.text(desc[:16], 0, 16, 1)
        display.show()
    except Exception as e:
        display.fill(0)
        display.text("Weather Error", 0, 0, 1)
        display.show()
        print(e)

if __name__ == "__main__":
    main()