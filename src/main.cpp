#include <Arduino.h>
#include <Crypto.h>
#include <SHA1.h>
#include <LowPower.h>
#include <string.h>

// ---- CONFIG ----
const uint8_t secretKey[] = "12345678901234567890";
const uint32_t timestep = 30;  // 30-second TOTP window

// ---- GLOBALS ----
SHA1 hash;
uint8_t i_key_pad[64];
uint8_t o_key_pad[64];

void prepareHMACPads() {
  memset(i_key_pad, 0x36, 64);
  memset(o_key_pad, 0x5C, 64);

  for (int i = 0; i < sizeof(secretKey) - 1; i++) {
    i_key_pad[i] ^= secretKey[i];
    o_key_pad[i] ^= secretKey[i];
  }
}

uint32_t generateTOTP(uint32_t time) {
  uint64_t counter = time / timestep;

  uint8_t counterBytes[8];
  for (int i = 7; i >= 0; --i) {
    counterBytes[i] = counter & 0xFF;
    counter >>= 8;
  }

  uint8_t tempHash[20];
  hash.reset();
  hash.update(i_key_pad, 64);
  hash.update(counterBytes, 8);
  hash.finalize(tempHash, sizeof(tempHash));

  uint8_t finalHash[20];
  hash.reset();
  hash.update(o_key_pad, 64);
  hash.update(tempHash, sizeof(tempHash));
  hash.finalize(finalHash, sizeof(finalHash));

  int offset = finalHash[19] & 0x0F;
  uint32_t binary =
      ((finalHash[offset] & 0x7F) << 24) |
      ((finalHash[offset + 1] & 0xFF) << 16) |
      ((finalHash[offset + 2] & 0xFF) << 8) |
      (finalHash[offset + 3] & 0xFF);

  return binary % 1000000; // 6 digits
}

void setup() {
  Serial.begin(9600);
  delay(2000);  // allow Serial Monitor to connect
  Serial.println("TOTP Generator starting...");
  prepareHMACPads();  // precompute HMAC pads
}

void loop() {
  static uint32_t lastWindow = 0;
  uint32_t now = millis() / 1000;
  uint32_t window = now / timestep;

  if (window != lastWindow) {
    lastWindow = window;

    // Generate and print TOTP code
    uint32_t code = generateTOTP(now);
    Serial.print("TOTP: ");
    Serial.println(code);
    Serial.flush(); // ensure all bytes sent

    // ---- Sleep AFTER printing ----
    LowPower.powerDown(SLEEP_8S, ADC_OFF, BOD_OFF);  // sleep 8s
  }
  // loop will keep checking until the next TOTP window
}
