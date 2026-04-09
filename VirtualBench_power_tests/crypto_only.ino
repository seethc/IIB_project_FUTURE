#include <Arduino.h>
#include <Crypto.h>
#include <SHA1.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <string.h>
#include <util/atomic.h>

#define PIN_CLK PIN_PC0
#define PIN_MOSI PIN_PC2
#define PIN_CS PIN_PC3
#define PIN_DC PIN_PA3
#define PIN_RST PIN_PA4
#define PIN_BUTTON PIN_PA6

constexpr uint8_t KEY_LENGTH = 20;
constexpr uint16_t WAKE_INTERVAL_SECONDS = 5;
constexpr uint32_t TOTP_STEP_SECONDS = 5;

const uint8_t SECRET_KEY[KEY_LENGTH] = {
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0'};

SHA1 sha1;
uint8_t iKeyPad[64];
uint8_t oKeyPad[64];

volatile uint32_t rtcBaseSeconds = 0;
volatile bool rtcCompareMatched = false;
volatile uint32_t lastCode = 0;

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

void parkDisplayHardware() {
  pinMode(PIN_CLK, OUTPUT);
  digitalWrite(PIN_CLK, LOW);
  pinMode(PIN_MOSI, OUTPUT);
  digitalWrite(PIN_MOSI, LOW);
  pinMode(PIN_DC, OUTPUT);
  digitalWrite(PIN_DC, LOW);
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_RST, OUTPUT);
  digitalWrite(PIN_RST, LOW);
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

uint32_t getRtcSeconds() {
  uint32_t overflowSecondsSnapshot;
  uint16_t currentCountSnapshot;
  uint8_t rtcFlagsSnapshot;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    currentCountSnapshot = RTC.CNT;
    overflowSecondsSnapshot = rtcBaseSeconds;
    rtcFlagsSnapshot = RTC.INTFLAGS;

    if ((rtcFlagsSnapshot & RTC_OVF_bm) != 0 && currentCountSnapshot < 0x8000) {
      overflowSecondsSnapshot += 65536UL;
    }
  }

  return overflowSecondsSnapshot + currentCountSnapshot;
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

void prepareHMACPads() {
  memset(iKeyPad, 0x36, sizeof(iKeyPad));
  memset(oKeyPad, 0x5C, sizeof(oKeyPad));

  for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
    iKeyPad[i] ^= SECRET_KEY[i];
    oKeyPad[i] ^= SECRET_KEY[i];
  }
}

uint32_t generateTOTP(uint32_t timeSeconds) {
  uint64_t counter = timeSeconds / TOTP_STEP_SECONDS;
  uint8_t counterBytes[8];

  for (int8_t i = 7; i >= 0; --i) {
    counterBytes[i] = counter & 0xFF;
    counter >>= 8;
  }

  uint8_t tempHash[20];
  sha1.reset();
  sha1.update(iKeyPad, sizeof(iKeyPad));
  sha1.update(counterBytes, sizeof(counterBytes));
  sha1.finalize(tempHash, sizeof(tempHash));

  uint8_t finalHash[20];
  sha1.reset();
  sha1.update(oKeyPad, sizeof(oKeyPad));
  sha1.update(tempHash, sizeof(tempHash));
  sha1.finalize(finalHash, sizeof(finalHash));

  const int offset = finalHash[19] & 0x0F;
  const uint32_t binary =
      ((uint32_t)(finalHash[offset] & 0x7F) << 24) |
      ((uint32_t)(finalHash[offset + 1] & 0xFF) << 16) |
      ((uint32_t)(finalHash[offset + 2] & 0xFF) << 8) |
      ((uint32_t)(finalHash[offset + 3] & 0xFF));

  return binary % 1000000UL;
}

void setup() {
  parkDisplayHardware();
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  setupRTC();
  prepareHMACPads();
  sei();

  lastCode = generateTOTP(getRtcSeconds());
}

void loop() {
  sleepForRtcSeconds(WAKE_INTERVAL_SECONDS);
  lastCode = generateTOTP(getRtcSeconds());
}
