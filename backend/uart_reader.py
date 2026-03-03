import serial
import csv
import datetime

COM_PORT    = '/dev/serial0'
BAUD_RATE   = 9600
CSV_FILE    = 'attiny_log.csv'

with serial.Serial(COM_PORT, BAUD_RATE, timeout=1) as ser, \
     open(CSV_FILE, mode='a', newline='', encoding='utf-8') as f:

    writer = csv.writer(f)
    writer.writerow(["UTC Timestamp", "TOTP Code", "Elapsed HH:MM:SS", "Elapsed (s)"])
    print(f"Logging to {CSV_FILE}. Ctrl+C to stop.")

    try:
        while True:
            line = ser.readline().decode('utf-8', errors='replace').strip()
            if not line:
                continue

            now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            if " | " in line:
                parts = line.split(" | ")
                if len(parts) == 3:
                    writer.writerow([now_utc, parts[0], parts[1], parts[2]])
                    f.flush()
            
            print(f"[{now_utc}] {line}")

    except KeyboardInterrupt:
        print("\nDone.")
