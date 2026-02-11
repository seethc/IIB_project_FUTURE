import hmac
import hashlib
import struct

# --- CONFIG ---
SECRET_KEY = b"12345678901234567890"
TIMESTEP = 30

def test_hmac():
    """Test HMAC-SHA1 output for debugging"""
    secret = b"12345678901234567890"
    counter = 0  # Test with time=0
    counter_bytes = struct.pack(">Q", counter)
    
    print("=== TOTP Debug Test ===")
    print(f"Secret key (hex): {secret.hex()}")
    print(f"Counter: {counter}")
    print(f"Counter bytes (hex): {counter_bytes.hex()}")
    
    hmac_hash = hmac.new(secret, counter_bytes, hashlib.sha1).digest()
    print(f"HMAC-SHA1 output (hex): {hmac_hash.hex()}")
    
    offset = hmac_hash[-1] & 0x0F
    print(f"Offset: {offset}")
    
    binary = ((hmac_hash[offset] & 0x7f) << 24 |
              (hmac_hash[offset + 1] & 0xff) << 16 |
              (hmac_hash[offset + 2] & 0xff) << 8 |
              (hmac_hash[offset + 3] & 0xff))
    print(f"Binary (truncated): {binary}")
    
    code = binary % 1000000
    print(f"Final TOTP code: {code:06d}")

if __name__ == "__main__":
    test_hmac()