#include <Arduino.h>
#include <EEPROM.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <Crypto.h>
#include <SHA256.h>
#include <string.h>
#include <stdlib.h>
#include <avr/sleep.h>
#include <avr/interrupt.h>
#include <util/atomic.h>

// PINS (ATtiny3216)
// SPI display - using software SPI on port C pins.
#define PIN_CLK PIN_PC0
#define PIN_MOSI PIN_PC2
#define PIN_CS PIN_PC3
#define PIN_DC PIN_PA3
#define PIN_RST PIN_PA4
#define PIN_BUTTON PIN_PA6
// P-channel high-side switch: LOW powers the LCD rail, HIGH disconnects it.
#define PIN_LCD_POWER_GATE PIN_PB0

#ifndef TOTP_TIMESTEP_SECONDS
#define TOTP_TIMESTEP_SECONDS 30UL
#endif

#ifndef TOKEN_FIRMWARE_VERSION
#define TOKEN_FIRMWARE_VERSION "token-main3-3profile-sha256-1.0"
#endif

#ifndef UART_ADMIN_WINDOW_SECONDS
#define UART_ADMIN_WINDOW_SECONDS 300UL
#endif

#ifndef RTC_CRYSTAL_STARTUP_TIMEOUT_MS
#define RTC_CRYSTAL_STARTUP_TIMEOUT_MS 2000UL
#endif

// DISPLAY
U8G2_ST7305_200X200_1_4W_SW_SPI u8g2(
    U8G2_R2, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

// TOTP CONFIG
constexpr uint8_t KEY_LENGTH = 20;
constexpr uint8_t CHALLENGE_LENGTH = 16;
constexpr uint8_t SHA256_DIGEST_LENGTH = 32;
constexpr uint8_t PROFILE_COUNT = 3;
constexpr uint16_t PROFILE_EEPROM_BYTES = KEY_LENGTH + 4 + 4 + 1;
constexpr uint16_t KEY_EEPROM_ADDR = 0;
constexpr uint16_t TIMESTEP_EEPROM_OFFSET = KEY_LENGTH;
constexpr uint16_t ELAPSED_OFFSET_EEPROM_OFFSET = TIMESTEP_EEPROM_OFFSET + 4;
constexpr uint16_t PROVISIONED_EEPROM_OFFSET = ELAPSED_OFFSET_EEPROM_OFFSET + 4;
constexpr uint8_t PROVISIONED_MARKER = 0xA5;
constexpr uint32_t DEFAULT_TOTP_TIMESTEP_SECONDS = TOTP_TIMESTEP_SECONDS;
constexpr uint32_t UART_ADMIN_WINDOW_SECONDS_VALUE = UART_ADMIN_WINDOW_SECONDS;
constexpr uint32_t RTC_CRYSTAL_STARTUP_TIMEOUT_MS_VALUE =
    RTC_CRYSTAL_STARTUP_TIMEOUT_MS;
constexpr uint16_t DISPLAY_WINDOW_SECONDS = 30;
constexpr uint32_t RTC_OVERFLOW_SECONDS = 65536UL;
constexpr uint16_t LCD_POWER_SETTLE_MS = 20;
constexpr uint16_t RESET_MODE_LONG_PRESS_MS = 1200;
constexpr uint16_t BUTTON_DEBOUNCE_MS = 45;
constexpr uint16_t RESET_MODE_ARM_WINDOW_MS = 12000;
constexpr uint16_t RESET_MODE_REFRESH_MS = 250;
constexpr uint16_t FEEDBACK_DISPLAY_MS = 3000;

SHA256 hash;
uint8_t profileSecretKeys[PROFILE_COUNT][KEY_LENGTH];
uint32_t profileTimesteps[PROFILE_COUNT];
uint32_t profileElapsedOffsets[PROFILE_COUNT];
bool profileProvisioned[PROFILE_COUNT];
uint8_t activeSecretKey[KEY_LENGTH];
uint8_t i_key_pad[64];
uint8_t o_key_pad[64];
uint32_t activeTimestep = DEFAULT_TOTP_TIMESTEP_SECONDS;
uint8_t activeProfileIndex = 0;
volatile bool buttonPressed = false;
uint32_t lastButtonEventMs = 0;
volatile uint32_t totalSeconds = 0;
volatile bool rtcCompareMatched = false;
bool rtcUsingExternalCrystal = false;
volatile uint16_t rtcCountSnapshot = 0;
volatile uint8_t rtcStatusSnapshot = 0;
volatile uint8_t rtcIntFlagsSnapshot = 0;
bool lcdPowerEnabled = false;
char uartLineBuffer[96];
uint8_t uartLineLength = 0;
uint32_t uartAdminAwakeUntil = 0;
char displayFeedback[22] = "";
uint32_t displayFeedbackUntilMs = 0;
bool resetModeActive = false;
uint32_t resetModeArmedUntilMs = 0;

void buttonISR();
void prepareHMACPads();
bool isProfileProvisioned(uint8_t profileIndex);
bool feedbackActive();

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
    totalSeconds += RTC_OVERFLOW_SECONDS;
  }

  if ((flags & RTC_CMP_bm) != 0) {
    rtcCompareMatched = true;
  }

  RTC.INTFLAGS = flags & (RTC_OVF_bm | RTC_CMP_bm);
}

void displayMessage(const char *line1, const char *line2 = nullptr) {
  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_6x12_tf);
    if (line1) {
      const int width1 = u8g2.getStrWidth(line1);
      u8g2.drawStr((200 - width1) / 2, 92, line1);
    }
    if (line2) {
      const int width2 = u8g2.getStrWidth(line2);
      u8g2.drawStr((200 - width2) / 2, 112, line2);
    }
  } while (u8g2.nextPage());
}

void pollRTCState() {
  rtcCountSnapshot = RTC.CNT;
  rtcStatusSnapshot = RTC.STATUS;
  rtcIntFlagsSnapshot = RTC.INTFLAGS;
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

void parkDisplayPinsForPowerOff() {
  pinMode(PIN_CLK, OUTPUT);
  digitalWrite(PIN_CLK, LOW);
  pinMode(PIN_MOSI, OUTPUT);
  digitalWrite(PIN_MOSI, LOW);
  pinMode(PIN_DC, OUTPUT);
  digitalWrite(PIN_DC, LOW);
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, LOW);
  pinMode(PIN_RST, OUTPUT);
  digitalWrite(PIN_RST, LOW);
}

void setupLcdPowerGate() {
  pinMode(PIN_LCD_POWER_GATE, OUTPUT);
  digitalWrite(PIN_LCD_POWER_GATE, HIGH);
  lcdPowerEnabled = false;
  parkDisplayPinsForPowerOff();
}

void enableLcdPower() {
  pinMode(PIN_LCD_POWER_GATE, OUTPUT);

  if (!lcdPowerEnabled) {
    parkDisplayPinsForPowerOff();
    digitalWrite(PIN_LCD_POWER_GATE, LOW);
    lcdPowerEnabled = true;
    delay(LCD_POWER_SETTLE_MS);
  }
}

void disableLcdPower() {
  pinMode(PIN_LCD_POWER_GATE, OUTPUT);
  digitalWrite(PIN_LCD_POWER_GATE, HIGH);
  lcdPowerEnabled = false;
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
  if (!lcdPowerEnabled) {
    parkDisplayPinsForPowerOff();
    disableLcdPower();
    return;
  }

  setupDisplayPins();

  digitalWrite(PIN_RST, LOW);
  delay(20);
  digitalWrite(PIN_RST, HIGH);
  delay(10);

  sendDisplayCommand(0x28);
  sendDisplayCommand(0x10);
  delay(5);

  parkDisplayPinsForPowerOff();
  disableLcdPower();
}

void beginDisplay() {
  enableLcdPower();
  setupDisplayPins();
  u8g2.begin();
  u8g2.setContrast(0x90);
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
#ifdef TCA0_SINGLE_CTRLA
  TCA0.SINGLE.CTRLA = 0;
  TCA0.SINGLE.INTCTRL = 0;
#endif
#ifdef TCB0_CTRLA
  TCB0.CTRLA = 0;
  TCB0.INTCTRL = 0;
#endif
#ifdef TCB1_CTRLA
  TCB1.CTRLA = 0;
  TCB1.INTCTRL = 0;
#endif

#ifdef BOD_SLEEP_DIS_gc
  BOD.CTRLA = (BOD.CTRLA & ~BOD_SLEEP_gm) | BOD_SLEEP_DIS_gc;
#endif
}

void disableDigitalInputBuffersForSleep() {
#ifdef PORTA
  PORTA.PIN1CTRL = PORT_ISC_INPUT_DISABLE_gc;
  PORTA.PIN2CTRL = PORT_ISC_INPUT_DISABLE_gc;
  PORTA.PIN3CTRL = PORT_ISC_INPUT_DISABLE_gc;
  PORTA.PIN4CTRL = PORT_ISC_INPUT_DISABLE_gc;
  PORTA.PIN5CTRL = PORT_ISC_INPUT_DISABLE_gc;
  PORTA.PIN7CTRL = PORT_ISC_INPUT_DISABLE_gc;
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

void beginSerial() {
  Serial.swap(1);
  Serial.begin(9600, SERIAL_HALF_DUPLEX);
  PORTA.PIN1CTRL = PORT_PULLUPEN_bm;
  PORTA.PIN2CTRL = PORT_PULLUPEN_bm;
}

void prepareLowPowerSleep() {
  shutdownDisplay();
  disableUnusedPeripherals();
  disableDigitalInputBuffersForSleep();
  configureWakeButton();
}

void setupRTC() {
  while (RTC.STATUS > 0 || RTC.PITSTATUS > 0) {
  }

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
  RTC.CNT = 0;

  while (RTC.STATUS > 0) {
  }

  RTC.INTCTRL = RTC_OVF_bm;
  RTC.CTRLA = RTC_PRESCALER_DIV32768_gc | RTC_RTCEN_bm | RTC_RUNSTDBY_bm;

  while (RTC.STATUS & RTC_CTRLABUSY_bm) {
  }

  const uint32_t crystalWaitStart = millis();
  while ((CLKCTRL.MCLKSTATUS & CLKCTRL_XOSC32KS_bm) == 0 &&
         (millis() - crystalWaitStart) < RTC_CRYSTAL_STARTUP_TIMEOUT_MS_VALUE) {
    delay(1);
  }

  if ((CLKCTRL.MCLKSTATUS & CLKCTRL_XOSC32KS_bm) != 0) {
    rtcUsingExternalCrystal = true;
    pollRTCState();
    return;
  }

  RTC.CTRLA = 0;
  while (RTC.STATUS > 0) {
  }
  RTC.INTCTRL = 0;
  RTC.INTFLAGS = RTC_OVF_bm | RTC_CMP_bm;
  RTC.CLKSEL = RTC_CLKSEL_INT32K_gc;
  RTC.PER = 0xFFFF;
  RTC.CNT = 0;
  while (RTC.STATUS > 0) {
  }
  RTC.INTCTRL = RTC_OVF_bm;
  RTC.CTRLA = RTC_PRESCALER_DIV32768_gc | RTC_RTCEN_bm | RTC_RUNSTDBY_bm;
  while (RTC.STATUS & RTC_CTRLABUSY_bm) {
  }

  rtcUsingExternalCrystal = false;
  pollRTCState();
}

uint32_t getRTCRawSeconds() {
  uint32_t overflowSecondsSnapshot;
  uint16_t currentCountSnapshot;
  uint8_t rtcFlagsSnapshot;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    currentCountSnapshot = RTC.CNT;
    overflowSecondsSnapshot = totalSeconds;
    rtcFlagsSnapshot = RTC.INTFLAGS;

    if ((rtcFlagsSnapshot & RTC_OVF_bm) != 0 && currentCountSnapshot < 0x8000) {
      overflowSecondsSnapshot += RTC_OVERFLOW_SECONDS;
    }
  }

  return overflowSecondsSnapshot + currentCountSnapshot;
}

uint32_t getProfileElapsedSeconds(uint8_t profileIndex) {
  const uint32_t rawSeconds = getRTCRawSeconds();
  const uint8_t safeProfile = profileIndex < PROFILE_COUNT ? profileIndex : 0;
  const uint32_t offsetSnapshot = profileElapsedOffsets[safeProfile];

  if (!isProfileProvisioned(safeProfile)) {
    return 0;
  }

  if (rawSeconds < offsetSnapshot) {
    return 0;
  }
  return rawSeconds - offsetSnapshot;
}

uint32_t getRTCSeconds() { return getProfileElapsedSeconds(activeProfileIndex); }

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
    set_sleep_mode(SLEEP_MODE_STANDBY);
    sleep_enable();
    sleep_cpu();
    sleep_disable();
  }

  RTC.INTCTRL &= static_cast<uint8_t>(~RTC_CMP_bm);
}

void shortBusyDelay() {
  for (uint8_t i = 0; i < 40; ++i) {
    pollRTCState();
    delayMicroseconds(2500);
  }
}

uint16_t profileEEPROMBase(uint8_t profileIndex) {
  return KEY_EEPROM_ADDR +
         static_cast<uint16_t>(profileIndex) * PROFILE_EEPROM_BYTES;
}

void writeProfileSecretKeyToEEPROM(uint8_t profileIndex, const uint8_t *key) {
  const uint16_t base = profileEEPROMBase(profileIndex);
  for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
    EEPROM.update(base + i, key[i]);
  }
}

void writeProfileTimestepToEEPROM(uint8_t profileIndex,
                                  uint32_t timestepSeconds) {
  const uint16_t base = profileEEPROMBase(profileIndex) + TIMESTEP_EEPROM_OFFSET;
  for (uint8_t i = 0; i < 4; ++i) {
    EEPROM.update(base + i,
                  static_cast<uint8_t>((timestepSeconds >> (8 * i)) & 0xFF));
  }
}

uint32_t readProfileTimestepFromEEPROM(uint8_t profileIndex) {
  const uint16_t base = profileEEPROMBase(profileIndex) + TIMESTEP_EEPROM_OFFSET;
  uint32_t stored = 0;
  for (uint8_t i = 0; i < 4; ++i) {
    stored |= static_cast<uint32_t>(EEPROM.read(base + i)) << (8 * i);
  }

  if (stored == 0xFFFFFFFFUL || stored == 0 || stored > 3600UL) {
    return DEFAULT_TOTP_TIMESTEP_SECONDS;
  }
  return stored;
}

void writeProfileElapsedOffsetToEEPROM(uint8_t profileIndex, uint32_t offset) {
  const uint16_t base =
      profileEEPROMBase(profileIndex) + ELAPSED_OFFSET_EEPROM_OFFSET;
  for (uint8_t i = 0; i < 4; ++i) {
    EEPROM.update(base + i, static_cast<uint8_t>((offset >> (8 * i)) & 0xFF));
  }
}

uint32_t readProfileElapsedOffsetFromEEPROM(uint8_t profileIndex) {
  const uint16_t base =
      profileEEPROMBase(profileIndex) + ELAPSED_OFFSET_EEPROM_OFFSET;
  uint32_t stored = 0;
  for (uint8_t i = 0; i < 4; ++i) {
    stored |= static_cast<uint32_t>(EEPROM.read(base + i)) << (8 * i);
  }

  if (stored == 0xFFFFFFFFUL) {
    return 0;
  }
  return stored;
}

bool isProfileProvisioned(uint8_t profileIndex) {
  return profileProvisioned[profileIndex < PROFILE_COUNT ? profileIndex : 0];
}

bool isProvisioned() { return isProfileProvisioned(activeProfileIndex); }

void writeProfileProvisionedMarker(uint8_t profileIndex, bool provisioned) {
  const uint16_t addr = profileEEPROMBase(profileIndex) + PROVISIONED_EEPROM_OFFSET;
  EEPROM.update(addr, provisioned ? PROVISIONED_MARKER : 0x00);
  profileProvisioned[profileIndex] = provisioned;
}

void writeProvisionedMarker(bool provisioned) {
  writeProfileProvisionedMarker(activeProfileIndex, provisioned);
}

void storeProvisioning(const uint8_t *key, uint32_t timestepSeconds,
                       bool provisioned) {
  writeProfileSecretKeyToEEPROM(activeProfileIndex, key);
  writeProfileTimestepToEEPROM(activeProfileIndex, timestepSeconds);
  writeProfileProvisionedMarker(activeProfileIndex, provisioned);
  memcpy(profileSecretKeys[activeProfileIndex], key, KEY_LENGTH);
  profileTimesteps[activeProfileIndex] = timestepSeconds;
  memcpy(activeSecretKey, key, KEY_LENGTH);
  activeTimestep = timestepSeconds;
  prepareHMACPads();
}

void loadActiveProfileCrypto() {
  memcpy(activeSecretKey, profileSecretKeys[activeProfileIndex], KEY_LENGTH);
  activeTimestep = profileTimesteps[activeProfileIndex];
  prepareHMACPads();
}

void selectActiveProfile(uint8_t profileIndex) {
  activeProfileIndex = profileIndex % PROFILE_COUNT;
  loadActiveProfileCrypto();
}

void clearActiveProfile() {
  uint8_t blankKey[KEY_LENGTH] = {0};
  const uint32_t rawSeconds = getRTCRawSeconds();

  writeProfileSecretKeyToEEPROM(activeProfileIndex, blankKey);
  writeProfileTimestepToEEPROM(activeProfileIndex,
                               DEFAULT_TOTP_TIMESTEP_SECONDS);
  writeProfileElapsedOffsetToEEPROM(activeProfileIndex, rawSeconds);
  writeProfileProvisionedMarker(activeProfileIndex, false);

  memset(profileSecretKeys[activeProfileIndex], 0, KEY_LENGTH);
  profileTimesteps[activeProfileIndex] = DEFAULT_TOTP_TIMESTEP_SECONDS;
  profileElapsedOffsets[activeProfileIndex] = rawSeconds;
  loadActiveProfileCrypto();
}

void loadProvisioningFromEEPROM() {
  for (uint8_t profile = 0; profile < PROFILE_COUNT; ++profile) {
    const uint16_t base = profileEEPROMBase(profile);

    for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
      profileSecretKeys[profile][i] = EEPROM.read(base + i);
    }

    profileTimesteps[profile] = readProfileTimestepFromEEPROM(profile);
    profileElapsedOffsets[profile] =
        readProfileElapsedOffsetFromEEPROM(profile);
    profileProvisioned[profile] =
        EEPROM.read(base + PROVISIONED_EEPROM_OFFSET) == PROVISIONED_MARKER;

    if (!profileProvisioned[profile]) {
      memset(profileSecretKeys[profile], 0, KEY_LENGTH);
      profileTimesteps[profile] = DEFAULT_TOTP_TIMESTEP_SECONDS;
    }
  }

  selectActiveProfile(0);
}

void prepareHMACPads() {
  memset(i_key_pad, 0x36, sizeof(i_key_pad));
  memset(o_key_pad, 0x5C, sizeof(o_key_pad));

  for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
    i_key_pad[i] ^= activeSecretKey[i];
    o_key_pad[i] ^= activeSecretKey[i];
  }
}

uint32_t generateTOTP(uint32_t time) {
  const uint32_t safeTimestep = activeTimestep == 0 ? 30UL : activeTimestep;
  uint64_t counter = time / safeTimestep;

  uint8_t counterBytes[8];
  for (int i = 7; i >= 0; --i) {
    counterBytes[i] = counter & 0xFF;
    counter >>= 8;
  }

  uint8_t tempHash[SHA256_DIGEST_LENGTH];
  hash.reset();
  hash.update(i_key_pad, 64);
  hash.update(counterBytes, 8);
  hash.finalize(tempHash, sizeof(tempHash));

  uint8_t finalHash[SHA256_DIGEST_LENGTH];
  hash.reset();
  hash.update(o_key_pad, 64);
  hash.update(tempHash, sizeof(tempHash));
  hash.finalize(finalHash, sizeof(finalHash));

  const int offset = finalHash[SHA256_DIGEST_LENGTH - 1] & 0x0F;
  const uint32_t binary =
      ((uint32_t)(finalHash[offset] & 0x7F) << 24) |
      ((uint32_t)(finalHash[offset + 1] & 0xFF) << 16) |
      ((uint32_t)(finalHash[offset + 2] & 0xFF) << 8) |
      ((uint32_t)(finalHash[offset + 3] & 0xFF));

  return binary % 1000000;
}

void displayCode(uint32_t code, uint32_t currentSeconds) {
  char text[7];
  char profileLine[16];
  char debugLine[24];
  char counterLine[24];
  char statusLine[24];
  const uint8_t *codeFont = u8g2_font_logisoso46_tn;
  uint16_t counterSnapshot;
  uint8_t statusSnapshot;
  uint8_t intFlagsSnapshot;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    counterSnapshot = rtcCountSnapshot;
    statusSnapshot = rtcStatusSnapshot;
    intFlagsSnapshot = rtcIntFlagsSnapshot;
  }

  sprintf(text, "%06lu", code);
  sprintf(profileLine, "Profile %u", activeProfileIndex + 1);
  sprintf(debugLine,
          "CLK:%s SEC:%lu",
          rtcUsingExternalCrystal ? "EXT" : "INT",
          currentSeconds);
  sprintf(counterLine, "CNT:%u", (unsigned int)counterSnapshot);
  sprintf(statusLine, "ST:%u FL:%u", (unsigned int)statusSnapshot,
          (unsigned int)intFlagsSnapshot);

  constexpr int displayWidth = 200;
  constexpr int displayHeight = 200;
  constexpr int codeTop = 66;
  constexpr int codeBottomPadding = 6;
  constexpr int codeAreaHeight = displayHeight - codeTop - codeBottomPadding;

  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_10x20_tf);
    const int profileWidth = u8g2.getStrWidth(profileLine);
    u8g2.drawStr((200 - profileWidth) / 2, 22, profileLine);

    u8g2.setFont(u8g2_font_6x12_tf);
    u8g2.drawStr(8, 40, debugLine);
    u8g2.drawStr(8, 54, counterLine);
    u8g2.drawStr(8, 68, statusLine);

    u8g2.setFont(codeFont);

    const int textWidth = u8g2.getStrWidth(text);
    const int codeHeight = u8g2.getAscent() - u8g2.getDescent();
    const int x = (displayWidth - textWidth) / 2;
    const int y = codeTop + ((codeAreaHeight - codeHeight) / 2) + u8g2.getAscent();

    u8g2.drawStr(x, y, text);
  } while (u8g2.nextPage());
}

void displayUnsetProfile() {
  char profileLine[16];
  sprintf(profileLine, "Profile %u", activeProfileIndex + 1);

  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_10x20_tf);
    int profileWidth = u8g2.getStrWidth(profileLine);
    u8g2.drawStr((200 - profileWidth) / 2, 84, profileLine);

    const char *unsetLine = "Not Set";
    int unsetWidth = u8g2.getStrWidth(unsetLine);
    u8g2.drawStr((200 - unsetWidth) / 2, 114, unsetLine);
  } while (u8g2.nextPage());
}

void displayActiveProfile() {
  pollRTCState();
  if (!isProvisioned()) {
    displayUnsetProfile();
    return;
  }

  const uint32_t currentSeconds = getRTCSeconds();
  displayCode(generateTOTP(currentSeconds), currentSeconds);
}

void cycleToNextProfile() {
  selectActiveProfile((activeProfileIndex + 1) % PROFILE_COUNT);
  displayFeedback[0] = '\0';
}

void displayResetMode() {
  char profileLine[16];
  char codeLine[8];
  char elapsedLine[24];
  char rawLine[24];
  char countLine[24];
  const bool provisioned = isProvisioned();
  const char *registrationLine = provisioned ? "REGISTERED YES" : "NOT SET";
  uint16_t counterSnapshot;
  uint32_t rawSeconds = getRTCRawSeconds();
  uint32_t elapsedSeconds = getRTCSeconds();
  const uint32_t code = provisioned ? generateTOTP(elapsedSeconds) : 0;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    counterSnapshot = rtcCountSnapshot;
  }

  sprintf(profileLine, "Profile %u", activeProfileIndex + 1);
  if (provisioned) {
    sprintf(codeLine, "%06lu", code);
  } else {
    strcpy(codeLine, "Not Set");
  }
  sprintf(elapsedLine, "ELAPSED %lu", elapsedSeconds);
  sprintf(rawLine, "RAW %lu", rawSeconds);
  sprintf(countLine, "CNT %u", (unsigned int)counterSnapshot);

  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_6x12_tf);
    const char *feedback = feedbackActive() ? displayFeedback : "UART READY";
    const int feedbackWidth = u8g2.getStrWidth(feedback);
    const int profileWidth = u8g2.getStrWidth(profileLine);
    const int registrationWidth = u8g2.getStrWidth(registrationLine);
    u8g2.drawStr((200 - profileWidth) / 2, 16, profileLine);
    u8g2.drawStr((200 - feedbackWidth) / 2, 34, feedback);
    u8g2.drawStr((200 - registrationWidth) / 2, 52, registrationLine);

    u8g2.drawStr(88, 72, "CODE");

    u8g2.setFont(provisioned ? u8g2_font_logisoso32_tn : u8g2_font_10x20_tf);
    int codeWidth = u8g2.getStrWidth(codeLine);
    u8g2.drawStr((200 - codeWidth) / 2, 104, codeLine);

    u8g2.setFont(u8g2_font_6x12_tf);
    int elapsedWidth = u8g2.getStrWidth(elapsedLine);
    int rawWidth = u8g2.getStrWidth(rawLine);
    int countWidth = u8g2.getStrWidth(countLine);
    u8g2.drawStr((200 - elapsedWidth) / 2, 128, elapsedLine);
    u8g2.drawStr((200 - rawWidth) / 2, 144, rawLine);
    u8g2.drawStr((200 - countWidth) / 2, 160, countLine);
    u8g2.drawStr(46, 184, "HOLD TO EXIT");
  } while (u8g2.nextPage());
}

void clearDisplay() {
  u8g2.firstPage();
  do {
  } while (u8g2.nextPage());
}

void buttonISR() {
  buttonPressed = true;
}

bool consumeButtonPress() {
  if (!buttonPressed) {
    return false;
  }

  buttonPressed = false;
  const uint32_t now = millis();
  if (lastButtonEventMs != 0 &&
      static_cast<int32_t>(now - lastButtonEventMs) < BUTTON_DEBOUNCE_MS) {
    return false;
  }
  lastButtonEventMs = now;
  return true;
}

bool buttonIsDown() {
  return digitalRead(PIN_BUTTON) == LOW;
}

bool acceptButtonDownAsPressStart() {
  const uint32_t now = millis();
  if (lastButtonEventMs != 0 &&
      static_cast<int32_t>(now - lastButtonEventMs) < BUTTON_DEBOUNCE_MS) {
    return false;
  }
  lastButtonEventMs = now;
  return true;
}

void armResetModeEntry() {
  resetModeArmedUntilMs = millis() + RESET_MODE_ARM_WINDOW_MS;
}

bool resetModeEntryArmed() {
  return static_cast<int32_t>(resetModeArmedUntilMs - millis()) > 0;
}

void setDisplayFeedback(const char *message) {
  strncpy(displayFeedback, message, sizeof(displayFeedback) - 1);
  displayFeedback[sizeof(displayFeedback) - 1] = '\0';
  displayFeedbackUntilMs = millis() + FEEDBACK_DISPLAY_MS;
}

bool feedbackActive() {
  return displayFeedback[0] != '\0' &&
         static_cast<int32_t>(displayFeedbackUntilMs - millis()) > 0;
}

void resetElapsedTime() {
  const uint32_t rawSeconds = getRTCRawSeconds();

  profileElapsedOffsets[activeProfileIndex] = rawSeconds;
  writeProfileElapsedOffsetToEEPROM(activeProfileIndex, rawSeconds);

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { rtcCompareMatched = false; }

  RTC.INTFLAGS = RTC_CMP_bm;
  pollRTCState();
}

void extendUARTAdminWindow() {
  if (UART_ADMIN_WINDOW_SECONDS_VALUE == 0) {
    return;
  }
  uartAdminAwakeUntil = getRTCSeconds() + UART_ADMIN_WINDOW_SECONDS_VALUE;
}

bool uartAdminWindowActive() {
  if (UART_ADMIN_WINDOW_SECONDS_VALUE == 0) {
    return false;
  }
  return static_cast<int32_t>(uartAdminAwakeUntil - getRTCSeconds()) > 0;
}

void sendProtocolError(const char *code, const char *message) {
  Serial.print("ERR ");
  Serial.print(code);
  Serial.print(" ");
  Serial.println(message);
}

int hexNibble(char value) {
  if (value >= '0' && value <= '9') {
    return value - '0';
  }
  if (value >= 'a' && value <= 'f') {
    return value - 'a' + 10;
  }
  if (value >= 'A' && value <= 'F') {
    return value - 'A' + 10;
  }
  return -1;
}

bool parseHexBytes(const char *text, uint8_t *out, uint8_t length) {
  if (strlen(text) != static_cast<size_t>(length) * 2) {
    return false;
  }

  for (uint8_t i = 0; i < length; ++i) {
    const int high = hexNibble(text[i * 2]);
    const int low = hexNibble(text[i * 2 + 1]);
    if (high < 0 || low < 0) {
      return false;
    }
    out[i] = static_cast<uint8_t>((high << 4) | low);
  }

  return true;
}

bool parseSecretHex(const char *text, uint8_t *out) {
  return parseHexBytes(text, out, KEY_LENGTH);
}

void printHexByte(uint8_t value) {
  const char hex[] = "0123456789abcdef";
  Serial.print(hex[value >> 4]);
  Serial.print(hex[value & 0x0F]);
}

void computeChallengeResponse(const uint8_t *challenge, uint8_t challengeLength,
                              uint8_t *response) {
  uint8_t tempHash[SHA256_DIGEST_LENGTH];

  hash.reset();
  hash.update(i_key_pad, 64);
  hash.update(challenge, challengeLength);
  hash.finalize(tempHash, sizeof(tempHash));

  hash.reset();
  hash.update(o_key_pad, 64);
  hash.update(tempHash, sizeof(tempHash));
  hash.finalize(response, SHA256_DIGEST_LENGTH);
}

bool parseProvisionArgs(char *args, uint8_t *newKey, uint32_t *newTimestep) {
  char *secretHex = strtok(args, " ");
  char *timestepText = strtok(nullptr, " ");
  char *extra = strtok(nullptr, " ");

  if (secretHex == nullptr || timestepText == nullptr || extra != nullptr) {
    return false;
  }
  if (!parseSecretHex(secretHex, newKey)) {
    return false;
  }

  char *end = nullptr;
  const unsigned long parsed = strtoul(timestepText, &end, 10);
  if (end == timestepText || *end != '\0' || parsed == 0 || parsed > 3600UL) {
    return false;
  }

  *newTimestep = static_cast<uint32_t>(parsed);
  return true;
}

void printRTCState() {
  uint16_t counterSnapshot;
  uint8_t statusSnapshot;
  uint8_t intFlagsSnapshot;
  uint32_t overflowSnapshot;

  pollRTCState();
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    counterSnapshot = rtcCountSnapshot;
    statusSnapshot = rtcStatusSnapshot;
    intFlagsSnapshot = rtcIntFlagsSnapshot;
    overflowSnapshot = totalSeconds;
  }

  Serial.print("OK RTC RAW=");
  Serial.print(getRTCRawSeconds());
  Serial.print(" ELAPSED=");
  Serial.print(getRTCSeconds());
  Serial.print(" CNT=");
  Serial.print(counterSnapshot);
  Serial.print(" OVF=");
  Serial.print(overflowSnapshot);
  Serial.print(" STATUS=");
  Serial.print(statusSnapshot);
  Serial.print(" FLAGS=");
  Serial.print(intFlagsSnapshot);
  Serial.print(" CLK=");
  Serial.println(rtcUsingExternalCrystal ? "EXT" : "INT");
}

bool requireResetModeForMutation() {
  if (resetModeActive) {
    return true;
  }

  sendProtocolError("RESET_MODE_REQUIRED", "Enter reset mode first");
  return false;
}

void processUARTCommand(char *line) {
  if (line[0] == '\0') {
    return;
  }

  if (strcmp(line, "HELLO") == 0) {
    Serial.print("OK HELLO TOKEN ");
    Serial.println(TOKEN_FIRMWARE_VERSION);
    return;
  }

  if (strcmp(line, "STATUS") == 0) {
    Serial.print("OK STATUS STEP=");
    Serial.print(activeTimestep);
    Serial.print(" ELAPSED=");
    Serial.print(getRTCSeconds());
    Serial.print(" PROVISIONED=");
    Serial.println(isProvisioned() ? "1" : "0");
    return;
  }

  if (strcmp(line, "READ_RTC") == 0) {
    printRTCState();
    return;
  }

  if (strcmp(line, "RESET_ARM") == 0) {
    armResetModeEntry();
    Serial.println("OK RESET_ARM");
    return;
  }

  if (strncmp(line, "CHALLENGE ", 10) == 0) {
    uint8_t challenge[CHALLENGE_LENGTH];
    uint8_t response[SHA256_DIGEST_LENGTH];
    if (!parseHexBytes(line + 10, challenge, CHALLENGE_LENGTH)) {
      sendProtocolError("BAD_ARGS", "Expected CHALLENGE <32_HEX_NONCE>");
      return;
    }

    computeChallengeResponse(challenge, CHALLENGE_LENGTH, response);
    Serial.print("OK CHALLENGE ");
    for (uint8_t i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
      printHexByte(response[i]);
    }
    Serial.print(" PROVISIONED=");
    Serial.println(isProvisioned() ? "1" : "0");
    return;
  }

  if (strcmp(line, "RESET_TIME") == 0) {
    if (!requireResetModeForMutation()) {
      return;
    }
    resetElapsedTime();
    setDisplayFeedback("TIMER RESET");
    Serial.println("OK RESET_TIME");
    return;
  }

  if (strcmp(line, "UNREGISTER") == 0) {
    if (!requireResetModeForMutation()) {
      return;
    }
    clearActiveProfile();
    setDisplayFeedback("UNREGISTERED");
    Serial.println("OK UNREGISTER");
    return;
  }

  if (strncmp(line, "PROVISION ", 10) == 0) {
    if (!requireResetModeForMutation()) {
      return;
    }
    uint8_t newKey[KEY_LENGTH];
    uint32_t newTimestep = DEFAULT_TOTP_TIMESTEP_SECONDS;
    if (!parseProvisionArgs(line + 10, newKey, &newTimestep)) {
      sendProtocolError("BAD_ARGS", "Expected PROVISION <40_HEX_SECRET> <TIMESTEP>");
      return;
    }

    storeProvisioning(newKey, newTimestep, true);
    setDisplayFeedback("REGISTERED");
    Serial.println("OK PROVISION");
    return;
  }

  if (strncmp(line, "RESET_ALL ", 10) == 0) {
    if (!requireResetModeForMutation()) {
      return;
    }
    uint8_t newKey[KEY_LENGTH];
    uint32_t newTimestep = DEFAULT_TOTP_TIMESTEP_SECONDS;
    if (!parseProvisionArgs(line + 10, newKey, &newTimestep)) {
      sendProtocolError("BAD_ARGS", "Expected RESET_ALL <40_HEX_SECRET> <TIMESTEP>");
      return;
    }

    resetElapsedTime();
    storeProvisioning(newKey, newTimestep, true);
    setDisplayFeedback("REGISTERED");
    Serial.println("OK RESET_ALL");
    return;
  }

  sendProtocolError("UNKNOWN", "Unsupported command");
}

bool handleUARTCommands() {
  bool processedCommand = false;

  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());

    if (incoming == '\r') {
      continue;
    }

    if (incoming == '\n') {
      uartLineBuffer[uartLineLength] = '\0';
      processUARTCommand(uartLineBuffer);
      uartLineLength = 0;
      processedCommand = true;
      continue;
    }

    if (uartLineLength >= sizeof(uartLineBuffer) - 1) {
      uartLineLength = 0;
      sendProtocolError("LINE_TOO_LONG", "Command line too long");
      processedCommand = true;
      continue;
    }

    uartLineBuffer[uartLineLength++] = incoming;
  }

  return processedCommand;
}

void enterSleep() {
  set_sleep_mode(SLEEP_MODE_STANDBY);
  sleep_enable();
  sleep_cpu();
  sleep_disable();
}

void setup() {
  setupLcdPowerGate();
  beginDisplay();
  displayMessage("RTC source:", "waiting for EXT");

  beginSerial();
  Serial.println("RTC source: waiting for external crystal");

  setupRTC();

  configureWakeButton();

  loadProvisioningFromEEPROM();
  prepareHMACPads();

  Serial.print("RTC source: ");
  Serial.println(rtcUsingExternalCrystal ? "external 32.768kHz crystal"
                                         : "internal 32kHz clock");
  displayMessage("RTC source:",
                 rtcUsingExternalCrystal ? "external crystal" : "internal clock");
  shortBusyDelay();
  clearDisplay();
  prepareLowPowerSleep();
  sei();
}

void runResetMode() {
  beginSerial();
  beginDisplay();
  setDisplayFeedback("RESET MODE");
  resetModeActive = true;
  buttonPressed = false;

  bool readyForExitPress = !buttonIsDown();
  bool trackingExitPress = false;
  uint32_t exitPressStartedMs = 0;
  uint32_t nextRefreshMs = 0;

  while (true) {
    beginSerial();
    pollRTCState();
    if (handleUARTCommands()) {
      extendUARTAdminWindow();
    }

    const bool pressEvent = consumeButtonPress();
    const bool buttonDown = buttonIsDown();
    if (!readyForExitPress) {
      if (!buttonDown) {
        readyForExitPress = true;
      }
      buttonPressed = false;
    } else if (!trackingExitPress &&
               ((pressEvent && buttonDown) ||
                (!pressEvent && buttonDown && acceptButtonDownAsPressStart()))) {
      trackingExitPress = true;
      exitPressStartedMs = millis();
    } else if (trackingExitPress) {
      if (!buttonDown) {
        trackingExitPress = false;
      } else if ((millis() - exitPressStartedMs) >= RESET_MODE_LONG_PRESS_MS) {
        break;
      }
    }

    const uint32_t now = millis();
    if (static_cast<int32_t>(now - nextRefreshMs) >= 0) {
      displayResetMode();
      nextRefreshMs = now + RESET_MODE_REFRESH_MS;
    }

    delay(10);
  }

  clearDisplay();
  shutdownDisplay();
  resetModeActive = false;
  buttonPressed = false;
  displayFeedback[0] = '\0';
}

void loop() {
  beginSerial();
  pollRTCState();
  if (handleUARTCommands()) {
    extendUARTAdminWindow();
  }

  if (consumeButtonPress()) {
    beginDisplay();
    displayActiveProfile();
    buttonPressed = false;
    uint32_t displayUntil = getRTCRawSeconds() + DISPLAY_WINDOW_SECONDS;
    bool readyForDisplayPress = !buttonIsDown();
    bool trackingDisplayPress = false;
    uint32_t displayPressStartedMs = 0;
    uint32_t nextRefreshMs = millis() + RESET_MODE_REFRESH_MS;

    while (static_cast<int32_t>(displayUntil - getRTCRawSeconds()) > 0) {
      pollRTCState();
      if (handleUARTCommands()) {
        extendUARTAdminWindow();
      }

      const bool pressEvent = consumeButtonPress();
      const bool buttonDown = buttonIsDown();
      if (!readyForDisplayPress) {
        if (!buttonDown) {
          readyForDisplayPress = true;
        }
        buttonPressed = false;
      } else if (!trackingDisplayPress) {
        if (pressEvent && !buttonDown) {
          cycleToNextProfile();
          displayActiveProfile();
          displayUntil = getRTCRawSeconds() + DISPLAY_WINDOW_SECONDS;
          nextRefreshMs = millis() + RESET_MODE_REFRESH_MS;
          continue;
        }
        if ((pressEvent && buttonDown) ||
            (!pressEvent && buttonDown && acceptButtonDownAsPressStart())) {
          trackingDisplayPress = true;
          displayPressStartedMs = millis();
        }
      } else if (trackingDisplayPress) {
        if (!buttonDown) {
          trackingDisplayPress = false;
          cycleToNextProfile();
          displayActiveProfile();
          displayUntil = getRTCRawSeconds() + DISPLAY_WINDOW_SECONDS;
          nextRefreshMs = millis() + RESET_MODE_REFRESH_MS;
          continue;
        }
        if ((millis() - displayPressStartedMs) >= RESET_MODE_LONG_PRESS_MS) {
          if (resetModeEntryArmed()) {
            runResetMode();
            return;
          }
          trackingDisplayPress = false;
          readyForDisplayPress = false;
          buttonPressed = false;
        }
      }

      const uint32_t now = millis();
      if (static_cast<int32_t>(now - nextRefreshMs) >= 0) {
        displayActiveProfile();
        nextRefreshMs = now + RESET_MODE_REFRESH_MS;
      }

      delay(10);
    }

    clearDisplay();
    shutdownDisplay();
  }

  if (uartAdminWindowActive()) {
    delay(10);
    return;
  }

  prepareLowPowerSleep();
  enterSleep();
}
