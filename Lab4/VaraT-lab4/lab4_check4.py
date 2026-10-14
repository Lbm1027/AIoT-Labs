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
NTFY_TOPIC = "hjk2169_bl3230_vjt2110_lab4"
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

def send_notification(message):
    r = requests.post("https://ntfy.sh/" + NTFY_TOPIC,
                      data=message.encode(),
                      headers={"Title": "ESP32 Weather"})
    print("ntfy status:", r.status_code)
    r.close()

try:
    connect_wifi()
    show("Locating...")
    lat, lon, city = get_location()
    show("Getting weather")
    temp, desc = get_weather(lat, lon)
    message = "%s (%.2f, %.2f): %.1f C, %s" % (city, lat, lon, temp, desc)
    print(message)
    show(city, "%.1f C" % temp, desc)
    send_notification(message)
    show("Sent to ntfy:", NTFY_TOPIC[:16])
except Exception as e:
    print("error:", e)
    show("Error:", str(e))
    raise
