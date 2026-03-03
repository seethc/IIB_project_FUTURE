import serial
import csv
import datetime

# --- CONFIGURATION ---
COM_PORT = 'COM3'
BAUD_RATE = 9600
CSV_FILENAME = 'attiny_log.csv'

try:
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
    print(f"Connected to {COM_PORT} at {BAUD_RATE} baud.")

    with open(CSV_FILENAME, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(["UTC Timestamp", "TOTP Code", "RTC Time (HHMMSS)", "Elapsed (s)"])
        print(f"Logging to {CSV_FILENAME}. Press Ctrl+C to stop.\n")

        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='replace').strip()

                if line and " | " in line:
                    parts = line.split(" | ")

                    if len(parts) == 3:
                        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        writer.writerow([now_utc, parts[0], parts[1], parts[2]])
                        file.flush()
                        print(f"[{now_utc}] {parts[0]} | {parts[1]} | {parts[2]}")

                elif line:
                    # Catch non-data lines like "Ready" or "RTC ERR"
                    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    print(f"[{now_utc}] {line}")

except serial.SerialException as e:
    print(f"\nError: Could not open {COM_PORT}. ({e})")
except KeyboardInterrupt:
    print("\nLogging stopped by user.")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()