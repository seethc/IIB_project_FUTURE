# Dyson Day OTP Workshop: Instructor Setup and Delivery Guide

## Required Software

Arduino IDE 2.3.4 must already be installed on each school computer.

Additional required components:

- megaTinyCore board package for ATtiny1616 workshops.
- Arduino ESP32 Boards package for Arduino Nano ESP32 workshops.
- U8g2 display library for the SPI SSD1306 OLED.
- Crypto library by Rhys Weatherley / Arduino CryptoLibs for SHA1 support in the OTP demo.
- USB serial driver for the jtag2updi programmer when using ATtiny1616 hardware.

## ATtiny1616 Boards Manager URL

This Boards Manager URL is required only for the ATtiny1616 version:

```text
https://drazzy.com/package_drazzy.com_index.json
```

The Arduino Nano ESP32 version does not need this URL.

## Reference URLs

```text
https://github.com/SpenceKonde/megaTinyCore
https://github.com/SpenceKonde/megaTinyCore/blob/master/Installation.md
https://github.com/SpenceKonde/megaTinyCore/blob/master/megaavr/extras/ATtiny_x16.md
https://github.com/olikraus/u8g2
https://github.com/olikraus/u8g2/wiki/u8g2setupcpp
https://github.com/rweather/arduinolibs
https://docs.arduino.cc/hardware/nano-esp32/
https://docs.arduino.cc/resources/pinouts/ABX00083-full-pinout.pdf
```

## Install Workshop Project Files

Copy the full `dyson_day_workshop` folder onto each school computer before the session.

Recommended location:

```text
%USERPROFILE%\Documents\Arduino\dyson_day_workshop
```

The folder must keep this structure:

```text
dyson_day_workshop/
  01_display_name/
    01_display_name.ino
  02_seconds_counter/
    02_seconds_counter.ino
  03_otp_final/
    03_otp_final.ino
    otp_helper.h
  instructor_notes.md
  workshop_notebook.md
  workshop_notebook_nano_esp32.md
```

Arduino IDE expects each `.ino` file to stay inside a folder with the same name as the sketch.

## Install megaTinyCore

Use this section only for the ATtiny1616 version.

1. Open Arduino IDE 2.3.4.
2. Open `File > Preferences`.
3. Add the required Boards Manager URL:

```text
https://drazzy.com/package_drazzy.com_index.json
```

4. Click `OK`.
5. Close and reopen Arduino IDE.
6. Open `Tools > Board > Boards Manager`.
7. Set the Boards Manager filter to `All`.
8. Search for:

```text
megaTinyCore
```

9. Install `megaTinyCore by Spence Konde`.
10. Wait for installation to finish.

## Install Arduino Nano ESP32 Board Package

Use this section only for the Arduino Nano ESP32 version.

1. Open Arduino IDE 2.3.4.
2. Open `Tools > Board > Boards Manager`.
3. Search for:

```text
Arduino ESP32 Boards
```

4. Install `Arduino ESP32 Boards` by Arduino.
5. Wait for installation to finish.

## Select ATtiny1616 Settings

The exact menu wording varies slightly between megaTinyCore versions.

Set the Arduino IDE `Tools` menu as follows:

- Board family: megaTinyCore / tinyAVR 0/1/2-series.
- Chip or board: `ATtiny1616`.
- Clock: `16 MHz internal` or `20 MHz internal`.
- Programmer: `jtag2updi`.
- Port: COM port assigned to the programmer.

Upload method:

```text
Sketch > Upload Using Programmer
```

Do not use the standard upload button unless the machine has been configured so that the button performs programmer uploads.

## Select Arduino Nano ESP32 Settings

Set the Arduino IDE `Tools` menu as follows:

- Board package: `Arduino ESP32 Boards`.
- Board: `Arduino Nano ESP32`.
- Port: USB port assigned to the Nano ESP32.

Upload method:

```text
Sketch > Upload
```

The Nano ESP32 programs directly over USB-C. No UPDI programmer is used.

## Arduino Nano ESP32 OLED Wiring

| OLED pin | Arduino Nano ESP32 pin |
| --- | --- |
| `VCC` | `3V3` |
| `GND` | `GND` |
| `SCK` or `CLK` | `D13` |
| `MOSI`, `SDA`, or `DIN` | `D11` |
| `CS` | `D10` |
| `DC` | `D9` |
| `RST` or `RES` | `D8` |

The Nano ESP32 uploads over USB-C. Do not connect a UPDI programmer.

## Install U8g2

1. Open `Tools > Manage Libraries`.
2. Search for:

```text
U8g2
```

3. Install:

```text
U8g2 by oliver
```

Validation:

1. Open:

```text
dyson_day_workshop/01_display_name/01_display_name.ino
```

2. Run `Sketch > Verify/Compile`.
3. `U8x8lib.h: No such file or directory` means U8g2 is missing for the active Windows/Arduino user account.

## Install Crypto

1. Open `Tools > Manage Libraries`.
2. Search for:

```text
Crypto
```

3. Install the Rhys Weatherley library, commonly listed as:

```text
Crypto
```

or copy the `Crypto` library folder from the workshop USB drive into the Arduino libraries folder.

The installed library must provide:

```text
SHA1.h
```

Validation:

1. Open:

```text
dyson_day_workshop/03_otp_final/03_otp_final.ino
```

2. Run `Sketch > Verify/Compile`.
3. `SHA1.h: No such file or directory` means the Crypto library is missing or the wrong library is installed.

## Programmer Setup

Use this section only for the ATtiny1616 version.

1. Connect the jtag2updi programmer by USB.
2. Open `Tools > Port`.
3. Select the COM port that appears when the programmer is connected.
4. Open `Tools > Programmer`.
5. Select:

```text
jtag2updi
```

## Preflight Validation

Complete this checklist before students arrive:

- Arduino IDE 2.3.4 opens.
- U8g2 is installed.
- Crypto library with `SHA1.h` is installed.
- Correct COM port is selected.
- All three sketches compile.
- The OLED shows the test name.

ATtiny1616-specific checks:

- megaTinyCore is installed.
- `ATtiny1616` is selected.
- Programmer is set to `jtag2updi`.
- `01_display_name` uploads with `Sketch > Upload Using Programmer`.

Arduino Nano ESP32-specific checks:

- `Arduino ESP32 Boards` is installed.
- `Arduino Nano ESP32` is selected.
- `01_display_name` uploads with `Sketch > Upload`.

Recommended hardware validation:

1. Wire one known-good ATtiny1616 and OLED kit.
2. Open:

```text
dyson_day_workshop/01_display_name/01_display_name.ino
```

3. Set:

```cpp
const char STUDENT_NAME[] = "TEST";
```

4. Run `Sketch > Upload Using Programmer` for ATtiny1616, or `Sketch > Upload` for Arduino Nano ESP32.
5. Confirm the OLED displays `TEST`.

## Before Students Arrive

- Compile all three sketches on one computer configured like the student computers.
- Upload `01_display_name` to one complete hardware kit.
- Confirm that the OLED module works at the selected voltage.
- Print or project the correct pinout for the selected board.
- Label each ATtiny1616 programmer with its expected COM port if possible.
- For Arduino Nano ESP32 kits, confirm each USB-C cable supports data.
- Keep one known-good wired kit available for comparison during troubleshooting.

## 30 Minute Flow

| Time | Activity |
| --- | --- |
| 0:00-0:03 | Show the finished OTP display and explain the goal. |
| 0:03-0:08 | Walk through power, ground, upload wiring, and OLED wiring for the selected board. |
| 0:08-0:13 | Students upload `01_display_name` and customize their name. |
| 0:13-0:18 | Students upload `02_seconds_counter`; explain `setup()`, `loop()`, and `millis()`. |
| 0:18-0:25 | Students upload `03_otp_final`; explain time window plus shared secret at a high level. |
| 0:25-0:30 | Debug, power-cycle test, and quick extension challenge. |

## Teaching Script Notes

Microcontroller:

- "This is a computer small enough to live inside another object."
- "It runs one program over and over."
- "`setup()` happens once; `loop()` repeats."

Display:

- "SPI is a simple way for the chip to talk to another chip."
- "Clock says when data is ready; MOSI carries the bits."
- "`CS`, `DC`, and `RST` are control lines for this display."

OTP:

- "A code is useful only if both sides can produce the same code."
- "The secret is shared, the time changes, and the code changes."
- "Today this demo uses uptime so no extra clock chip is needed."

Security caveat:

- Do not describe the final sketch as secure.
- Say: "This is the shape of an authenticator, not a production authenticator."
- Real deployments need a secure secret, accurate time, replay protection, and server-side verification.

## Troubleshooting

Blank screen:

- Check common ground first.
- Check OLED power and voltage.
- Confirm `SCK` and `MOSI` are not swapped.
- Confirm `CS`, `DC`, and `RST` are connected to the pins listed in the selected student notebook.
- Confirm the display is SSD1306 128x64 SPI. SH1106 or I2C modules need different code.

Upload failure:

- Use `Sketch > Upload Using Programmer`.
- Check programmer selection and COM port.
- Check UPDI to `PA0 / UPDI`.
- Check that programmer and target share ground.
- Disconnect OLED temporarily if power is unstable.

Compile failure:

- Missing `U8x8lib.h`: install U8g2.
- Missing `SHA1.h`: install Crypto by Rhys Weatherley / Arduino CryptoLibs.
- Wrong board selected: select `ATtiny1616` for the ATtiny version or `Arduino Nano ESP32` for the Nano version.

## Deliberate Fault Check

Before the workshop, prepare one bad wiring example and practice diagnosing it:

- Missing shared ground: upload may fail or display may stay blank.
- Swapped `SCK` and `MOSI`: upload works, display stays blank.
- Wrong COM port: upload fails before programming.
- Wrong board package: compile fails with unknown pin names.

## Optional Extensions

- Change `OTP_STEP_SECONDS` from 10 to 30.
- Add a countdown bar to the OTP screen.
- Compare two devices with the same secret powered on at the same time.
- Discuss what extra hardware is needed to keep codes correct after power loss.
