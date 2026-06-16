#include <Arduino.h>
#include <U8x8lib.h>
#include <Wire.h>
#include <string.h>

#include "otp_helper.h"

const char STUDENT_NAME[] = "YOUR NAME";

U8X8_SSD1306_128X64_NONAME_HW_I2C display(U8X8_PIN_NONE);

uint32_t lastDisplayedSecond = 0xFFFFFFFFUL;

uint32_t secondsSincePowerOn() {
  return millis() / 1000UL;
}

uint8_t centeredColumn(const char *text) {
  size_t length = strlen(text);
  if (length >= 16) {
    return 0;
  }
  return (16 - length) / 2;
}

void drawCentered(uint8_t row, const char *text) {
  display.drawString(centeredColumn(text), row, text);
}

void formatCountdown(uint32_t secondsLeft, char output[12]) {
  output[0] = 'n';
  output[1] = 'e';
  output[2] = 'x';
  output[3] = 't';
  output[4] = ' ';

  if (secondsLeft >= 10) {
    output[5] = '0' + (secondsLeft / 10);
    output[6] = '0' + (secondsLeft % 10);
    output[7] = 's';
    output[8] = '\0';
  } else {
    output[5] = '0' + secondsLeft;
    output[6] = 's';
    output[7] = '\0';
  }
}

void drawOtpScreen(uint32_t secondsNow) {
  char codeText[7];
  uint32_t code = generateOtpCode(secondsNow);
  formatOtp(code, codeText);

  uint32_t secondsLeft = OTP_STEP_SECONDS - (secondsNow % OTP_STEP_SECONDS);
  if (secondsLeft == 0) {
    secondsLeft = OTP_STEP_SECONDS;
  }

  char countdownText[12];
  formatCountdown(secondsLeft, countdownText);

  display.clearDisplay();
  drawCentered(0, STUDENT_NAME);
  drawCentered(2, "OTP CODE");
  drawCentered(3, codeText);
  drawCentered(5, countdownText);
}

void setup() {
  otpBegin();
  display.begin();
  display.setPowerSave(0);
  display.setFont(u8x8_font_chroma48medium8_r);
  drawOtpScreen(secondsSincePowerOn());
}

void loop() {
  uint32_t secondsNow = secondsSincePowerOn();

  if (secondsNow != lastDisplayedSecond) {
    lastDisplayedSecond = secondsNow;
    drawOtpScreen(secondsNow);
  }
}
