#include <Arduino.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <Crypto.h>
#include <SHA1.h>
#include <string.h>
#include <avr/sleep.h>
#include <avr/interrupt.h>

// --- PINS (ATtiny1616) ---
#define PIN_CLK  PIN_PA3
#define PIN_MOSI PIN_PA1
#define PIN_CS   PIN_PA4
#define PIN_DC   PIN_PA7
#define PIN_RST  PIN_PA6
#define PIN_BUTTON PIN_PA2

// --- DISPLAY ---
U8G2_ST7305_200X200_1_4W_SW_SPI u8g2(U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

// --- TOTP CONFIG ---
const uint8_t secretKey[] = "12345678901234567890";
const uint32_t timestep = 1;

// --- GLOBALS ---
SHA1 hash;
uint8_t i_key_pad[64];
uint8_t o_key_pad[64];
volatile bool buttonPressed = false;

// --- TIME TRACKING ---
volatile uint32_t totalSeconds = 0;

// --- RTC OVERFLOW INTERRUPT ---
ISR(RTC_CNT_vect) {
  totalSeconds += 64;
  RTC.INTFLAGS = RTC_OVF_bm; // Clear overflow flag
}

// --- RTC SETUP ---
void setupRTC() {
  while (RTC.STATUS > 0);
  
  // Select 32.768kHz Internal Ultra Low-Power Oscillator
  RTC.CLKSEL = RTC_CLKSEL_INT32K_gc;
  
  // Enable overflow interrupt
  RTC.INTCTRL = RTC_OVF_bm;
  
  // Enable RTC with DIV32 prescaler and RUNSTDBY
  // DIV32: 32768 / 32 = 1024 Hz
  // RUNSTDBY: Keeps RTC running during standby sleep
  RTC.CTRLA = RTC_PRESCALER_DIV32_gc | RTC_RTCEN_bm | RTC_RUNSTDBY_bm;
  
  while (RTC.STATUS & RTC_CTRLABUSY_bm);
}

// --- GET TIME FROM RTC ---
uint32_t getRTCSeconds() {
  // Read current RTC count
  uint16_t currentCount = RTC.CNT;
  
  // Current seconds = total overflow seconds + current count
  return totalSeconds + (currentCount / 1024);
}

// --- HMAC PREPARATION ---
void prepareHMACPads() {
  memset(i_key_pad, 0x36, 64);
  memset(o_key_pad, 0x5C, 64);

  for (int i = 0; i < sizeof(secretKey) - 1; i++) {
    i_key_pad[i] ^= secretKey[i];
    o_key_pad[i] ^= secretKey[i];
  }
}

// --- TOTP GENERATION ---
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

// --- DISPLAY TOTP CODE ---
void displayCode(uint32_t code) {
  char text[7];
  sprintf(text, "%06lu", code);

  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_logisoso42_tn);
    
    int textWidth = u8g2.getStrWidth(text);
    int x = (200 - textWidth) / 2;
    int y = 125;
    
    u8g2.drawStr(x, y, text);
  } while (u8g2.nextPage());
}

// --- CLEAR DISPLAY ---
void clearDisplay() {
  u8g2.firstPage();
  do {
    // Empty page = blank screen
  } while (u8g2.nextPage());
}

// --- BUTTON INTERRUPT ---
void buttonISR() {
  buttonPressed = true;
}

// --- ENTER SLEEP MODE ---
void enterSleep() {
  // Use STANDBY mode instead of PWR_DOWN so RTC keeps running
  set_sleep_mode(SLEEP_MODE_STANDBY);
  sleep_enable();
  sleep_cpu();
  sleep_disable();
}

// --- SETUP ---
void setup() {
  // Enable interrupts globally
  sei();
  
  // Setup RTC for continuous timekeeping
  setupRTC();
  
  // Button setup
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BUTTON), buttonISR, FALLING);
  
  // Display setup
  u8g2.begin();
  u8g2.setContrast(0x90);
  
  // TOTP setup
  prepareHMACPads();
  
  // Clear display initially
  clearDisplay();
}

// --- MAIN LOOP ---
void loop() {
  if (buttonPressed) {
    buttonPressed = false;
    
    // 1. Mark start time
    uint32_t startLoopTime = getRTCSeconds();
    
    // 2. Loop until 30 seconds have passed
    while ( (getRTCSeconds() - startLoopTime) < 30 ) {
      
      // Get current time & generate code
      uint32_t currentSeconds = getRTCSeconds();
      uint32_t code = generateTOTP(currentSeconds);
      
      // Update Display
      displayCode(code);
      
      // Wait approx 1 second
      delay(1000);
    }
    
    clearDisplay();
  }
  
  // Enter sleep mode (RTC keeps counting)
  enterSleep();
}