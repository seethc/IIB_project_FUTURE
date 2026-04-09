#include <Arduino.h>
#include <SHA1.h>
#include <U8g2lib.h>
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
constexpr uint16_t RTC_TICKS_PER_SECOND = 1024;
constexpr uint32_t RTC_OVERFLOW_SECONDS = 64;
constexpr uint32_t TOTP_TIMESTEP_SECONDS = 30;
constexpr uint32_t DISPLAY_WINDOW_SECONDS = 30;
constexpr uint16_t DISPLAY_WINDOW_TICKS =
    DISPLAY_WINDOW_SECONDS * RTC_TICKS_PER_SECOND;

const uint8_t secretKey[KEY_LENGTH] = {
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0'};

U8G2_ST7305_200X200_1_4W_SW_SPI u8g2(
    U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

SHA1 hash;
uint8_t iKeyPad[64];
uint8_t oKeyPad[64];
volatile bool buttonPressed = false;
volatile uint32_t rtcOverflowSeconds = 0;
volatile bool rtcCompareMatched = false;

#define DISABLE_PORT_INPUTS(port)                                               \
  do {                                                                          \
    port.PIN0CTRL = PORT_ISC_INPUT_DISABLE_gc;                                  \
    port.PIN1CTRL = PORT_ISC_INPUT_DISABLE_gc;                                  \
    port.PIN2CTRL = PORT_ISC_INPUT_DISABLE_gc;                                  \
    port.PIN3CTRL = PORT_ISC_INPUT_DISABLE_gc;                                  \
    port.PIN4CTRL = PORT_ISC_INPUT_DISABLE_gc;                                  \
    port.PIN5CTRL = PORT_ISC_INPUT_DISABLE_gc;                                  \
    port.PIN6CTRL = PORT_ISC_INPUT_DISABLE_gc;                                  \
    port.PIN7CTRL = PORT_ISC_INPUT_DISABLE_gc;                                  \
  } while (0)

ISR(RTC_CNT_vect) {
  const uint8_t flags = RTC.INTFLAGS;

  if ((flags & RTC_OVF_bm) != 0) {
    rtcOverflowSeconds += RTC_OVERFLOW_SECONDS;
  }

  if ((flags & RTC_CMP_bm) != 0) {
    rtcCompareMatched = true;
  }

  RTC.INTFLAGS = flags & (RTC_OVF_bm | RTC_CMP_bm);
}

void buttonISR() {
  buttonPressed = true;
}

void setupDisplayPins() {
  pinMode(PIN_CLK, OUTPUT);
  digitalWrite(PIN_CLK, LOW);
  pinMode(PIN_MOSI, OUTPUT);
  digitalWrite(PIN_MOSI, LOW);
  pinMode(PIN_DC, OUTPUT);
  digitalWrite(PIN_DC, LOW);
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  pinMode(PIN_RST, OUTPUT);
  digitalWrite(PIN_RST, HIGH);
}

void writeDisplayByte(uint8_t value) {
  for (uint8_t mask = 0x80; mask != 0; mask >>= 1) {
    digitalWrite(PIN_MOSI, (value & mask) != 0 ? HIGH : LOW);
    digitalWrite(PIN_CLK, HIGH);
    digitalWrite(PIN_CLK, LOW);
  }
}

void sendDisplayCommand(uint8_t command) {
  digitalWrite(PIN_CS, LOW);
  digitalWrite(PIN_DC, LOW);
  writeDisplayByte(command);
  digitalWrite(PIN_CS, HIGH);
}

void shutdownDisplay() {
  setupDisplayPins();

  digitalWrite(PIN_RST, LOW);
  delay(20);
  digitalWrite(PIN_RST, HIGH);
  delay(10);

  sendDisplayCommand(0x28);
  sendDisplayCommand(0x10);
  delay(5);

  digitalWrite(PIN_CLK, LOW);
  digitalWrite(PIN_MOSI, LOW);
  digitalWrite(PIN_DC, LOW);
  digitalWrite(PIN_CS, HIGH);
  digitalWrite(PIN_RST, HIGH);
}

void beginDisplay() {
  u8g2.begin();
  u8g2.setContrast(0x90);
}

void parkDisplayPins() {
  digitalWrite(PIN_CLK, LOW);
  digitalWrite(PIN_MOSI, LOW);
  digitalWrite(PIN_DC, LOW);
  digitalWrite(PIN_CS, HIGH);
  digitalWrite(PIN_RST, HIGH);
}

void disableUnusedPeripherals() {
  ADC0.CTRLA = 0;

#ifdef AC0_CTRLA
  AC0.CTRLA = 0;
#endif
#ifdef DAC0_CTRLA
  DAC0.CTRLA = 0;
#endif
#ifdef VREF_CTRLA
  VREF.CTRLA = 0;
#endif
#ifdef CCL_CTRLA
  CCL.CTRLA = 0;
#endif
#ifdef USART0_CTRLA
  USART0.CTRLA = 0;
  USART0.CTRLB = 0;
#endif
#ifdef SPI0_CTRLA
  SPI0.CTRLA = 0;
  SPI0.INTCTRL = 0;
#endif
#ifdef TWI0_MCTRLA
  TWI0.MCTRLA = 0;
  TWI0.SCTRLA = 0;
#endif

#ifdef BOD_SLEEP_DIS_gc
  BOD.CTRLA = (BOD.CTRLA & ~BOD_SLEEP_gm) | BOD_SLEEP_DIS_gc;
#endif
}

void disableDigitalInputBuffers() {
#ifdef PORTA
  DISABLE_PORT_INPUTS(PORTA);
#endif
#ifdef PORTB
  DISABLE_PORT_INPUTS(PORTB);
#endif
#ifdef PORTC
  DISABLE_PORT_INPUTS(PORTC);
#endif
}

void configureWakeButton() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BUTTON), buttonISR, FALLING);
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

  RTC.CLKSEL = RTC_CLKSEL_INT32K_gc;
  RTC.PER = 0xFFFF;
  RTC.CNT = 0;

  waitForRtcSync();

  RTC.INTCTRL = RTC_OVF_bm;
  RTC.CTRLA = RTC_PRESCALER_DIV32_gc | RTC_RTCEN_bm | RTC_RUNSTDBY_bm;

  while (RTC.STATUS & RTC_CTRLABUSY_bm) {
  }
}

uint32_t getRTCSeconds() {
  uint32_t overflowSecondsSnapshot;
  uint16_t currentCountSnapshot;
  uint8_t rtcFlagsSnapshot;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    currentCountSnapshot = RTC.CNT;
    overflowSecondsSnapshot = rtcOverflowSeconds;
    rtcFlagsSnapshot = RTC.INTFLAGS;

    if ((rtcFlagsSnapshot & RTC_OVF_bm) != 0 && currentCountSnapshot < 0x8000) {
      overflowSecondsSnapshot += RTC_OVERFLOW_SECONDS;
    }
  }

  return overflowSecondsSnapshot + (currentCountSnapshot / RTC_TICKS_PER_SECOND);
}

void prepareHMACPads() {
  memset(iKeyPad, 0x36, sizeof(iKeyPad));
  memset(oKeyPad, 0x5C, sizeof(oKeyPad));

  for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
    iKeyPad[i] ^= secretKey[i];
    oKeyPad[i] ^= secretKey[i];
  }
}

uint32_t generateTOTP(uint32_t timeSeconds) {
  uint64_t counter = timeSeconds / TOTP_TIMESTEP_SECONDS;
  uint8_t counterBytes[8];

  for (int8_t i = 7; i >= 0; --i) {
    counterBytes[i] = counter & 0xFF;
    counter >>= 8;
  }

  uint8_t tempHash[20];
  hash.reset();
  hash.update(iKeyPad, sizeof(iKeyPad));
  hash.update(counterBytes, sizeof(counterBytes));
  hash.finalize(tempHash, sizeof(tempHash));

  uint8_t finalHash[20];
  hash.reset();
  hash.update(oKeyPad, sizeof(oKeyPad));
  hash.update(tempHash, sizeof(tempHash));
  hash.finalize(finalHash, sizeof(finalHash));

  const int offset = finalHash[19] & 0x0F;
  const uint32_t binary =
      ((uint32_t)(finalHash[offset] & 0x7F) << 24) |
      ((uint32_t)(finalHash[offset + 1] & 0xFF) << 16) |
      ((uint32_t)(finalHash[offset + 2] & 0xFF) << 8) |
      ((uint32_t)(finalHash[offset + 3] & 0xFF));

  return binary % 1000000UL;
}

void formatSixDigits(uint32_t code, char *text) {
  uint32_t value = code % 1000000UL;

  for (int8_t i = 5; i >= 0; --i) {
    text[i] = static_cast<char>('0' + (value % 10));
    value /= 10;
  }

  text[6] = '\0';
}

void displayCode(uint32_t code) {
  char text[7];
  formatSixDigits(code, text);

  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_logisoso24_tn);
    const int textWidth = u8g2.getStrWidth(text);
    const int textHeight = u8g2.getAscent() - u8g2.getDescent();
    const int x = (200 - textWidth) / 2;
    const int y = 28 + ((160 - textHeight) / 2) + u8g2.getAscent();

    u8g2.drawStr(x, y, text);
  } while (u8g2.nextPage());
}

void enterStandby() {
  set_sleep_mode(SLEEP_MODE_STANDBY);
  sleep_enable();
  sleep_cpu();
  sleep_disable();
}

void sleepForDisplayWindow() {
  rtcCompareMatched = false;
  RTC.INTFLAGS = RTC_CMP_bm;

  while (RTC.STATUS & RTC_CMPBUSY_bm) {
  }
  RTC.CMP = static_cast<uint16_t>(RTC.CNT + DISPLAY_WINDOW_TICKS);
  while (RTC.STATUS & RTC_CMPBUSY_bm) {
  }

  RTC.INTCTRL |= RTC_CMP_bm;

  while (!rtcCompareMatched) {
    enterStandby();
  }

  RTC.INTCTRL &= static_cast<uint8_t>(~RTC_CMP_bm);
}

void showTotpWindow() {
  const uint32_t code = generateTOTP(getRTCSeconds());

  beginDisplay();
  displayCode(code);
  parkDisplayPins();
  disableUnusedPeripherals();
  sleepForDisplayWindow();

  buttonPressed = false;
  shutdownDisplay();
}

void setup() {
  shutdownDisplay();
  setupRTC();
  disableUnusedPeripherals();
  disableDigitalInputBuffers();
  configureWakeButton();
  prepareHMACPads();
  sei();
}

void loop() {
  if (buttonPressed) {
    buttonPressed = false;
    showTotpWindow();
  }

  enterStandby();
}
