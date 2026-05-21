#include <Arduino.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <string.h>
#include <avr/sleep.h>
#include <avr/interrupt.h>
#include <util/atomic.h>

// Low-power elapsed-time RTC test for the ATtiny3216 token board.
// PB0 drives the LCD high-side switch: LOW powers the LCD, HIGH disconnects it.
#define PIN_CLK PIN_PC0
#define PIN_MOSI PIN_PC2
#define PIN_CS PIN_PC3
#define PIN_DC PIN_PA3
#define PIN_RST PIN_PA4
#define PIN_BUTTON PIN_PA6
#define PIN_LCD_POWER_GATE PIN_PB0

#ifndef RTC_TEST_FIRMWARE_VERSION
#define RTC_TEST_FIRMWARE_VERSION "rtc-sync-elapsed-1.0"
#endif

#ifndef UART_ADMIN_WINDOW_SECONDS
#define UART_ADMIN_WINDOW_SECONDS 300UL
#endif

#ifndef RTC_CRYSTAL_STARTUP_TIMEOUT_MS
#define RTC_CRYSTAL_STARTUP_TIMEOUT_MS 2000UL
#endif

U8G2_ST7305_200X200_1_4W_SW_SPI u8g2(
    U8G2_R2, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

constexpr uint16_t DISPLAY_WINDOW_SECONDS = 30;
constexpr uint32_t RTC_OVERFLOW_SECONDS = 65536UL;
constexpr uint16_t LCD_POWER_SETTLE_MS = 20;
constexpr uint16_t DISPLAY_REFRESH_MS = 250;
constexpr uint32_t UART_ADMIN_WINDOW_SECONDS_VALUE = UART_ADMIN_WINDOW_SECONDS;
constexpr uint32_t RTC_CRYSTAL_STARTUP_TIMEOUT_MS_VALUE =
    RTC_CRYSTAL_STARTUP_TIMEOUT_MS;

volatile bool buttonPressed = false;
volatile bool rtcCompareMatched = false;
volatile uint32_t totalSeconds = 0;
volatile uint32_t elapsedOffsetSeconds = 0;
volatile uint16_t rtcCountSnapshot = 0;
volatile uint8_t rtcStatusSnapshot = 0;
volatile uint8_t rtcIntFlagsSnapshot = 0;
bool rtcUsingExternalCrystal = false;
bool lcdPowerEnabled = false;
char uartLineBuffer[96];
uint8_t uartLineLength = 0;
uint32_t uartAdminAwakeUntil = 0;

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

void buttonISR() {
  buttonPressed = true;
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

void drawCentered(const char *text, int16_t y) {
  const int width = u8g2.getStrWidth(text);
  u8g2.drawStr((200 - width) / 2, y, text);
}

void displayMessage(const char *line1, const char *line2 = nullptr) {
  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_6x12_tf);
    if (line1) {
      drawCentered(line1, 92);
    }
    if (line2) {
      drawCentered(line2, 112);
    }
  } while (u8g2.nextPage());
}

void displayElapsed(uint32_t currentSeconds) {
  char secondsText[16];
  char sourceLine[24];
  char counterLine[24];
  const uint8_t *elapsedFont = u8g2_font_logisoso32_tn;
  const uint8_t *candidateFonts[] = {
      u8g2_font_logisoso62_tn, u8g2_font_logisoso58_tn,
      u8g2_font_logisoso54_tn, u8g2_font_logisoso50_tn,
      u8g2_font_logisoso46_tn, u8g2_font_logisoso42_tn,
      u8g2_font_logisoso38_tn, u8g2_font_logisoso34_tn,
      u8g2_font_logisoso32_tn};
  uint16_t counterSnapshot;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    counterSnapshot = rtcCountSnapshot;
  }

  sprintf(secondsText, "%lu", static_cast<unsigned long>(currentSeconds));
  sprintf(sourceLine, "CLK:%s",
          rtcUsingExternalCrystal ? "EXT" : "INT");
  sprintf(counterLine, "CNT:%u", static_cast<unsigned int>(counterSnapshot));

  for (const uint8_t *candidateFont : candidateFonts) {
    u8g2.setFont(candidateFont);
    if (u8g2.getStrWidth(secondsText) <= 190) {
      elapsedFont = candidateFont;
      break;
    }
  }

  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_6x12_tf);
    drawCentered(sourceLine, 18);
    drawCentered(counterLine, 34);
    drawCentered("ELAPSED", 62);

    u8g2.setFont(elapsedFont);
    const int textWidth = u8g2.getStrWidth(secondsText);
    const int textHeight = u8g2.getAscent() - u8g2.getDescent();
    const int x = (200 - textWidth) / 2;
    const int y = 72 + ((92 - textHeight) / 2) + u8g2.getAscent();
    u8g2.drawStr(x, y, secondsText);

    u8g2.setFont(u8g2_font_6x12_tf);
    drawCentered("SECONDS", 184);
  } while (u8g2.nextPage());
}

void clearDisplay() {
  u8g2.firstPage();
  do {
  } while (u8g2.nextPage());
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

uint32_t getRTCSeconds() {
  const uint32_t rawSeconds = getRTCRawSeconds();
  uint32_t offsetSnapshot;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    offsetSnapshot = elapsedOffsetSeconds;
  }

  if (rawSeconds < offsetSnapshot) {
    return 0;
  }
  return rawSeconds - offsetSnapshot;
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

void resetElapsedTime() {
  const uint32_t rawSeconds = getRTCRawSeconds();

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    elapsedOffsetSeconds = rawSeconds;
    rtcCompareMatched = false;
  }

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

void processUARTCommand(char *line) {
  if (line[0] == '\0') {
    return;
  }

  if (strcmp(line, "HELLO") == 0) {
    Serial.print("OK HELLO TOKEN ");
    Serial.println(RTC_TEST_FIRMWARE_VERSION);
    return;
  }

  if (strcmp(line, "STATUS") == 0) {
    Serial.print("OK STATUS STEP=1 ELAPSED=");
    Serial.print(getRTCSeconds());
    Serial.println(" PROVISIONED=0");
    return;
  }

  if (strcmp(line, "READ_RTC") == 0) {
    printRTCState();
    return;
  }

  if (strcmp(line, "RESET_TIME") == 0) {
    resetElapsedTime();
    Serial.println("OK RESET_TIME");
    return;
  }

  if (strncmp(line, "PROVISION ", 10) == 0) {
    Serial.println("OK PROVISION");
    return;
  }

  if (strncmp(line, "RESET_ALL ", 10) == 0) {
    resetElapsedTime();
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
  displayMessage("RTC elapsed", "starting");

  beginSerial();
  Serial.println("RTC elapsed test starting");

  setupRTC();
  configureWakeButton();
  extendUARTAdminWindow();

  displayMessage("RTC source:",
                 rtcUsingExternalCrystal ? "external crystal" : "internal clock");
  Serial.print("RTC source: ");
  Serial.println(rtcUsingExternalCrystal ? "external crystal" : "internal clock");
  shortBusyDelay();
  clearDisplay();
  shutdownDisplay();
  sei();
}

void loop() {
  beginSerial();
  pollRTCState();
  if (handleUARTCommands()) {
    extendUARTAdminWindow();
  }

  if (buttonPressed) {
    buttonPressed = false;

    beginDisplay();
    const uint32_t displayUntil = getRTCSeconds() + DISPLAY_WINDOW_SECONDS;
    uint32_t nextRefreshMs = 0;
    do {
      beginSerial();
      pollRTCState();
      if (handleUARTCommands()) {
        extendUARTAdminWindow();
      }
      const uint32_t now = millis();
      if (static_cast<int32_t>(now - nextRefreshMs) >= 0) {
        displayElapsed(getRTCSeconds());
        nextRefreshMs = now + DISPLAY_REFRESH_MS;
      }
      delay(10);
    } while (!buttonPressed &&
             static_cast<int32_t>(displayUntil - getRTCSeconds()) > 0);

    clearDisplay();
    buttonPressed = false;
    shutdownDisplay();
    extendUARTAdminWindow();
  }

  if (uartAdminWindowActive()) {
    delay(10);
    return;
  }

  prepareLowPowerSleep();
  enterSleep();
}
