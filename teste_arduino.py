import serial
import time

PORTA = "COM3"  
BAUDRATE = 115200

ser = serial.Serial(PORTA, BAUDRATE, timeout=1)
time.sleep(2)

print("Escutando comandos do WeMos...")

while True:
    if ser.in_waiting:
        comando = ser.readline().decode(errors="ignore").strip()
        if comando:
            print("Recebido:", comando)