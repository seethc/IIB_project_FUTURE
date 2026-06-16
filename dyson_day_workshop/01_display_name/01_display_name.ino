#include <Arduino.h>
#include <U8x8lib.h>
#include <Wire.h>
#include <string.h>

const char STUDENT_NAME[] = "YOUR NAME";

#if defined(MEGATINYCORE)
const char BOARD_NAME[] = "ATtiny1616";
#else
const char BOARD_NAME[] = "Nano ESP32";
#endif

U8X8_SSD1306_128X64_NONAME_HW_I2C display(U8X8_PIN_NONE);

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
