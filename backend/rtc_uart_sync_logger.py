import argparse
import csv
import os
import re
import time
from datetime import datetime, timezone

import serial


DEFAULT_PORT = "/dev/serial0"
DEFAULT_BAUD = 9600
DEFAULT_OUTPUT = "pendant_rtc_sync_log.csv"
DEFAULT_RECONNECT_DELAY_SECONDS = 2.0

FIELD_PATTERN = re.compile(r"([A-Z_]+)=([^\s]+)")


def parse_rtc_line(line):
    if line.startswith("SYNC "):
        fields = dict(FIELD_PATTERN.findall(line))
        return {
            "message_type": "SYNC",
            "event": fields.get("EVENT", ""),
            "raw_seconds": fields.get("RAW", ""),
            "elapsed_seconds": fields.get("ELAPSED", ""),
            "rtc_count": fields.get("CNT", ""),
            "overflow_seconds": fields.get("OVF", ""),
            "clock_source": fields.get("CLK", ""),
        }

    if line.startswith("OK RTC "):
        fields = dict(FIELD_PATTERN.findall(line))
        return {
            "message_type": "READ_RTC",
            "event": "COMMAND",
            "raw_seconds": fields.get("RAW", ""),
            "elapsed_seconds": fields.get("ELAPSED", ""),
            "rtc_count": fields.get("CNT", ""),
            "overflow_seconds": fields.get("OVF", ""),
            "clock_source": fields.get("CLK", ""),
        }

    return None


def open_csv(path):
    file_exists = os.path.exists(path) and os.path.getsize(path) > 0
    csv_file = open(path, mode="a", newline="", encoding="utf-8")
    fieldnames = [
        "unix_time",
        "utc_iso",
        "message_type",
        "event",
        "raw_seconds",
        "elapsed_seconds",
        "rtc_count",
        "overflow_seconds",
        "clock_source",
        "serial_line",
    ]
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

    if not file_exists:
        writer.writeheader()
        csv_file.flush()

    return csv_file, writer


def log_serial_line(line, writer, csv_file):
    unix_time = time.time()
    utc_iso = datetime.fromtimestamp(unix_time, timezone.utc).isoformat()
    parsed = parse_rtc_line(line)

    if parsed is None:
        print(f"[{utc_iso}] ignored: {line}")
        return

    row = {
        "unix_time": f"{unix_time:.6f}",
        "utc_iso": utc_iso,
        "serial_line": line,
        **parsed,
    }
    writer.writerow(row)
    csv_file.flush()

    print(
        f"[{utc_iso}] {parsed['message_type']} "
        f"raw={parsed['raw_seconds']} elapsed={parsed['elapsed_seconds']} "
        f"cnt={parsed['rtc_count']} clk={parsed['clock_source']}"
    )


def read_serial_forever(port, baud, writer, csv_file):
    with serial.Serial(port, baud, timeout=1) as ser:
        print(f"Listening on {port} at {baud} baud")
        ser.reset_input_buffer()

        while True:
            raw_line = ser.readline()
            if not raw_line:
                continue

            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                log_serial_line(line, writer, csv_file)


def log_uart(port, baud, output, reconnect_delay):
    csv_file, writer = open_csv(output)

    try:
        print(f"Logging Pendant RTC sync samples to {output}")
        print("Press the Pendant button to wake it. Press Ctrl+C to stop.")

        while True:
            try:
                read_serial_forever(port, baud, writer, csv_file)
            except serial.SerialException as exc:
                print(
                    f"Serial error on {port}: {exc}. "
                    f"Retrying in {reconnect_delay:g}s..."
                )
                time.sleep(reconnect_delay)
    finally:
        csv_file.close()


def main():
    parser = argparse.ArgumentParser(
        description="Log Pendant RTC counts from the Raspberry Pi UART to CSV."
    )
    parser.add_argument("--port", default=DEFAULT_PORT, help="UART port to read.")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="UART baud rate.")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="CSV file to append samples to.",
    )
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=DEFAULT_RECONNECT_DELAY_SECONDS,
        help="Seconds to wait before reopening the serial port after an error.",
    )
    args = parser.parse_args()

    try:
        log_uart(args.port, args.baud, args.output, args.reconnect_delay)
    except KeyboardInterrupt:
        print("\nStopped logging.")


if __name__ == "__main__":
    main()
