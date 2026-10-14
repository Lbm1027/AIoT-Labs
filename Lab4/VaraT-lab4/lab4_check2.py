from machine import I2C, Pin
import ssd1306
import network
import utime
try:
    import urequests as requests
except ImportError:
    import requests

WIFI_SSID = "Columbia University"
WIFI_PASSWORD = ""

i2c = I2C(0, sda=Pin(22), scl=Pin(20), freq=400000)
oled = ssd1306.SSD1306_I2C(128, 32, i2c)

def show(*lines):
    oled.fill(0)
    for i, line in enumerate(lines):
        oled.text(line[:16], 0, i * 10)
    oled.show()

def connect_wifi(timeout_s=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        start = utime.ticks_ms()
        while not wlan.isconnected():
            if utime.ticks_diff(utime.ticks_ms(), start) > timeout_s * 1000:
                raise OSError("Wi-Fi timeout")
            utime.sleep_ms(200)
    print("Wi-Fi:", wlan.ifconfig())
    return wlan

def get_location():
    r = requests.get("http://ip-api.com/json")
    data = r.json()
    r.close()
    print("geolocation:", data)
    return data["lat"], data["lon"], data.get("city", "")

try:
    connect_wifi()
    show("Wi-Fi OK", "Locating...")
    lat, lon, city = get_location()
    show("Lat %.4f" % lat, "Lon %.4f" % lon, city)
except Exception as e:
    print("error:", e)
    show("Error:", str(e))
    raise
