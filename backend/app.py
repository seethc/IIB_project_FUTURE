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
    except KeyboardInterrupt:
        print("Backend stopped")

if __name__ == "__main__":
    main()
