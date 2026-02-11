#include <Arduino.h>
#include <Crypto.h>
#include <SHA1.h>
#include <string.h>

// --- TOTP CONFIG ---
const uint8_t secretKey[] = "12345678901234567890";
const uint32_t timestep = 30;

// --- GLOBALS ---
SHA1 hash;
uint8_t i_key_pad[64];
uint8_t o_key_pad[64];

// --- HMAC PREPARATION ---
void prepareHMACPads() {
  memset(i_key_pad, 0x36, 64);
  memset(o_key_pad, 0x5C, 64);

  for (int i = 0; i < sizeof(secretKey) - 1; i++) {
    i_key_pad[i] ^= secretKey[i];
    o_key_pad[i] ^= secretKey[i];
  }
}

void setup() {
  Serial.begin(9600);
  while (!Serial) {
    ; // Wait for serial port to connect (for Leonardo/Micro)
  }
  delay(1000);
  
  Serial.println("=== TOTP Debug Test ===");
  Serial.println();
  
  // Print secret key
  Serial.print("Secret key (hex): ");
  for (int i = 0; i < sizeof(secretKey) - 1; i++) {
    if (secretKey[i] < 16) Serial.print("0");
    Serial.print(secretKey[i], HEX);
  }
  Serial.println();
  
  // Test with time = 0
  uint32_t time = 0;
  uint64_t counter = time / timestep;
  
  Serial.print("Counter: ");
  Serial.println((uint32_t)counter);
  
  // Counter bytes
  uint8_t counterBytes[8];
  uint64_t tempCounter = counter;
  for (int i = 7; i >= 0; --i) {
    counterBytes[i] = tempCounter & 0xFF;
    tempCounter >>= 8;
  }
  
  Serial.print("Counter bytes (hex): ");
  for (int i = 0; i < 8; i++) {
    if (counterBytes[i] < 16) Serial.print("0");
    Serial.print(counterBytes[i], HEX);
  }
  Serial.println();
  
  // Prepare HMAC pads
  prepareHMACPads();
  
  // Print i_key_pad (first 20 bytes for verification)
  Serial.print("i_key_pad (first 20 bytes): ");
  for (int i = 0; i < 20; i++) {
    if (i_key_pad[i] < 16) Serial.print("0");
    Serial.print(i_key_pad[i], HEX);
  }
  Serial.println();
  
  // Compute inner hash
  uint8_t tempHash[20];
  hash.reset();
  hash.update(i_key_pad, 64);
  hash.update(counterBytes, 8);
  hash.finalize(tempHash, sizeof(tempHash));
  
  Serial.print("Inner hash (hex): ");
  for (int i = 0; i < 20; i++) {
    if (tempHash[i] < 16) Serial.print("0");
    Serial.print(tempHash[i], HEX);
  }
  Serial.println();
  
  // Compute outer hash (final HMAC)
  uint8_t finalHash[20];
  hash.reset();
  hash.update(o_key_pad, 64);
  hash.update(tempHash, sizeof(tempHash));
  hash.finalize(finalHash, sizeof(finalHash));
  
  Serial.print("HMAC-SHA1 output (hex): ");
  for (int i = 0; i < 20; i++) {
    if (finalHash[i] < 16) Serial.print("0");
    Serial.print(finalHash[i], HEX);
  }
  Serial.println();
  
  // Dynamic truncation
  int offset = finalHash[19] & 0x0F;
  Serial.print("Offset: ");
  Serial.println(offset);
  
  Serial.print("Bytes at offset [");
  Serial.print(offset);
  Serial.print("]: ");
  for (int i = 0; i < 4; i++) {
    if (finalHash[offset + i] < 16) Serial.print("0");
    Serial.print(finalHash[offset + i], HEX);
    Serial.print(" ");
  }
  Serial.println();
  
  uint32_t binary =
    ((uint32_t)(finalHash[offset] & 0x7F) << 24) |
    ((uint32_t)(finalHash[offset + 1] & 0xFF) << 16) |
    ((uint32_t)(finalHash[offset + 2] & 0xFF) << 8) |
    ((uint32_t)(finalHash[offset + 3] & 0xFF));
  
  Serial.print("Binary (truncated): ");
  Serial.println(binary);
  
  uint32_t code = binary % 1000000;
  Serial.print("Final TOTP code: ");
  Serial.println(code);
  
  Serial.println();
  Serial.println("=== Test Complete ===");
}

void loop() {
  // Nothing to do
}