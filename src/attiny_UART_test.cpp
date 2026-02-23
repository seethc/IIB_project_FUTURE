#include <Arduino.h>
#include <EEPROM.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <avr/sleep.h>
#include <avr/interrupt.h>

// --- PINS ---
#define PIN_CLK    PIN_PC0
#define PIN_MOSI   PIN_PC2
#define PIN_CS     PIN_PC3
#define PIN_DC     PIN_PA3
#define PIN_RST    PIN_PA4
#define PIN_BUTTON PIN_PA6

// --- DISPLAY ---
U8G2_ST7305_200X200_1_4W_SW_SPI u8g2(U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

// --- EEPROM ---
#define KEY_EEPROM_ADDR 0
#define KEY_LENGTH 20

volatile bool buttonPressed = false;

void buttonISR() { buttonPressed = true; }

// --- DISPLAY MESSAGE ---
void displayMessage(const char* line1, const char* line2 = nullptr, const char* line3 = nullptr) {
  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_logisoso28_tf);
    if (line1) u8g2.drawStr(0, 30,  line1);
    if (line2) u8g2.drawStr(0, 68,  line2);
    if (line3) u8g2.drawStr(0, 106, line3);
  } while (u8g2.nextPage());
}

void displayKey(const char* label, uint8_t* key) {
  char line1[11]; char line2[11];
  for (int i = 0; i < 10; i++) line1[i] = (key[i]    == 0x00) ? '-' : ((key[i]    >= 32 && key[i]    < 127) ? (char)key[i]    : '.');
  for (int i = 0; i < 10; i++) line2[i] = (key[i+10] == 0x00) ? '-' : ((key[i+10] >= 32 && key[i+10] < 127) ? (char)key[i+10] : '.');
  line1[10] = '\0'; line2[10] = '\0';

  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_logisoso28_tf);
    u8g2.drawStr(0, 30, label);
    u8g2.drawHLine(0, 38, 200);
    u8g2.drawStr(0, 80, line1);
    u8g2.drawStr(0, 118, line2);
  } while (u8g2.nextPage());
}

void setup() {
  sei();
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BUTTON), buttonISR, FALLING);

  // Alternate SPI pins (port C)
  PORTMUX.CTRLB |= PORTMUX_SPI0_bm;

  u8g2.begin();
  u8g2.setContrast(0x90);
  displayMessage("Initialising...");

  Serial.swap(1);
  Serial.begin(9600, SERIAL_HALF_DUPLEX);
  PORTA.PIN1CTRL |= PORT_PULLUPEN_bm;

  if (EEPROM.read(KEY_EEPROM_ADDR) == 0xFF) {
    for (int i = 0; i < KEY_LENGTH; i++) {
      EEPROM.update(KEY_EEPROM_ADDR + i, 0x00);
    }
  }

  delay(2000);
  Serial.print("ATtiny alive\r\n");
  displayMessage("ATtiny alive");
}

void loop() {
  if (Serial.available() > 0) {
    uint8_t firstByte = Serial.read();

    if (firstByte == 0xAA) {
      uint8_t newKey[KEY_LENGTH];
      int bytesRead = 0;
      uint32_t timeout = millis() + 2000;

      while (bytesRead < KEY_LENGTH && millis() < timeout) {
        if (Serial.available() > 0) {
          newKey[bytesRead] = Serial.read();
          bytesRead++;
        }
      }

      if (bytesRead == KEY_LENGTH) {
        for (int i = 0; i < KEY_LENGTH; i++) {
          EEPROM.update(KEY_EEPROM_ADDR + i, newKey[i]);
        }

        Serial.print("Key saved: ");
        for (int i = 0; i < KEY_LENGTH; i++) Serial.write(newKey[i]);
        Serial.print("\r\n");

        displayKey("Key saved:", newKey);

      } else {
        Serial.print("Timeout\r\n");
        displayMessage("Timeout", "Key not received");
      }

    } else {
      Serial.print("Ignored Hex: ");
      Serial.println(firstByte, HEX);
    }
  }

  if (buttonPressed) {
    buttonPressed = false;

    uint8_t storedKey[KEY_LENGTH];
    for (int i = 0; i < KEY_LENGTH; i++) storedKey[i] = EEPROM.read(KEY_EEPROM_ADDR + i);

    Serial.print("Current key: ");
    for (int i = 0; i < KEY_LENGTH; i++) {
      uint8_t val = storedKey[i];
      Serial.write(val == 0x00 ? '-' : val);
    }
    Serial.print("\r\n");

    displayKey("Current key:", storedKey);
  }
}