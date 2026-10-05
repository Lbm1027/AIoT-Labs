#import lab3_check1
#import lab3_check2
#import lab3_check3
#import lab3_check4

# Lisen to the serial port for debugging
# python -m serial.tools.miniterm COM3 115200 --xonxoff

# Upload the code to the ESP32 using mpfshell
# mpfshell -nc "open COM3; put main.py; put lab3_check1.py"
# mpfshell -nc "open COM3; put main.py; put lab3_check2.py"
# mpfshell -nc "open COM3; put main.py; put lab3_check3.py"
# mpfshell -nc "open COM3; put main.py; put lab3_check4.py"