<<<<<<< HEAD
import pyotp
import time

# Demo patient secret (base32, should match the token)
# For production, generate and store securely per patient
DEMO_SECRET = "JBSWY3DPEHPK3PXP"

def generate_totp(secret):
    totp = pyotp.TOTP(secret, interval=30)  # 30 second interval
    return totp.now()

def main():
    print("Starting TOTP backend...")
    try:
        while True:
            code = generate_totp(DEMO_SECRET)
            print(f"Current backend TOTP code: {code}")
            time.sleep(1)  # update every second
=======
import hmac
import hashlib
import time
import struct

# --- CONFIG ---
SECRET_KEY = b"12345678901234567890"  
TIMESTEP = 30  # 30-second TOTP window

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
>>>>>>> 4241b06ff4c3e38b9a06b555dfb46760263afc80
    except KeyboardInterrupt:
        print("Backend stopped")

if __name__ == "__main__":
    main()
