// #include <Arduino.h>

// // put function declarations here:
// int myFunction(int, int);

// void setup() {
//   // put your setup code here, to run once:
//   int result = myFunction(2, 3);
// }

// void loop() {
//   // put your main code here, to run repeatedly:
// }

// // put function definitions here:
// int myFunction(int x, int y) {
//   return x + y;
// }

#include <Crypto.h>
#include <SHA256.h>

const uint8_t secretKey[] = "12345678901234567890";

uint32_t generateTOTP(uint32_t time, uint32_t timestep = 10) {
  SHA256 hash;
  uint64_t counter = time / timestep;

  uint8_t counterBytes[8];
  for (int i = 7; i >= 0; --i) {
    counterBytes[i] = counter & 0xFF;
    counter >>= 8;
  }

  uint8_t i_key_pad[64], o_key_pad[64];
  uint8_t tempHash[32];
  memset(i_key_pad, 0x36, 64);
  memset(o_key_pad, 0x5C, 64);
  for (int i = 0; i < sizeof(secretKey) - 1; i++) {
    i_key_pad[i] ^= secretKey[i];
    o_key_pad[i] ^= secretKey[i];
  }

  hash.reset();
  hash.update(i_key_pad, 64);
  hash.update(counterBytes, 8);
  hash.finalize(tempHash, sizeof(tempHash));

  hash.reset();
  hash.update(o_key_pad, 64);
  hash.update(tempHash, sizeof(tempHash));
  uint8_t finalHash[32];
  hash.finalize(finalHash, sizeof(finalHash));

  int offset = finalHash[31] & 0x0F;
  uint32_t binary =
      ((finalHash[offset] & 0x7F) << 24) |
      ((finalHash[offset + 1] & 0xFF) << 16) |
      ((finalHash[offset + 2] & 0xFF) << 8) |
      (finalHash[offset + 3] & 0xFF);

  return binary % 1000000; // 6 digits
}

void setup() {
  Serial.begin(9600);
}

void loop() {
  static uint32_t lastWindow = 0;
  uint32_t now = millis() / 1000;  // seconds since power-up
  uint32_t window = now / 10;      // 30-sec TOTP step

  if (window != lastWindow) {      // only when the 30s window changes
    lastWindow = window;
    uint32_t code = generateTOTP(now);
    Serial.print("TOTP: ");
    Serial.println(code);
  }
}
