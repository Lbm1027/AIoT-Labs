'''
from machine import RTC
import time

#create real-time clock
rtc = RTC()

# Set the clock when the ESP32 boots
# Format:
# (year, month, day, weekday, hour, minute, second, microsecond)
rtc.datetime((2026, 9, 30, 2, 9, 0, 0, 0))

while True:
    #read the current date/time
    current_time = rtc.datetime()
    print(current_time)
    time.sleep(1)
    '''

from machine import RTC
import time

# 1. Initialize the RTC object
rtc = RTC()

# 2. Hardcode startup time: (year, month, day, weekday, hours, minutes, seconds, subseconds)
# Note: weekday is 0-6 (0 = Monday, 6 = Sunday)
START_TIME = (2026, 9, 30, 2, 9, 0, 0, 0) # September 30, 2026, 9:00:00 AM (Wednesday)

# Set the RTC date and time
rtc.datetime(START_TIME)
print("System time initialized to hardcoded value.")

# 3. Read and format the time continuously
while True:
    current_time = rtc.datetime()
    
    # Unpack tuple: (year, month, day, weekday, hours, minutes, seconds, subseconds)
    year, month, day, _, hours, minutes, seconds, _ = current_time
    
    # Format as YYYY-MM-DD HH:MM:SS
    formatted_time = f"{year:04d}-{month:02d}-{day:02d} {hours:02d}:{minutes:02d}:{seconds:02d}"
    
    print("Current Time:", formatted_time)
    
    time.sleep(1)