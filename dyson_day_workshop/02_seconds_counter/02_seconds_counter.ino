#include <Arduino.h>
#include <U8x8lib.h>
#include <Wire.h>
#include <string.h>

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

void formatSeconds(uint32_t value, char output[11]) {
  char reversed[10];
  uint8_t count = 0;

  do {
    reversed[count] = '0' + (value % 10);
    value /= 10;
    count++;
  } while (value > 0 && count < sizeof(reversed));

  for (uint8_t index = 0; index < count; ++index) {
    output[index] = reversed[count - index - 1];
  }
  output[count] = '\0';
}

void drawCounterScreen(uint32_t secondsNow) {
  char secondsText[11];
  formatSeconds(secondsNow, secondsText);

  display.clearDisplay();
  drawCentered(0, STUDENT_NAME);
  drawCentered(2, "seconds since");
  drawCentered(3, "power on");
  drawCentered(5, secondsText);
}

void setup() {
  display.begin();
  display.setPowerSave(0);
  display.setFont(u8x8_font_chroma48medium8_r);
  drawCounterScreen(secondsSincePowerOn());
}

void loop() {
  uint32_t secondsNow = secondsSincePowerOn();

  if (secondsNow != lastDisplayedSecond) {
    lastDisplayedSecond = secondsNow;
    drawCounterScreen(secondsNow);
  }
}
