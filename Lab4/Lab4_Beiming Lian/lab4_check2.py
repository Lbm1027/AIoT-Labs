from machine import Pin, I2C
import network
import socket
import json
import time
import ssd1306

# Fill in the WiFi network credentials.
WIFI_SSID = "Columbia University"
WIFI_PASSWORD = ""

# Same OLED wiring as your working Lab3 program.
SDA_PIN = 22
SCL_PIN = 20
OLED_ADDR = 0x3C
WIFI_TIMEOUT_MS = 30000
HTTP_TIMEOUT_S = 10
MAX_RESPONSE_BYTES = 8192
MAX_ATTEMPTS = 3
RETRY_SECONDS = 60
API_HOST = "ip-api.com"
API_PATH = "/json/?fields=status,message,lat,lon,city,country,query"


def show(display, *lines):
    display.fill(0)
    for row, line in enumerate(lines[:4]):
        # The built-in font is 8 pixels wide: at most 16 characters per row.
        readable = "".join(c if 32 <= ord(c) < 127 else "?" for c in str(line))
        display.text(readable[:16], 0, row * 8, 1)
    display.show()


def connect_wifi(display):
    wlan = network.WLAN()  # Station interface on MicroPython 1.26.
    wlan.active(True)
    if not wlan.isconnected():
        show(display, "LAB4 CHECK2", "Connecting WiFi", "Please wait...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        started = time.ticks_ms()
        while not wlan.isconnected():
            status = wlan.status()
            if status < 0:
                wlan.disconnect()
                raise OSError("WiFi connection failed; status=%d" % status)
            if time.ticks_diff(time.ticks_ms(), started) >= WIFI_TIMEOUT_MS:
                wlan.disconnect()
                raise OSError("WiFi timeout: check SSID, password and network access")
            time.sleep_ms(200)
    print("WiFi connected; local IP:", wlan.ipconfig("addr4")[0])
    return wlan


class HTTPError(Exception):
    def __init__(self, code, retry_seconds):
        super().__init__("HTTP %d" % code)
        self.retry_seconds = retry_seconds


def fetch_location():
    # HTTP/1.0 + Connection: close requests an unchunked, close-delimited reply.
    # The lab's free ip-api endpoint uses HTTP and does not require an API key.
    address = socket.getaddrinfo(API_HOST, 80, 0, socket.SOCK_STREAM)[0][-1]
    connection = socket.socket()
    try:
        connection.settimeout(HTTP_TIMEOUT_S)
        connection.connect(address)
        request = ("GET %s HTTP/1.0\r\nHost: %s\r\n"
                   "Accept: application/json\r\nConnection: close\r\n\r\n"
                   % (API_PATH, API_HOST)).encode()
        sent = 0
        while sent < len(request):
            count = connection.send(request[sent:])
            if not count:
                raise OSError("HTTP connection closed while sending")
            sent += count
        response = bytearray()
        while True:
            chunk = connection.recv(512)
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > MAX_RESPONSE_BYTES:
                raise ValueError("Unexpectedly large HTTP response")
    finally:
        connection.close()

    separator = response.find(b"\r\n\r\n")
    if separator < 0:
        raise ValueError("Incomplete HTTP response; check Internet access")
    header_lines = bytes(response[:separator]).decode().split("\r\n")
    status = header_lines[0].split()
    if len(status) < 2 or not status[0].startswith("HTTP/"):
        raise ValueError("Invalid HTTP status line")
    code = int(status[1])
    headers = {}
    for line in header_lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.lower()] = value.strip()
    if code != 200:
        delay = RETRY_SECONDS
        for name in ("x-ttl", "retry-after"):
            try:
                delay = max(delay, int(headers.get(name, "0")))
            except ValueError:
                pass
        raise HTTPError(code, delay)
    if "transfer-encoding" in headers:
        raise ValueError("Unexpected HTTP encoding; check network proxy")
    body = bytes(response[separator + 4:])
    if "content-length" in headers and len(body) != int(headers["content-length"]):
        raise ValueError("Incomplete HTTP body")
    data = json.loads(body.decode())
    if not isinstance(data, dict) or data.get("status") != "success":
        message = data.get("message", "Unknown API error") if isinstance(data, dict) else "Invalid JSON result"
        raise ValueError("Location API failed: " + str(message))
    latitude, longitude = data.get("lat"), data.get("lon")
    if (isinstance(latitude, bool) or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float))
            or not isinstance(longitude, (int, float))
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        raise ValueError("Location API returned invalid coordinates")
    return data


def main():
    i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=400000)
    if OLED_ADDR not in i2c.scan():
        raise OSError("OLED 0x3C not found; check existing SDA/SCL wiring")
    display = ssd1306.SSD1306_I2C(128, 32, i2c, addr=OLED_ADDR)
    display.contrast(180)
    print("LAB4 CHECK2 - WiFi and IP geolocation")
    if not WIFI_SSID or WIFI_SSID == "YOUR_WIFI_NAME" or WIFI_PASSWORD == "YOUR_WIFI_PASSWORD":
        show(display, "Set WiFi first", "Edit SSID/key", "lab4_check2.py", "Then press Reset")
        print("Fill WIFI_SSID and WIFI_PASSWORD in lab4_check2.py, upload, then Reset.")
        return

    stage = "WiFi"
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                stage = "WiFi"
                connect_wifi(display)
                stage = "Location API"
                show(display, "WiFi connected", "Getting location", "Attempt %d/%d" % (attempt, MAX_ATTEMPTS))
                location = fetch_location()
                show(display, "IP LOCATION",
                     "Lat: %.4f" % location["lat"],
                     "Lon: %.4f" % location["lon"],
                     location.get("city") or "Location found")
                print("Latitude:", location["lat"])
                print("Longitude:", location["lon"])
                print("City:", location.get("city", ""), "Country:", location.get("country", ""))
                print("Public IP:", location.get("query", ""))
                print("Approximate IP location. Press Reset to request again.")
                return  # OLED retains the result; avoid repeated API requests.
            except (OSError, ValueError, HTTPError) as error:
                print("%s attempt %d failed:" % (stage, attempt), error)
                if attempt == MAX_ATTEMPTS:
                    show(display, "Location failed", stage, "See serial log", "Reset to retry")
                    return
                delay = max(RETRY_SECONDS, getattr(error, "retry_seconds", 0))
                for remaining in range(delay, 0, -1):
                    show(display, stage + " failed", "See serial log", "Retry in %ds" % remaining)
                    time.sleep_ms(1000)
    except KeyboardInterrupt:
        print("Stopped")
        show(display, "Stopped", "Reset to start")


# main.py starts this program with one import after Reset.
main()