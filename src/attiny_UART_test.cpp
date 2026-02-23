#include <Arduino.h>
#include <EEPROM.h>
#include <avr/sleep.h>
#include <avr/interrupt.h>

#define PIN_BUTTON PIN_PA6
#define KEY_EEPROM_ADDR 0
#define KEY_LENGTH 20

volatile bool buttonPressed = false;

void buttonISR() { buttonPressed = true; }

void setup() {
  sei();
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BUTTON), buttonISR, FALLING);

  Serial.swap(1); // Safely routes TX to PA1 and RX to PA2
  Serial.begin(9600);
  
  delay(2000);
  Serial.println("ATtiny alive");

  // Print whatever key is currently in EEPROM
  Serial.print("Current key: ");
  for (int i = 0; i < KEY_LENGTH; i++) {
    Serial.write(EEPROM.read(KEY_EEPROM_ADDR + i));
  }
  Serial.println();
}

void loop() {
  // Listen for incoming key over UART
  // Expect exactly 20 bytes
  if (Serial.available() >= KEY_LENGTH) {
    uint8_t newKey[KEY_LENGTH];
    for (int i = 0; i < KEY_LENGTH; i++) {
      newKey[i] = Serial.read();
    }

    // Write to EEPROM
    for (int i = 0; i < KEY_LENGTH; i++) {
      EEPROM.update(KEY_EEPROM_ADDR + i, newKey[i]);
    }

    // Confirm back
    Serial.print("Received new key: ");
    for (int i = 0; i < KEY_LENGTH; i++) {
      Serial.write(newKey[i]);
    }
    Serial.println();
  }

  // When button is pressed, print the key currently stored in EEPROM
  if (buttonPressed) {
    buttonPressed = false;
    Serial.print("Button pressed. Current key: ");
    for (int i = 0; i < KEY_LENGTH; i++) {
      Serial.write(EEPROM.read(KEY_EEPROM_ADDR + i));
    }
    Serial.println();
  }
}