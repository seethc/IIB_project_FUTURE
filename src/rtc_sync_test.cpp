#include <Arduino.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <Wire.h>
#include <RTClib.h>
#include <Crypto.h>
#include <SHA1.h>

// --- OLED PINS ---
#define PIN_CLK  PIN_PA4
#define PIN_MOSI PIN_PA5
#define PIN_CS   PIN_PA3
#define PIN_DC   PIN_PA6
#define PIN_RST  PIN_PA7

// Note this is for the 128x64 OLED test display, not the 200x200 ST7305 LCD.
U8G2_SSD1306_128X64_NONAME_F_4W_SW_SPI u8g2(U8G2_R0, PIN_CLK, PIN_MOSI, PIN_CS, PIN_DC, PIN_RST);

// --- RTC ---
RTC_DS3231 rtc;

uint32_t startUnix = 0;
uint32_t lastSec   = 0;

// --- TOTP CONFIG ---
const uint8_t secretKey[] = "12345678901234567890";
const uint32_t timestep   = 30;

// --- HMAC PADS ---
SHA1 sha1hash;
uint8_t i_key_pad[64];
uint8_t o_key_pad[64];

// --- HMAC PREPARATION ---
void prepareHMACPads() {
    memset(i_key_pad, 0x36, 64);
    memset(o_key_pad, 0x5C, 64);

    for (size_t i = 0; i < sizeof(secretKey) - 1; i++) {
        i_key_pad[i] ^= secretKey[i];
        o_key_pad[i] ^= secretKey[i];
    }
}

// --- TOTP GENERATION ---
uint32_t generateTOTP(uint32_t elapsedTime) {
    uint64_t counter = elapsedTime / timestep;

    uint8_t counterBytes[8];
    for (int i = 7; i >= 0; --i) {
        counterBytes[i] = counter & 0xFF;
        counter >>= 8;
    }

    uint8_t tempHash[20];
    sha1hash.reset();
    sha1hash.update(i_key_pad, 64);
    sha1hash.update(counterBytes, 8);
    sha1hash.finalize(tempHash, sizeof(tempHash));

    uint8_t finalHash[20];
    sha1hash.reset();
    sha1hash.update(o_key_pad, 64);
    sha1hash.update(tempHash, sizeof(tempHash));
    sha1hash.finalize(finalHash, sizeof(finalHash));

    int offset = finalHash[19] & 0x0F;

    uint32_t binary =
        ((uint32_t)(finalHash[offset]     & 0x7F) << 24) |
        ((uint32_t)(finalHash[offset + 1] & 0xFF) << 16) |
        ((uint32_t)(finalHash[offset + 2] & 0xFF) << 8)  |
        ((uint32_t)(finalHash[offset + 3] & 0xFF));

    return binary % 1000000;
}

// --- DRAW CENTERED ROW ---
void drawCentered(const char* str, int16_t y) {
    int16_t w = u8g2.getStrWidth(str);
    u8g2.drawStr((128 - w) / 2, y, str);
}

// --- DISPLAY ---
void drawScreen(DateTime now, uint32_t elapsed) {
    // Row 1: 6-digit TOTP code — uses elapsed seconds, matching Pi implementation
    char codeStr[7];
    snprintf(codeStr, sizeof(codeStr), "%06lu", generateTOTP(elapsed));

    // Row 2: HHMMSS (digits only, no colons)
    char timeStr[7];
    snprintf(timeStr, sizeof(timeStr), "%02d%02d%02d",
             now.hour(), now.minute(), now.second());

    // Row 3: elapsed seconds
    char elapsedStr[11];
    snprintf(elapsedStr, sizeof(elapsedStr), "%lu", elapsed);

    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_lubR08_tn);

    drawCentered(codeStr,    18);
    drawCentered(timeStr,    39);
    drawCentered(elapsedStr, 60);

    u8g2.sendBuffer();
}

// --- SETUP ---
void setup() {
    Wire.swap(1);   // PA1=SDA, PA2=SCL
    Wire.begin();

    u8g2.begin();

    if (!rtc.begin()) {
        u8g2.clearBuffer();
        u8g2.setFont(u8g2_font_lubR08_tn);
        drawCentered("000000", 39);
        u8g2.sendBuffer();
        while (true) {}
    }

    prepareHMACPads();

    startUnix = rtc.now().unixtime();
    lastSec   = 0;
}

// --- LOOP ---
void loop() {
    DateTime now     = rtc.now();
    uint32_t elapsed = now.unixtime() - startUnix;

    if (elapsed != lastSec) {
        lastSec = elapsed;
        drawScreen(now, elapsed);
    }

    delay(200);
}