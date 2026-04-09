#include <Arduino.h>
#include <SPI.h>
#include <U8g2lib.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>

#define PIN_CLK PIN_PC0
#define PIN_MOSI PIN_PC2
#define PIN_CS PIN_PC3
#define PIN_DC PIN_PA3
#define PIN_RST PIN_PA4
#define PIN_BUTTON PIN_PA6

constexpr uint16_t WAKE_INTERVAL_SECONDS = 5;

U8G2_ST7305_200X200_1_4W_SW_SPI u8g2(
    U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

volatile uint32_t rtcBaseSeconds = 0;
volatile bool rtcCompareMatched = false;

bool showAlternateScreen = false;

ISR(RTC_CNT_vect) {
  const uint8_t flags = RTC.INTFLAGS;

  if ((flags & RTC_OVF_bm) != 0) {
    rtcBaseSeconds += 65536UL;
  }

  if ((flags & RTC_CMP_bm) != 0) {
    rtcCompareMatched = true;
  }

  RTC.INTFLAGS = flags & (RTC_OVF_bm | RTC_CMP_bm);
}

void waitForRtcSync() {
  while (RTC.STATUS > 0 || RTC.PITSTATUS > 0) {
  }
}

void setupRTC() {
  waitForRtcSync();

  RTC.CTRLA = 0;
  RTC.INTCTRL = 0;
  RTC.INTFLAGS = RTC_OVF_bm | RTC_CMP_bm;
  RTC.PITINTCTRL = 0;
  RTC.PITCTRLA = 0;
  RTC.PITINTFLAGS = RTC_PI_bm;

  _PROTECTED_WRITE(CLKCTRL.XOSC32KCTRLA,
                   CLKCTRL_RUNSTDBY_bm | CLKCTRL_CSUT_64K_gc);
  _PROTECTED_WRITE(CLKCTRL.XOSC32KCTRLA,
                   CLKCTRL_ENABLE_bm | CLKCTRL_RUNSTDBY_bm |
                       CLKCTRL_CSUT_64K_gc);

  RTC.CLKSEL = RTC_CLKSEL_TOSC32K_gc;
  RTC.PER = 0xFFFF;
  RTC.CMP = 0;
  RTC.CNT = 0;

  waitForRtcSync();

  RTC.INTCTRL = RTC_OVF_bm;
  RTC.CTRLA = RTC_PRESCALER_DIV32768_gc | RTC_RTCEN_bm | RTC_RUNSTDBY_bm;

  while (RTC.STATUS & RTC_CTRLABUSY_bm) {
  }
  while ((CLKCTRL.MCLKSTATUS & CLKCTRL_XOSC32KS_bm) == 0) {
  }
}

void enterStandby() {
  set_sleep_mode(SLEEP_MODE_STANDBY);
  sleep_enable();
  sleep_cpu();
  sleep_disable();
}

void sleepForRtcSeconds(uint16_t seconds) {
  rtcCompareMatched = false;
  RTC.INTFLAGS = RTC_CMP_bm;

  while (RTC.STATUS & RTC_CMPBUSY_bm) {
  }
  RTC.CMP = static_cast<uint16_t>(RTC.CNT + seconds);
  while (RTC.STATUS & RTC_CMPBUSY_bm) {
  }

  RTC.INTCTRL |= RTC_CMP_bm;

  while (!rtcCompareMatched) {
    enterStandby();
  }

  RTC.INTCTRL &= static_cast<uint8_t>(~RTC_CMP_bm);
}

void drawCenteredLabel(const char *text, const uint8_t *font, int16_t y) {
  u8g2.setFont(font);
  const int16_t width = u8g2.getStrWidth(text);
  u8g2.drawStr((200 - width) / 2, y, text);
}

void drawCurrentFrame() {
  u8g2.firstPage();
  do {
    if (!showAlternateScreen) {
      drawCenteredLabel("SECURE", u8g2_font_logisoso24_tf, 48);
      u8g2.drawFrame(18, 66, 164, 64);
      u8g2.drawDisc(42, 98, 14);
      u8g2.drawDisc(100, 98, 14);
      u8g2.drawDisc(158, 98, 14);
      u8g2.drawHLine(30, 148, 140);
      u8g2.drawHLine(30, 156, 140);
    } else {
      drawCenteredLabel("FUTURE", u8g2_font_logisoso24_tf, 48);
      for (uint8_t row = 0; row < 3; ++row) {
        for (uint8_t col = 0; col < 3; ++col) {
          const uint8_t x = 28 + (col * 48);
          const uint8_t y = 74 + (row * 28);
          if (((row + col) & 0x01) == 0) {
            u8g2.drawBox(x, y, 32, 20);
          } else {
            u8g2.drawFrame(x, y, 32, 20);
          }
        }
      }
      u8g2.drawCircle(100, 166, 18);
      u8g2.drawLine(82, 166, 118, 166);
      u8g2.drawLine(100, 148, 100, 184);
    }
  } while (u8g2.nextPage());
}

void setup() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  setupRTC();

  u8g2.begin();
  u8g2.setContrast(0x90);

  sei();
  drawCurrentFrame();
}

void loop() {
  sleepForRtcSeconds(WAKE_INTERVAL_SECONDS);
  showAlternateScreen = !showAlternateScreen;
  drawCurrentFrame();
}
