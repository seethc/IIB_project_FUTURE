# Build a Tiny OTP Display: Arduino Nano ESP32

Today you will program an Arduino Nano ESP32 and wire it to a small 4-pin MIDAS OLED display. By the end, your circuit will show a six-digit code when it powers up.

## What You Have

- Arduino Nano ESP32
- 4-pin MIDAS OLED display with `VDD`, `GND`, `SCL`, and `SDA`
- USB-C cable
- Breadboard and jumper wires
- Arduino IDE with the Nano ESP32 board package and libraries already installed

## Wiring

Power everything from the Nano ESP32 3.3 V rail. Do not use 5 V for the OLED.

All grounds must connect together.

| OLED pin | Connects to Arduino Nano ESP32 | What it does |
| --- | --- | --- |
| `VDD` | `3V3` | Display power |
| `GND` | `GND` | Shared ground |
| `SCL` | `A5 / SCL` | Display clock |
| `SDA` | `A4 / SDA` | Display data |

The Nano ESP32 programs directly over USB-C. There is no UPDI programmer wiring for this version.

## Arduino IDE Setup

Use these settings:

- Board package: `Arduino ESP32 Boards`
- Board: `Arduino Nano ESP32`
- Port: the USB port for the Nano ESP32

To upload, use the normal Arduino IDE upload button or `Sketch > Upload`.

## Step 1: Put Your Name on the Screen

Open `01_display_name/01_display_name.ino`.

Find this line:

```cpp
const char STUDENT_NAME[] = "YOUR NAME";
```

Change it to your name. Keep the quotation marks.

Upload the sketch. Your display should show your name and `Nano ESP32`.

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

`millis()` is a timer built into Arduino. It tells us how many milliseconds have passed since the board powered on.

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

Unplug and replug the USB-C cable. A code appears immediately because the board starts running from `setup()`.

## What Is Happening?

An OTP is a one-time password. A real time-based OTP works like this:

1. The device and server both know the same secret.
2. They both know the current time.
3. They both run the same crypto recipe.
4. They get the same six-digit code for a short time window.

In this workshop, the board uses seconds since power-up instead of real clock time. That makes it great for learning, but not secure for real accounts.

## Debug Checklist

Blank display:

- Is OLED `GND` connected to Nano ESP32 `GND`?
- Is OLED `VDD` connected to `3V3`?
- Are `SCL` and `SDA` swapped?
- Is OLED `SCL` on `A5 / SCL`?
- Is OLED `SDA` on `A4 / SDA`?
- Did the upload finish?

Upload error:

- Is the board set to `Arduino Nano ESP32`?
- Is the USB port correct?
- Is the USB cable a data cable, not charge-only?

Weird or mirrored display:

- Try adding `display.setFlipMode(1);` after `display.begin();`.

## Challenge Ideas

- Change the name text.
- Change the OTP refresh period from 10 seconds to 30 seconds in `otp_helper.h`.
- Change the screen labels.
- Show a row of `*` characters as a countdown bar.
