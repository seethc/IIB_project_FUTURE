#include <Arduino.h>
#include <EEPROM.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <Crypto.h>
#include <SHA1.h>
#include <string.h>
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

// DISPLAY
U8G2_ST7305_200X200_1_4W_SW_SPI u8g2(
    U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

// TOTP CONFIG
constexpr uint8_t KEY_LENGTH = 20;
constexpr uint8_t KEY_EEPROM_ADDR = 0;
constexpr uint8_t PROVISIONING_MARKER = 0xAA;
constexpr uint32_t timestep = 5;
const uint8_t defaultSecretKey[KEY_LENGTH] = {
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0'};

SHA1 hash;
uint8_t activeSecretKey[KEY_LENGTH];
uint8_t i_key_pad[64];
uint8_t o_key_pad[64];
volatile bool buttonPressed = false;

// TIME TRACKING
constexpr uint32_t RTC_OVERFLOW_SECONDS = 65536UL;
volatile uint32_t totalSeconds = 0;
bool rtcUsingExternalCrystal = false;
volatile uint16_t rtcCountSnapshot = 0;
volatile uint8_t rtcStatusSnapshot = 0;
volatile uint8_t rtcIntFlagsSnapshot = 0;

// RTC OVERFLOW INTERRUPT
ISR(RTC_CNT_vect) {
  totalSeconds += RTC_OVERFLOW_SECONDS;
  RTC.INTFLAGS = RTC_OVF_bm;
}

// DISPLAY STATUS MESSAGE
void displayMessage(const char *line1, const char *line2 = nullptr) {
  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_6x12_tf);
    if (line1) {
      int width1 = u8g2.getStrWidth(line1);
      u8g2.drawStr((200 - width1) / 2, 92, line1);
    }
    if (line2) {
      int width2 = u8g2.getStrWidth(line2);
      u8g2.drawStr((200 - width2) / 2, 112, line2);
    }
  } while (u8g2.nextPage());
}

void pollRTCState() {
  rtcCountSnapshot = RTC.CNT;
  rtcStatusSnapshot = RTC.STATUS;
  rtcIntFlagsSnapshot = RTC.INTFLAGS;
}

// RTC SETUP
void setupRTC() {
  while (RTC.STATUS > 0 || RTC.PITSTATUS > 0) {
  }

  RTC.CTRLA = 0;
  RTC.INTCTRL = 0;
  RTC.INTFLAGS = RTC_OVF_bm;
  RTC.PITINTCTRL = 0;
  RTC.PITCTRLA = 0;
  RTC.PITINTFLAGS = RTC_PI_bm;

  // External 32.768 kHz watch crystal on PB3/PB2 (TOSC1/TOSC2).
  _PROTECTED_WRITE(CLKCTRL.XOSC32KCTRLA,
                   CLKCTRL_RUNSTDBY_bm | CLKCTRL_CSUT_64K_gc);
  _PROTECTED_WRITE(CLKCTRL.XOSC32KCTRLA,
                   CLKCTRL_ENABLE_bm | CLKCTRL_RUNSTDBY_bm |
                       CLKCTRL_CSUT_64K_gc);

  // Request the RTC clock domain from the external crystal.
  RTC.CLKSEL = RTC_CLKSEL_TOSC32K_gc;
  RTC.PER = 0xFFFF;
  while (RTC.STATUS > 0) {
  }

  RTC.INTCTRL = RTC_OVF_bm;
  RTC.CTRLA = RTC_PRESCALER_DIV32768_gc | RTC_RTCEN_bm | RTC_RUNSTDBY_bm;
  while (RTC.STATUS & RTC_CTRLABUSY_bm) {
  }
  while ((CLKCTRL.MCLKSTATUS & CLKCTRL_XOSC32KS_bm) == 0) {
  }

  rtcUsingExternalCrystal = true;
  pollRTCState();
}

// GET TIME FROM RTC
uint32_t getRTCSeconds() {
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

void waitForRTCSeconds(uint32_t seconds) {
  uint32_t startSeconds = getRTCSeconds();
  while ((getRTCSeconds() - startSeconds) < seconds) {
    pollRTCState();
  }
}

void shortBusyDelay() {
  for (uint8_t i = 0; i < 40; ++i) {
    pollRTCState();
    delayMicroseconds(2500);
  }
}

// SECRET STORAGE
bool isSecretKeyUninitialized() {
  for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
    if (EEPROM.read(KEY_EEPROM_ADDR + i) != 0xFF) {
      return false;
    }
  }
  return true;
}

void writeSecretKeyToEEPROM(const uint8_t *key) {
  for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
    EEPROM.update(KEY_EEPROM_ADDR + i, key[i]);
  }
}

void loadSecretKeyFromEEPROM() {
  if (isSecretKeyUninitialized()) {
    writeSecretKeyToEEPROM(defaultSecretKey);
  }

  for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
    activeSecretKey[i] = EEPROM.read(KEY_EEPROM_ADDR + i);
  }
}

// HMAC PREPARATION
void prepareHMACPads() {
  memset(i_key_pad, 0x36, sizeof(i_key_pad));
  memset(o_key_pad, 0x5C, sizeof(o_key_pad));

  for (uint8_t i = 0; i < KEY_LENGTH; ++i) {
    i_key_pad[i] ^= activeSecretKey[i];
    o_key_pad[i] ^= activeSecretKey[i];
  }
}

// TOTP GENERATION
uint32_t generateTOTP(uint32_t time) {
  uint64_t counter = time / timestep;

  uint8_t counterBytes[8];
  for (int i = 7; i >= 0; --i) {
    counterBytes[i] = counter & 0xFF;
    counter >>= 8;
  }

  uint8_t tempHash[20];
  hash.reset();
  hash.update(i_key_pad, 64);
  hash.update(counterBytes, 8);
  hash.finalize(tempHash, sizeof(tempHash));

  uint8_t finalHash[20];
  hash.reset();
  hash.update(o_key_pad, 64);
  hash.update(tempHash, sizeof(tempHash));
  hash.finalize(finalHash, sizeof(finalHash));

  int offset = finalHash[19] & 0x0F;

  uint32_t binary =
      ((uint32_t)(finalHash[offset] & 0x7F) << 24) |
      ((uint32_t)(finalHash[offset + 1] & 0xFF) << 16) |
      ((uint32_t)(finalHash[offset + 2] & 0xFF) << 8) |
      ((uint32_t)(finalHash[offset + 3] & 0xFF));

  return binary % 1000000;
}

// DISPLAY TOTP CODE
void displayCode(uint32_t code, uint32_t currentSeconds) {
  char text[7];
  char debugLine[24];
  char counterLine[24];
  char statusLine[24];
  const uint8_t *codeFont = u8g2_font_logisoso24_tn;
  const uint8_t *candidateFonts[] = {
      u8g2_font_logisoso62_tn, u8g2_font_logisoso58_tn,
      u8g2_font_logisoso54_tn, u8g2_font_logisoso50_tn,
      u8g2_font_logisoso46_tn, u8g2_font_logisoso42_tn,
      u8g2_font_logisoso38_tn, u8g2_font_logisoso34_tn,
      u8g2_font_logisoso32_tn};
  uint16_t counterSnapshot;
  uint8_t statusSnapshot;
  uint8_t intFlagsSnapshot;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    counterSnapshot = rtcCountSnapshot;
    statusSnapshot = rtcStatusSnapshot;
    intFlagsSnapshot = rtcIntFlagsSnapshot;
  }

  sprintf(text, "%06lu", code);
  sprintf(debugLine,
          "CLK:%s SEC:%lu",
          rtcUsingExternalCrystal ? "EXT" : "INT",
          currentSeconds);
  sprintf(counterLine, "CNT:%u", (unsigned int)counterSnapshot);
  sprintf(statusLine, "ST:%u FL:%u", (unsigned int)statusSnapshot,
          (unsigned int)intFlagsSnapshot);

  constexpr int displayWidth = 200;
  constexpr int displayHeight = 200;
  constexpr int codeTop = 50;
  constexpr int codeBottomPadding = 6;
  constexpr int codeHorizontalPadding = 4;
  constexpr int codeAreaHeight = displayHeight - codeTop - codeBottomPadding;

  for (const uint8_t *candidateFont : candidateFonts) {
    u8g2.setFont(candidateFont);
    int width = u8g2.getStrWidth(text);
    int height = u8g2.getAscent() - u8g2.getDescent();

    if (width <= (displayWidth - 2 * codeHorizontalPadding) &&
        height <= codeAreaHeight) {
      codeFont = candidateFont;
      break;
    }
  }

  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_6x12_tf);
    u8g2.drawStr(8, 14, debugLine);
    u8g2.drawStr(8, 28, counterLine);
    u8g2.drawStr(8, 42, statusLine);

    u8g2.setFont(codeFont);

    int textWidth = u8g2.getStrWidth(text);
    int codeHeight = u8g2.getAscent() - u8g2.getDescent();
    int x = (displayWidth - textWidth) / 2;
    int y = codeTop + ((codeAreaHeight - codeHeight) / 2) + u8g2.getAscent();

    u8g2.drawStr(x, y, text);
  } while (u8g2.nextPage());
}

// CLEAR DISPLAY
void clearDisplay() {
  u8g2.firstPage();
  do {
  } while (u8g2.nextPage());
}

// BUTTON INTERRUPT
void buttonISR() {
  buttonPressed = true;
}

// UART PROVISIONING
bool tryReadProvisionedKey(uint8_t *newKey) {
  if (Serial.available() <= 0) {
    return false;
  }

  int firstByte = Serial.read();
  if (firstByte != PROVISIONING_MARKER) {
    return false;
  }

  uint8_t bytesRead = 0;
  uint32_t timeoutStart = getRTCSeconds();

  while (bytesRead < KEY_LENGTH && (getRTCSeconds() - timeoutStart) < 2) {
    if (Serial.available() > 0) {
      newKey[bytesRead++] = Serial.read();
    }
  }

  return bytesRead == KEY_LENGTH;
}

void handleUARTProvisioning() {
  uint8_t newKey[KEY_LENGTH];

  if (!tryReadProvisionedKey(newKey)) {
    return;
  }

  writeSecretKeyToEEPROM(newKey);
  memcpy(activeSecretKey, newKey, KEY_LENGTH);
  prepareHMACPads();

  Serial.println("Secret key updated");
}

// ENTER SLEEP MODE
void enterSleep() {
  set_sleep_mode(SLEEP_MODE_STANDBY);
  sleep_enable();
  sleep_cpu();
  sleep_disable();
}

// SETUP
void setup() {
  sei();

  u8g2.begin();
  u8g2.setContrast(0x90);
  displayMessage("RTC source:", "waiting for EXT");

  Serial.swap(1);
  Serial.begin(9600, SERIAL_HALF_DUPLEX);
  PORTA.PIN1CTRL |= PORT_PULLUPEN_bm;
  Serial.println("RTC source: waiting for external crystal");

  setupRTC();

  pinMode(PIN_BUTTON, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BUTTON), buttonISR, FALLING);

  loadSecretKeyFromEEPROM();
  prepareHMACPads();

  Serial.println("RTC source: external 32.768kHz crystal");
  displayMessage("RTC source:", "external crystal");
  shortBusyDelay();
  clearDisplay();
}

// MAIN LOOP
void loop() {
  pollRTCState();
  handleUARTProvisioning();

  if (buttonPressed) {
    buttonPressed = false;

    uint32_t startLoopTime = getRTCSeconds();

    while ((getRTCSeconds() - startLoopTime) < 30) {
      pollRTCState();
      handleUARTProvisioning();

      uint32_t currentSeconds = getRTCSeconds();
      uint32_t code = generateTOTP(currentSeconds);

      displayCode(code, currentSeconds);
      shortBusyDelay();
    }

    clearDisplay();
  }

  enterSleep();
}
