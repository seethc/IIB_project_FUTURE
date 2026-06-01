import hashlib
import hmac
import os
import struct
import time
from datetime import datetime, timezone

try:
    import smbus

    HAS_SMBUS = True
except ImportError:
    print("WARNING: smbus not found (likely not on Raspberry Pi). I2C will be mocked.")
    HAS_SMBUS = False


DEFAULT_TIMESTEP_SECONDS = int(os.environ.get("TOTP_TIMESTEP_SECONDS", "30"))
DS3231_ADDR = 0x68
BUS_NUMBER = 1


def _init_bus():
    if not HAS_SMBUS:
        return None

    try:
        return smbus.SMBus(BUS_NUMBER)
    except Exception as exc:
        print(f"I2C Bus failed: {exc}")
        return None


bus = _init_bus()


def bcd_to_int(bcd):
    return (bcd & 0x0F) + ((bcd >> 4) * 10)


def get_rtc_timestamp():
    """
    Reads the DS3231 registers and converts them to a Unix timestamp.
    Uses system time when the RTC is unavailable so the app can run on a laptop.
    """
    if bus is None:
        return int(time.time())

    try:
        regs = bus.read_i2c_block_data(DS3231_ADDR, 0x00, 7)

        sec = bcd_to_int(regs[0])
        minute = bcd_to_int(regs[1])
        hour = bcd_to_int(regs[2] & 0x3F)
        day = bcd_to_int(regs[4])
        month = bcd_to_int(regs[5] & 0x1F)
        year = bcd_to_int(regs[6]) + 2000

        dt = datetime(year, month, day, hour, minute, sec, tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception as exc:
        print(f"Error reading RTC: {exc}")
        return int(time.time())


def generate_totp(secret, elapsed_time, timestep=DEFAULT_TIMESTEP_SECONDS):
    if isinstance(secret, str):
        secret = secret.encode("utf-8")

    timestep = int(timestep)
    if timestep <= 0:
        raise ValueError("timestep must be positive")

    counter = int(elapsed_time) // timestep
    counter_bytes = struct.pack(">Q", counter)
    hmac_hash = hmac.new(secret, counter_bytes, hashlib.sha256).digest()

    offset = hmac_hash[-1] & 0x0F
    binary = (
        ((hmac_hash[offset] & 0x7F) << 24)
        | ((hmac_hash[offset + 1] & 0xFF) << 16)
        | ((hmac_hash[offset + 2] & 0xFF) << 8)
        | (hmac_hash[offset + 3] & 0xFF)
    )

    return binary % 1000000


def secret_hex_to_bytes(secret_hex):
    """
    New records store 20-byte secrets as 40 hex characters.
    Legacy records may still contain the old plain text 20-char secret.
    """
    if isinstance(secret_hex, bytes):
        return secret_hex

    value = str(secret_hex)
    if len(value) == 40:
        try:
            return bytes.fromhex(value)
        except ValueError:
            pass

    return value.encode("utf-8")


def generate_challenge_response(secret_hex, challenge_hex):
    return hmac.new(
        secret_hex_to_bytes(secret_hex),
        bytes.fromhex(challenge_hex),
        hashlib.sha256,
    ).hexdigest()
