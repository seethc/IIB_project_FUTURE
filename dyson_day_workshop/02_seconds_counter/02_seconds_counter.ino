#include <Arduino.h>
#include <U8x8lib.h>
#include <string.h>

#if defined(MEGATINYCORE)
const uint8_t OLED_CLK = PIN_PA4;
const uint8_t OLED_MOSI = PIN_PA5;
const uint8_t OLED_CS = PIN_PA3;
const uint8_t OLED_DC = PIN_PA6;
const uint8_t OLED_RST = PIN_PA7;
#else
const uint8_t OLED_CLK = D13;
const uint8_t OLED_MOSI = D11;
const uint8_t OLED_CS = D10;
const uint8_t OLED_DC = D9;
const uint8_t OLED_RST = D8;
#endif

const char STUDENT_NAME[] = "YOUR NAME";

U8X8_SSD1306_128X64_NONAME_4W_SW_SPI display(
    OLED_CLK, OLED_MOSI, OLED_CS, OLED_DC, OLED_RST);

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
