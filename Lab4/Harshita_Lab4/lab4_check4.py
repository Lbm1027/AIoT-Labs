import network
import time
from machine import Pin, I2C
import ssd1306
import urequests

WIFI_SSID = "Columbia University"
WIFI_PASS = ""
NTFY_TOPIC = "hjk2169_lab4"  # Change to your unique channel name

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

    display.fill(0)
    display.text("Sending Notif...", 0, 0, 1)
    display.show()

    try:
        # Fetch location for message payload
        geo_res = urequests.get("http://ip-api.com/json")
        geo_data = geo_res.json()
        geo_res.close()
        lat, lon = geo_data.get("lat", 0.0), geo_data.get("lon", 0.0)

        message = f"Smartwatch Alert: Lat={lat}, Lon={lon} - Greetings from Lab 4!"
        
        # Publish via ntfy.sh API
        ntfy_url = f"https://ntfy.sh/{NTFY_TOPIC}"
        response = urequests.post(ntfy_url, data=message.encode("utf-8"))
        response.close()

        display.fill(0)
        display.text("Notif Sent!", 0, 0, 1)
        display.text("Check ntfy.sh", 0, 12, 1)
        display.show()
    except Exception as e:
        display.fill(0)
        display.text("Notif Error", 0, 0, 1)
        display.show()
        print(e)

if __name__ == "__main__":
    main()