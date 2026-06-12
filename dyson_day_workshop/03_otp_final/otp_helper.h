#ifndef OTP_HELPER_H
#define OTP_HELPER_H

#include <Arduino.h>
#include <SHA1.h>
#include <string.h>

constexpr uint32_t OTP_STEP_SECONDS = 10UL;

namespace {
constexpr uint8_t SECRET_LENGTH = 20;

const uint8_t CLASSROOM_SECRET[SECRET_LENGTH] = {
    'H', 'I', 'G', 'H', 'S', 'C', 'H', 'O', 'O', 'L',
    'O', 'T', 'P', 'D', 'E', 'M', 'O', '2', '0', '2'};

SHA1 sha1;
uint8_t innerKeyPad[64];
uint8_t outerKeyPad[64];
bool otpPadsReady = false;
}

void otpBegin() {
  memset(innerKeyPad, 0x36, sizeof(innerKeyPad));
  memset(outerKeyPad, 0x5C, sizeof(outerKeyPad));

  for (uint8_t index = 0; index < SECRET_LENGTH; ++index) {
    innerKeyPad[index] ^= CLASSROOM_SECRET[index];
    outerKeyPad[index] ^= CLASSROOM_SECRET[index];
  }

  otpPadsReady = true;
}

uint32_t generateOtpCode(uint32_t secondsSinceBoot) {
  if (!otpPadsReady) {
    otpBegin();
  }

  uint64_t counter = secondsSinceBoot / OTP_STEP_SECONDS;
  uint8_t counterBytes[8];

  for (uint8_t index = 8; index > 0; --index) {
    counterBytes[index - 1] = counter & 0xFF;
    counter >>= 8;
  }

  uint8_t innerHash[20];
  sha1.reset();
  sha1.update(innerKeyPad, sizeof(innerKeyPad));
  sha1.update(counterBytes, sizeof(counterBytes));
  sha1.finalize(innerHash, sizeof(innerHash));

  uint8_t finalHash[20];
  sha1.reset();
  sha1.update(outerKeyPad, sizeof(outerKeyPad));
  sha1.update(innerHash, sizeof(innerHash));
  sha1.finalize(finalHash, sizeof(finalHash));

  uint8_t offset = finalHash[19] & 0x0F;
  uint32_t binaryCode =
      ((uint32_t)(finalHash[offset] & 0x7F) << 24) |
      ((uint32_t)(finalHash[offset + 1] & 0xFF) << 16) |
      ((uint32_t)(finalHash[offset + 2] & 0xFF) << 8) |
      ((uint32_t)(finalHash[offset + 3] & 0xFF));

  return binaryCode % 1000000UL;
}

void formatOtp(uint32_t code, char output[7]) {
  code %= 1000000UL;
  for (int8_t index = 5; index >= 0; --index) {
    output[index] = '0' + (code % 10);
    code /= 10;
  }
  output[6] = '\0';
}

#endif
