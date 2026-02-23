#include <SoftwareSerial.h>

#define KEY_LENGTH 20

SoftwareSerial attinySerial(10, 11); // RX=10, TX=11

void setup() {
  Serial.begin(9600);
  attinySerial.begin(9600);
  Serial.println("--- Bridge Ready ---");
}

void loop() {
  if (attinySerial.available()) {
    Serial.write(attinySerial.read());
  }
  if (Serial.available()) {
    String input = Serial.readString();
    Serial.print("Sending key of length: ");
    Serial.println(input.length());
    if (input.length() >= KEY_LENGTH) {
      attinySerial.write(0xAA);
      delay(50);  // increase this from 10 to 50
      for (int i = 0; i < KEY_LENGTH; i++) {
        attinySerial.write((uint8_t)input[i]);
      }
    }
  }
}