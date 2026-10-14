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
OWM_API_KEY = ""

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
    return wlan

def get_location():
    r = requests.get("http://ip-api.com/json")
    data = r.json()
    r.close()
    return data["lat"], data["lon"], data.get("city", "")

def get_weather(lat, lon):
    url = ("http://api.openweathermap.org/data/2.5/weather?lat=%s&lon=%s"
           "&units=metric&appid=%s" % (lat, lon, OWM_API_KEY))
    r = requests.get(url)
    data = r.json()
    r.close()
    print("weather:", data)
    return data["main"]["temp"], data["weather"][0]["description"]

try:
    connect_wifi()
    lat, lon, city = get_location()
    show("Weather for", city)
    temp, desc = get_weather(lat, lon)
    show(city, "%.1f C" % temp, desc)
except Exception as e:
    print("error:", e)
    show("Error:", str(e))
    raise
