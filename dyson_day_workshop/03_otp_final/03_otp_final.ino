#include <Arduino.h>
#include <U8g2lib.h>

#include "otp_helper.h"

#define PIN_CLK PIN_PA4
#define PIN_MOSI PIN_PA5
#define PIN_CS PIN_PA3
#define PIN_DC PIN_PA6
#define PIN_RST PIN_PA7

const char STUDENT_NAME[] = "YOUR NAME";

U8G2_SSD1306_128X64_NONAME_1_4W_SW_SPI display(
    U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

uint32_t lastDisplayedSecond = 0xFFFFFFFFUL;

uint32_t secondsSincePowerOn() {
  return millis() / 1000UL;
}

void drawCentered(const char *text, int16_t y) {
  int16_t width = display.getStrWidth(text);
  display.drawStr((128 - width) / 2, y, text);
}

void drawOtpScreen(uint32_t secondsNow) {
  char codeText[7];
  uint32_t code = generateOtpCode(secondsNow);
  formatOtp(code, codeText);

  uint32_t secondsLeft = OTP_STEP_SECONDS - (secondsNow % OTP_STEP_SECONDS);
  if (secondsLeft == 0) {
    secondsLeft = OTP_STEP_SECONDS;
  }

  char countdownText[18];
  snprintf(countdownText, sizeof(countdownText), "refresh in %lus",
           (unsigned long)secondsLeft);

  display.firstPage();
  do {
    display.setFont(u8g2_font_6x10_tf);
    drawCentered(STUDENT_NAME, 9);

    display.setFont(u8g2_font_logisoso24_tn);
    drawCentered(codeText, 42);

    display.setFont(u8g2_font_6x10_tf);
    drawCentered(countdownText, 62);
  } while (display.nextPage());
}

void setup() {
  otpBegin();
  display.begin();
  drawOtpScreen(secondsSincePowerOn());
}

void loop() {
  uint32_t secondsNow = secondsSincePowerOn();

  if (secondsNow != lastDisplayedSecond) {
    lastDisplayedSecond = secondsNow;
    drawOtpScreen(secondsNow);
  }
}
