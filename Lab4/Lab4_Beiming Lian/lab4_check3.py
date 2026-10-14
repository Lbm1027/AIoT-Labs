from machine import Pin, I2C
import network
import socket
import ssl
import json
import time
import ssd1306

# Fill in the WiFi network credentials.
WIFI_SSID = "Columbia University"
WIFI_PASSWORD = ""

# Fill in the OpenWeatherMap API key.
OPENWEATHER_API_KEY = "0c7fefae1a438058096a1d1047a4ea09"

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
WEATHER_HOST = "api.openweathermap.org"
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
        show(display, "LAB4 CHECK3", "Connecting WiFi", "Please wait...")
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
        self.code = code
        self.retry_seconds = retry_seconds


def get_json(host, path, https=False):
    # HTTP/1.0 requests connection-close framing; chunked replies also supported.
    port = 443 if https else 80
    address = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
    raw_socket = socket.socket()
    connection = raw_socket
    try:
        raw_socket.settimeout(HTTP_TIMEOUT_S)
        raw_socket.connect(address)
        if https:
            # MicroPython's convenience wrapper uses no CA validation by default.
            # It avoids requiring a separate CA file and RTC synchronization here.
            connection = ssl.wrap_socket(raw_socket, server_hostname=host)
        request = ("GET %s HTTP/1.0\r\nHost: %s\r\n"
                   "Accept: application/json\r\nConnection: close\r\n\r\n"
                   % (path, host)).encode()
        # SSL sockets expose stream read/write in MicroPython.
        sent = 0
        while sent < len(request):
            count = connection.write(request[sent:])
            if not count:
                raise OSError("HTTP connection closed while sending")
            sent += count
        response = bytearray()
        while True:
            chunk = connection.read(512)
            if not chunk:
                break
            response.extend(chunk)
            if len(response) > MAX_RESPONSE_BYTES:
                raise ValueError("Unexpectedly large HTTP response")
    finally:
        try:
            connection.close()
        finally:
            if connection is not raw_socket:
                raw_socket.close()

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
    body = bytes(response[separator + 4:])
    encoding = headers.get("transfer-encoding", "").lower()
    if encoding == "chunked":
        body = decode_chunks(body)
    elif encoding:
        raise ValueError("Unsupported HTTP transfer encoding")
    elif "content-length" in headers and len(body) != int(headers["content-length"]):
        raise ValueError("Incomplete HTTP body")
    if headers.get("content-encoding", "identity").lower() != "identity":
        raise ValueError("Unsupported HTTP content encoding")
    return json.loads(body.decode())


def decode_chunks(body):
    decoded = bytearray()
    position = 0
    while True:
        end = body.find(b"\r\n", position)
        if end < 0:
            raise ValueError("Incomplete chunk size")
        size = int(body[position:end].split(b";", 1)[0], 16)
        if size < 0:
            raise ValueError("Invalid chunk size")
        position = end + 2
        if size == 0:
            if body[position:position + 2] != b"\r\n" and b"\r\n\r\n" not in body[position:]:
                raise ValueError("Incomplete HTTP trailer")
            return bytes(decoded)
        end = position + size
        if body[end:end + 2] != b"\r\n":
            raise ValueError("Incomplete HTTP chunk")
        decoded.extend(body[position:end])
        position = end + 2


def fetch_location():
    data = get_json(API_HOST, API_PATH)
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


def fetch_weather(latitude, longitude):
    # The metric option makes main.temp Celsius; English fits the OLED font.
    path = ("/data/2.5/weather?lat=%.6f&lon=%.6f&appid=%s&units=metric&lang=en"
            % (latitude, longitude, OPENWEATHER_API_KEY.strip()))
    data = get_json(WEATHER_HOST, path, https=True)
    if not isinstance(data, dict) or str(data.get("cod")) != "200":
        raise ValueError("Weather API did not return a successful result")
    details = data.get("main")
    conditions = data.get("weather")
    if not isinstance(details, dict) or not isinstance(conditions, list) or not conditions:
        raise ValueError("Weather response is missing temperature or description")
    temperature = details.get("temp")
    if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not -273.15 <= temperature <= 100):
        raise ValueError("Weather response has an invalid temperature")
    descriptions = []
    for condition in conditions:
        description = condition.get("description") if isinstance(condition, dict) else None
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Weather response has an invalid description")
        descriptions.append(description.strip())
    return temperature, "; ".join(descriptions)


def wrap_description(description):
    # Wrap by words; retain every character even for unusually long words.
    lines = []
    line = ""
    for word in description.split():
        if line and len(line) + 1 + len(word) <= 16:
            line += " " + word
            continue
        if line:
            lines.append(line)
            line = ""
        while len(word) > 16:
            lines.append(word[:16])
            word = word[16:]
        line = word
    if line:
        lines.append(line)
    return lines or ["No description"]


def display_weather(display, temperature, description):
    lines = wrap_description(description)
    page_count = (len(lines) + 1) // 2
    page = 0
    while True:
        title = "CURRENT WEATHER" if page_count == 1 else "WEATHER %d/%d" % (page + 1, page_count)
        show(display, title, "Temp: %.1f ℃" % temperature,
             lines[page * 2], lines[page * 2 + 1] if page * 2 + 1 < len(lines) else "")
        if page_count == 1:
            return  # The screen retains this result after main returns.
        time.sleep_ms(3000)
        page = (page + 1) % page_count


def main():
    i2c = I2C(0, sda=Pin(SDA_PIN), scl=Pin(SCL_PIN), freq=400000)
    if OLED_ADDR not in i2c.scan():
        raise OSError("OLED 0x3C not found; check existing SDA/SCL wiring")
    display = ssd1306.SSD1306_I2C(128, 32, i2c, addr=OLED_ADDR)
    display.contrast(180)
    print("LAB4 CHECK3 - Location and current weather")
    if not WIFI_SSID or WIFI_SSID == "YOUR_WIFI_NAME" or WIFI_PASSWORD == "YOUR_WIFI_PASSWORD":
        show(display, "Set WiFi first", "Edit SSID/key", "lab4_check3.py", "Then press Reset")
        print("Fill WIFI_SSID and WIFI_PASSWORD, upload, then Reset.")
        return
    key = OPENWEATHER_API_KEY.strip()
    if not key or key == "YOUR_OPENWEATHER_API_KEY":
        show(display, "Set weather key", "OpenWeatherMap", "lab4_check3.py", "Then press Reset")
        print("Fill OPENWEATHER_API_KEY with your Current Weather API key.")
        return
    if not all(c in "0123456789abcdefABCDEF" for c in key):
        show(display, "Check API key", "Paste key only", "No URL or spaces", "Then press Reset")
        print("API key should contain hexadecimal characters only; paste the key, not the URL.")
        return

    location = None
    stage = "WiFi"
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                stage = "WiFi"
                connect_wifi(display)
                if location is None:
                    stage = "Location API"
                    show(display, "WiFi connected", "Getting location")
                    location = fetch_location()
                    print("Latitude:", location["lat"], "Longitude:", location["lon"])
                    print("City:", location.get("city", ""))
                stage = "Weather API"
                show(display, "Location found", "Getting weather", "Attempt %d/%d" % (attempt, MAX_ATTEMPTS))
                temperature, description = fetch_weather(location["lat"], location["lon"])
                print("Temperature: %.1f ℃" % temperature)
                print("Weather:", description)
                print("Weather at the IP-based location. Press Reset to update.")
                display_weather(display, temperature, description)
                return
            except (OSError, ValueError, HTTPError) as error:
                # Never print the request path or credentials.
                print("%s attempt %d failed:" % (stage, attempt), error)
                if isinstance(error, HTTPError) and stage == "Weather API" and error.code in (401, 403):
                    show(display, "Weather HTTP %d" % error.code, "Check API key", "Activation/plan", "Then press Reset")
                    print("Check API key, activation and Current Weather access in your account.")
                    return
                if attempt == MAX_ATTEMPTS:
                    show(display, "Weather failed", stage, "See serial log", "Reset to retry")
                    return
                delay = max(RETRY_SECONDS, getattr(error, "retry_seconds", 0))
                for remaining in range(delay, 0, -1):
                    show(display, stage + " failed", "See serial log", "Retry in %ds" % remaining)
                    time.sleep_ms(1000)
    except KeyboardInterrupt:
        print("Stopped")
        show(display, "Stopped", "Reset to start")


# Upload main.py containing just: import lab4_check3
main()
