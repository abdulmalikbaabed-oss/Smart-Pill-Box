import serial
import csv
import time
from datetime import datetime
import os

# ============== Settings ==============
# Update to your Pico's COM port (e.g., 'COM16')
COM_PORT = 'COM16' 
BAUD_RATE = 115200
FILE_NAME = 'medication_log.csv'

def initialize_file():
    if not os.path.exists(FILE_NAME):
        try:
            with open(FILE_NAME, mode='w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                writer.writerow(['Date', 'Box ID', 'Scheduled Time', 'Taken Time', 'Pills Before', 'Pills After', 'Pills Taken', 'Delay (Mins)'])
            print(f"[*] Created new log file: {FILE_NAME}")
        except PermissionError:
            print(f"[!] WARNING: Cannot create {FILE_NAME}. Please close Excel if it's open.")

initialize_file()
print(f"[*] Connecting to {COM_PORT}...")

try:
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
    print("[*] Connected Successfully! Waiting for Smart Box data...\n")

    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            
            if line.startswith("DATALOG,"):
                parts = line.split(',')
                if len(parts) == 8:
                    current_date = datetime.now().strftime("%Y-%m-%d")
                    box_id = parts[1]
                    sched_time = parts[2]
                    actual_time = parts[3]
                    pills_before = parts[4]
                    pills_after = parts[5]
                    pills_taken = parts[6]
                    delay = parts[7]

                    data_row = [current_date, box_id, sched_time, actual_time, pills_before, pills_after, pills_taken, delay]
                    
                    try:
                        with open(FILE_NAME, mode='a', newline='', encoding='utf-8-sig') as file:
                            writer = csv.writer(file)
                            writer.writerow(data_row)
                        
                        print(f"[SUCCESS] New Dose Logged:")
                        print(f"  > {box_id} | Sched: {sched_time} | Taken: {actual_time} | Qty: {pills_taken} | Delay: {delay} min\n")
                    except PermissionError:
                        print(f"[ERROR] Cannot write to Excel. The file '{FILE_NAME}' is open!")
                        print(f"  > Please close the Excel file immediately. Data is pending...")
                        # We don't crash, we just let the user know.

except serial.SerialException as e:
    print(f"[ERROR] Connection Failed. Make sure the Pico is plugged in and Thonny is disconnected.")
except KeyboardInterrupt:
    print("\n[*] Logging Stopped.")
    if 'ser' in locals() and ser.is_open:
        ser.close()