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
#define PIN_BUTTON PIN_PA2  // Button pin (change as needed)

// --- DISPLAY ---
U8G2_ST7305_200X200_1_4W_SW_SPI u8g2(U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

// --- TOTP CONFIG ---
const uint8_t secretKey[] = "12345678901234567890";
const uint32_t timestep = 30;  // 30-second TOTP window

// --- GLOBALS ---
SHA1 hash;
uint8_t i_key_pad[64];
uint8_t o_key_pad[64];
volatile bool buttonPressed = false;
uint32_t uptimeSeconds = 0;  // Track time even across sleep

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
      ((finalHash[offset] & 0x7F) << 24) |
      ((finalHash[offset + 1] & 0xFF) << 16) |
      ((finalHash[offset + 2] & 0xFF) << 8) |
      (finalHash[offset + 3] & 0xFF);

  return binary % 1000000; // 6 digits
}

// --- DISPLAY TOTP CODE ---
void displayCode(uint32_t code) {
  char text[7];
  sprintf(text, "%06lu", code);  // Format as 6-digit string with leading zeros

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
  set_sleep_mode(SLEEP_MODE_PWR_DOWN);  // Deepest sleep
  sleep_enable();
  sleep_cpu();
  sleep_disable();  // Execute after waking
}

// --- SETUP ---
void setup() {
  // Enable interrupts globally
  sei();
  
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
    buttonPressed = false;  // Reset flag
    
    // STEP 1: Generate TOTP (cryptography FIRST)
    uptimeSeconds += millis() / 1000;  // Update time tracker
    uint32_t code = generateTOTP(uptimeSeconds);
    
    // STEP 2: Display code (display SECOND)
    displayCode(code);
    
    // STEP 3: Show for 10 seconds
    delay(10000);
    
    // STEP 4: Clear display and sleep
    clearDisplay();
  }
  
  // Enter sleep mode (button will wake)
  enterSleep();
}