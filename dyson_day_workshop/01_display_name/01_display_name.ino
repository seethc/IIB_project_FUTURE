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

#if defined(MEGATINYCORE)
const char BOARD_NAME[] = "ATtiny1616";
#else
const char BOARD_NAME[] = "Nano ESP32";
#endif

U8X8_SSD1306_128X64_NONAME_4W_SW_SPI display(
    OLED_CLK, OLED_MOSI, OLED_CS, OLED_DC, OLED_RST);

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

void drawNameScreen() {
  display.clearDisplay();
  drawCentered(1, "HELLO");
  drawCentered(3, STUDENT_NAME);
  drawCentered(6, BOARD_NAME);
}

void setup() {
  display.begin();
  display.setPowerSave(0);
  display.setFont(u8x8_font_chroma48medium8_r);
  drawNameScreen();
}

void loop() {
}
