import network
import time
from machine import Pin, I2C, RTC
import ssd1306
import urequests
import ujson

WIFI_SSID = "Columbia University"
WIFI_PASS = ""

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
        print("Connecting to Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        while not wlan.isconnected():
            time.sleep(0.5)
    print("Connected! Network config:", wlan.ifconfig())

def main():
    connect_wifi()
    i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=I2C_FREQ)
    display = ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)

    display.fill(0)
    display.text("Fetching Geo...", 0, 0, 1)
    display.show()

    try:
        response = urequests.get("http://ip-api.com/json")
        data = response.json()
        response.close()
        
        lat = data.get("lat", 0.0)
        lon = data.get("lon", 0.0)
        
        display.fill(0)
        display.text("Lat: %.2f" % lat, 0, 0, 1)
        display.text("Lon: %.2f" % lon, 0, 12, 1)
        display.show()
    except Exception as e:
        display.fill(0)
        display.text("Geo Error", 0, 0, 1)
        display.show()
        print(e)

if __name__ == "__main__":
    main()