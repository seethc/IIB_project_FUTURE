#include <SoftwareSerial.h>

// Define the pins for SoftwareSerial
// Uno Pin 10 (RX) connects to ATtiny TX (PA1)
// Uno Pin 11 (TX) connects to ATtiny RX (PA2)
const int rxPin = 10;
const int txPin = 11;

SoftwareSerial attinySerial(rxPin, txPin);

void setup() {
  // 1. Start communication with your PC's Serial Monitor
  Serial.begin(9600);
  
  // 2. Start communication with the ATtiny1616
  attinySerial.begin(9600);
  
  Serial.println("--- Arduino Uno Bridge Ready ---");
  Serial.println("Send your 20-byte key via the Serial Monitor.");
}

void loop() {
  // Listen for messages from the ATtiny and print them to the PC
  if (attinySerial.available()) {
    char incomingChar = attinySerial.read();
    Serial.write(incomingChar); 
  }

  // Listen for keys typed on the PC and pass them directly to the ATtiny
  if (Serial.available()) {
    char outgoingChar = Serial.read();
    attinySerial.write(outgoingChar);
  }
}