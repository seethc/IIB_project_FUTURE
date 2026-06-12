#include <Arduino.h>
#include <U8g2lib.h>

#define PIN_CLK PIN_PA4
#define PIN_MOSI PIN_PA5
#define PIN_CS PIN_PA3
#define PIN_DC PIN_PA6
#define PIN_RST PIN_PA7

const char STUDENT_NAME[] = "YOUR NAME";

U8G2_SSD1306_128X64_NONAME_1_4W_SW_SPI display(
    U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

void drawCentered(const char *text, int16_t y) {
  int16_t width = display.getStrWidth(text);
  display.drawStr((128 - width) / 2, y, text);
}

void drawNameScreen() {
  display.firstPage();
  do {
    display.setFont(u8g2_font_6x10_tf);
    drawCentered("HELLO", 12);

    display.setFont(u8g2_font_helvB12_tf);
    drawCentered(STUDENT_NAME, 36);

    display.setFont(u8g2_font_6x10_tf);
    drawCentered("ATtiny1616", 58);
  } while (display.nextPage());
}

void setup() {
  display.begin();
  drawNameScreen();
}

void loop() {
}
