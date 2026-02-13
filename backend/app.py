import hmac
import hashlib
import time
import struct

# --- CONFIG ---
SECRET_KEY = b"12345678901234567890"  
TIMESTEP = 1 # 30-second TOTP window

# --- GLOBAL CLOCK ---
start_time = time.time()  # reset clock for PoC

def get_uptime_seconds():
    """Simulate uptimeSeconds from token"""
    return int(time.time() - start_time)

# --- TOTP GENERATION ---
def generate_totp(secret, time_seconds):
    """
    Generate 6-digit TOTP using HMAC-SHA1 and raw byte secret
    """
    counter = time_seconds // TIMESTEP
    # Counter must be 8-byte big-endian
    counter_bytes = struct.pack(">Q", counter)
    
    # HMAC-SHA1
    hmac_hash = hmac.new(secret, counter_bytes, hashlib.sha1).digest()
    
    # Dynamic truncation
    offset = hmac_hash[-1] & 0x0F
    binary = ((hmac_hash[offset] & 0x7f) << 24 |
              (hmac_hash[offset + 1] & 0xff) << 16 |
              (hmac_hash[offset + 2] & 0xff) << 8 |
              (hmac_hash[offset + 3] & 0xff))
    
    code = binary % 1000000  # 6 digits
    return code

# --- DISPLAY SIMULATION ---
def display_code(code):
    """Print the 6-digit code"""
    print(f"TOTP code: {code:06d}")

# --- MAIN LOOP ---
def main():
    print("TOTP backend starting (clock reset to 0)...")
    try:
        while True:
            uptime = get_uptime_seconds()
            code = generate_totp(SECRET_KEY, uptime)
            display_code(code)
            time.sleep(1)
    except KeyboardInterrupt:
        print("Backend stopped")

if __name__ == "__main__":
    main()
