# Build a Tiny OTP Display

Today you will program an ATtiny1616 microcontroller and wire it to a small 4-pin MIDAS OLED display. By the end, your circuit will show a six-digit code when it powers up.

## What You Have

- ATtiny1616 microcontroller
- 4-pin MIDAS OLED display with `VDD`, `GND`, `SCL`, and `SDA`
- USB programmer
- Breadboard and jumper wires
- Arduino IDE with the ATtiny board package and libraries already installed

## Wiring

Power everything from the same voltage rail. Use 3.3 V, DO NOT USE 5 V.

All grounds must connect together.

| OLED pin | Connects to ATtiny1616 | 20-pin SOIC chip pin | What it does |
| --- | --- | --- | --- |
| `VDD` | `VDD` | 1 | Display power |
| `GND` | `GND` | 20 | Shared ground |
| `SCL` | `PB0 / SCL` | 11 | Display clock |
| `SDA` | `PB1 / SDA` | 10 | Display data |

Programmer wiring:

| Programmer pin | Connects to ATtiny1616 |
| --- | --- |
| `UPDI` | `PA0 / RESET / UPDI`, chip pin 16 |
| `VCC` or `VTG` | Same power rail as ATtiny |
| `GND` | Shared ground |

Bare adapter check before powering:

| ATtiny signal | 20-pin chip pin, if your adapter preserves chip pin order | Your adapter label |
| --- | --- | --- |
| `VDD` | 1 | |
| `PB1 / SDA` | 10 | |
| `PB0 / SCL` | 11 | |
| `PA0 / RESET / UPDI` | 16 | |
| `GND` | 20 | |

If your adapter has different labels, use the adapter sheet from your instructor.

## Arduino IDE Setup

Use these settings:

- Board package: `megaTinyCore`
- Board: `ATtiny1616`
- Programmer: `jtag2updi`
- Port: the COM port for your programmer

To upload, use `Sketch > Upload Using Programmer`.

## Step 1: Put Your Name on the Screen

Open `01_display_name/01_display_name.ino`.

Find this line:

```cpp
const char STUDENT_NAME[] = "YOUR NAME";
```

Change it to your name. Keep the quotation marks.

Upload using the programmer. Your display should show your name and `ATtiny1616`.

If the screen is upside down, add this line after `display.begin();`:

```cpp
display.setFlipMode(1);
```

## Step 2: Make the Chip Count Seconds

Open `02_seconds_counter/02_seconds_counter.ino`.

This sketch uses:

```cpp
millis()
```

`millis()` is a timer built into Arduino. It tells us how many milliseconds have passed since the chip powered on.

Upload the sketch. The display should count upward once per second.

Try changing this line:

```cpp
const char STUDENT_NAME[] = "YOUR NAME";
```

You now have a tiny program that remembers a number, updates it, and redraws the screen.

## Step 3: Show an OTP Code

Open `03_otp_final/03_otp_final.ino`.

This folder has two files:

- `03_otp_final.ino` is the sketch you edit.
- `otp_helper.h` contains the crypto helper. You can read it, but you do not need to change it.

The important line is:

```cpp
uint32_t code = generateOtpCode(secondsNow);
```

The helper turns time into a six-digit code. The sketch then draws that code on the OLED.

Upload the sketch. You should see:

- A six-digit code
- Your name
- A countdown until the next code

Turn the power off and back on. A code appears immediately because the chip starts running from `setup()`.

## What Is Happening?

An OTP is a one-time password. A real time-based OTP works like this:

1. The device and server both know the same secret.
2. They both know the current time.
3. They both run the same crypto recipe.
4. They get the same six-digit code for a short time window.

In this workshop, the chip uses seconds since power-up instead of real clock time. That makes it great for learning, but not secure for real accounts.

## Debug Checklist

Blank display:

- Is `GND` connected between the OLED, ATtiny, and programmer?
- Is OLED `VDD` connected to the correct voltage?
- Are `SCL` and `SDA` swapped?
- Is OLED `SCL` on `PB0`, chip pin 11?
- Is OLED `SDA` on `PB1`, chip pin 10?
- Did the upload actually finish?

Upload error:

- Did you choose `Upload Using Programmer`?
- Is the programmer set to `jtag2updi`?
- Is the COM port correct?
- Is the UPDI wire on `PA0 / RESET / UPDI`, chip pin 16?
- Does the programmer voltage match the ATtiny voltage?

Weird or mirrored display:

- Try adding `display.setFlipMode(1);` after `display.begin();`.

## Challenge Ideas

- Change the name text.
- Change the OTP refresh period from 10 seconds to 30 seconds in `otp_helper.h`.
- Change the screen labels.
- Show a row of `*` characters as a countdown bar.
