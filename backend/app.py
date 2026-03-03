import hmac
import hashlib
import time
import struct
import csv  
from datetime import datetime, timezone

try:
    import smbus
    HAS_SMBUS = True
except ImportError:
    print("WARNING: smbus not found (likely not on Raspberry Pi). I2C will be mocked.")
    HAS_SMBUS = False

# --- CONFIG ---
SECRET_KEY = b"12345678901234567890"  
TIMESTEP = 30 
DS3231_ADDR = 0x68
BUS_NUMBER = 1  # Raspberry Pi 4 uses I2C bus 1
CSV_FILENAME = "totp_log.csv" 

# Initialize I2C Bus
if HAS_SMBUS:
    try:
        bus = smbus.SMBus(BUS_NUMBER)
    except Exception as e:
        print(f"I2C Bus failed: {e}")
        bus = None
else:
    bus = None

# --- HELPER FUNCTIONS ---
def bcd_to_int(bcd):
    """Convert Binary Coded Decimal to Integer"""
    return (bcd & 0x0F) + ((bcd >> 4) * 10)

def get_rtc_timestamp():
    """
    Reads the DS3231 registers and converts to a linear Unix timestamp.
    If hardware is missing, uses system time as a mock.
    """
    if bus is None:
        return int(time.time())

    try:
        regs = bus.read_i2c_block_data(DS3231_ADDR, 0x00, 7)
        
        sec = bcd_to_int(regs[0])
        min = bcd_to_int(regs[1])
        hour = bcd_to_int(regs[2] & 0x3F) 
        day = bcd_to_int(regs[4])
        month = bcd_to_int(regs[5] & 0x1F)
        year = bcd_to_int(regs[6]) + 2000
        
        dt = datetime(year, month, day, hour, min, sec, tzinfo=timezone.utc)
        return int(dt.timestamp())
        
    except Exception as e:
        print(f"Error reading RTC: {e}")
        return int(time.time())

# --- TOTP GENERATION ---
def generate_totp(secret, elapsed_time):
    """Generate 6-digit TOTP based on ELAPSED time since start"""
    counter = elapsed_time // TIMESTEP
    counter_bytes = struct.pack(">Q", counter)
    
    hmac_hash = hmac.new(secret, counter_bytes, hashlib.sha1).digest()
    
    offset = hmac_hash[-1] & 0x0F
    binary = ((hmac_hash[offset] & 0x7f) << 24 |
              (hmac_hash[offset + 1] & 0xff) << 16 |
              (hmac_hash[offset + 2] & 0xff) << 8 |
              (hmac_hash[offset + 3] & 0xff))
    
    return binary % 1000000

# --- MAIN LOOP ---
def main():
    print("Initializing...")
    
    start_timestamp = get_rtc_timestamp()
    
    if start_timestamp == 0:
        print("Failed to read RTC. Check wiring.")
        return

    # Open the CSV file in append mode ('a')
    with open(CSV_FILENAME, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        # Write the header row to the CSV
        writer.writerow(["SYS UTC (INTERNET)", "RTC TIME", "TOTP CODE", "ELAPSED (s)"])
        
        # Console Header
        print("-" * 75)
        print(f"{'SYS UTC (INTERNET)':<20} | {'RTC TIME':<10} | {'TOTP CODE':<10} | {'ELAPSED (s)':<15}")
        print("-" * 75)
        print(f"Logging data to {CSV_FILENAME}... Press Ctrl+C to stop.")

        last_processed_time = -1

        try:
            while True:
                current_timestamp = get_rtc_timestamp()
                
                if current_timestamp != last_processed_time:
                    
                    elapsed_seconds = current_timestamp - start_timestamp
                    totp_code = generate_totp(SECRET_KEY, elapsed_seconds)
                    
                    rtc_str = datetime.fromtimestamp(current_timestamp, timezone.utc).strftime('%H:%M:%S')
                    system_utc_now = datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3]
                    
                    # 1. Print to the console
                    print(f"{system_utc_now:<20} | {rtc_str:<10} | {totp_code:06d}    | {elapsed_seconds:<15}")
                    
                    # 2. Write to the CSV file
                    writer.writerow([system_utc_now, rtc_str, f"{totp_code:06d}", elapsed_seconds])
                    
                    # 3. Flush the file buffer so data is saved immediately
                    file.flush()
                    
                    last_processed_time = current_timestamp
                
                time.sleep(0.05)

        except KeyboardInterrupt:
            print("\nStopped logging. File saved.")

if __name__ == "__main__":
    main()