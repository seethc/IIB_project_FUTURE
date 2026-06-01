import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from totp_utils import generate_challenge_response, generate_totp, secret_hex_to_bytes


class TotpUtilsTest(unittest.TestCase):
    def test_generate_totp_uses_sha256_truncated_to_six_digits(self):
        secret = b"12345678901234567890"

        self.assertEqual(generate_totp(secret, 0, timestep=30), 875740)
        self.assertEqual(generate_totp(secret, 59, timestep=30), 247374)

    def test_generate_totp_supports_two_and_half_minute_step(self):
        secret = b"12345678901234567890"

        self.assertEqual(generate_totp(secret, 149, timestep=150), 875740)
        self.assertEqual(generate_totp(secret, 150, timestep=150), 247374)

    def test_secret_hex_to_bytes_prefers_new_hex_storage(self):
        self.assertEqual(
            secret_hex_to_bytes("3132333435363738393031323334353637383930"),
            b"12345678901234567890",
        )

    def test_secret_hex_to_bytes_accepts_legacy_plaintext(self):
        self.assertEqual(
            secret_hex_to_bytes("12345678901234567890"),
            b"12345678901234567890",
        )

    def test_generate_challenge_response(self):
        self.assertEqual(
            generate_challenge_response(
                "3132333435363738393031323334353637383930",
                "000102030405060708090a0b0c0d0e0f",
            ),
            "0cf1d1219065f5c2e12e4219c2c081d31d561402baa05bf5b9290baa2e83b00e",
        )


if __name__ == "__main__":
    unittest.main()
