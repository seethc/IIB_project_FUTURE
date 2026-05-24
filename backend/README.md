## Token Manager Backend

Run from the repository root:

```powershell
python -m pip install -r backend/requirements.txt
$env:HARDWARE_MOCK="1"  # optional laptop dry run without hardware
python backend/server.py
```

Open `http://localhost:5000`.

Useful environment variables:

- `UART_PORT`: token UART port, for example `COM4` or `/dev/ttyUSB0`.
- `UPLOAD_PORT`: SerialUPDI upload port.
- `ADAPTER_CONTROL_PORT`: adapter MCU command port.
- `ADAPTER_BAUD`: adapter MCU command baud rate. Default is `115200`.
- `ADAPTER_REQUIRE_ACK=1`: require `OK MODE UPDI`/`OK MODE UART` replies when
  the backend sends automatic mode-switch commands. By default these commands
  are best-effort so flashing/UART flows can still continue with adapters that
  do not echo a confirmation.
- `ADAPTER_OPEN_DELAY_SECONDS`: delay after opening the adapter serial port
  before sending the mode command. Default is `1.0`.
- `ARDUINO_CLI_EXE`: Arduino CLI executable path. On Windows the bundled
  Arduino IDE CLI is detected automatically.
- `ARDUINO_FQBN`: Arduino board target. Default is
  `megaTinyCore:megaavr:atxy6` with the visible Arduino IDE settings used for
  the ATtiny3216 token: 20 MHz internal clock, EEPROM retained, BOD disabled,
  UPDI pin, default millis/printf/PWM/Wire/interrupt settings.
- `ARDUINO_PROGRAMMER`: programmer ID. Default is `serialupdi57k`, matching
  "SerialUPDI - SLOW: 57600 baud".
- `ARDUINO_VERIFY_UPLOAD=1`: ask Arduino CLI to verify after upload. Disabled
  by default to match the normal Arduino IDE upload flow.
- `UPDI_SETTLE_SECONDS`: delay after switching the adapter to UPDI before the
  upload command opens the port. Default is `1.5`.
- `HARDWARE_MOCK=1`: mock serial/provisioning responses for UI testing.

The web app can flash `src/main2.cpp` or `src/rtc_sync_test_elapsed.cpp`. It
copies the selected file into a temporary Arduino sketch under `.arduino-build/`,
then runs Arduino CLI with megaTinyCore and SerialUPDI. The backend also points
Microchip/pymcuprog logging at a workspace-local console-only config so web
uploads do not fail trying to write logs under AppData. Select the UPDI upload
port before flashing, and select the token UART port before reading status,
reading the raw RTC state, or provisioning a new key.
