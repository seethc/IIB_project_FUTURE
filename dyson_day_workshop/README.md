# High School OTP Display Workshop

This folder is a self-contained workshop pack for a 30 minute Arduino IDE activity.

Students use either an ATtiny1616 or an Arduino Nano ESP32 with an SPI SSD1306 128x64 OLED display. They start by flashing a name to the display, then show a seconds counter, then finish with a simple uptime-based OTP demo.

## Files

- `workshop_notebook.md` - student-facing ATtiny1616 notebook and live workflow.
- `workshop_notebook_nano_esp32.md` - student-facing Arduino Nano ESP32 notebook and live workflow.
- `instructor_notes.md` - school computer setup, board-specific setup, timing plan, and troubleshooting notes.
- `01_display_name/` - first display sketch.
- `02_seconds_counter/` - display plus `millis()` sketch.
- `03_otp_final/` - final OTP demo sketch with a provided helper.

## Important

The final sketch is a teaching demo. It uses seconds since power-up, so it is not a real authenticator token. A real TOTP device needs a trusted clock or RTC and careful secret handling.
