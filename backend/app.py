import hmac
import hashlib
import time
import struct
import smbus
from datetime import datetime, timezone

# --- CONFIG ---
SECRET_KEY = b"12345678901234567890"  
TIMESTEP = 30 
DS3231_ADDR = 0x68
BUS_NUMBER = 1  # Raspberry Pi 4 uses I2C bus 1

# Initialize I2C Bus
bus = smbus.SMBus(BUS_NUMBER)

# --- HELPER FUNCTIONS ---
def bcd_to_int(bcd):
    """Convert Binary Coded Decimal to Integer"""
    return (bcd & 0x0F) + ((bcd >> 4) * 10)

def get_rtc_timestamp():
    """
    Reads the DS3231 registers and converts to a linear Unix timestamp.
    """
    try:
        # Read 7 bytes starting from register 0x00 (Seconds)
        # 00:Sec, 01:Min, 02:Hour, 03:Day, 04:Date, 05:Month, 06:Year
        regs = bus.read_i2c_block_data(DS3231_ADDR, 0x00, 7)
        
        sec = bcd_to_int(regs[0])
        min = bcd_to_int(regs[1])
        hour = bcd_to_int(regs[2] & 0x3F) 
        day = bcd_to_int(regs[4])
        month = bcd_to_int(regs[5] & 0x1F)
        year = bcd_to_int(regs[6]) + 2000
        
        # Convert to linear timestamp
        dt = datetime(year, month, day, hour, min, sec, tzinfo=timezone.utc)
        return int(dt.timestamp())
        
    except Exception as e:
        print(f"Error reading RTC: {e}")
        return 0

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
    
    # 1. Capture the "Zero Point" from the RTC
    # This ignores system time and locks "T=0" to the current RTC reading
    start_timestamp = get_rtc_timestamp()
    
    if start_timestamp == 0:
        print("Failed to read RTC. Check wiring.")
        return

    # Header
    print("-" * 55)
    print(f"{'RTC TIME':<15} | {'TOTP CODE':<10} | {'ELAPSED TIME (s)':<15}")
    print("-" * 55)

    last_processed_time = -1

    try:
        while True:
            # 2. Get current Raw RTC time
            current_timestamp = get_rtc_timestamp()
            
            # Only update display if the second has changed
            if current_timestamp != last_processed_time:
                
                # 3. Calculate Total Elapsed (Linear, non-resetting)
                elapsed_seconds = current_timestamp - start_timestamp
                
                # 4. Generate TOTP using the ELAPSED time
                totp_code = generate_totp(SECRET_KEY, elapsed_seconds)
                
                # 5. Display Formatting
                rtc_str = datetime.fromtimestamp(current_timestamp, timezone.utc).strftime('%H:%M:%S')
                
                # Print the row
                print(f"{rtc_str:<15} | {totp_code:06d}     | {elapsed_seconds:<15}")
                
                last_processed_time = current_timestamp
            
            # Poll fast enough to catch the second change instantly
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
