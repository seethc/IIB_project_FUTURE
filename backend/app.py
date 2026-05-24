import csv
import time
from datetime import datetime, timezone

from totp_utils import DEFAULT_TIMESTEP_SECONDS, generate_totp, get_rtc_timestamp


SECRET_KEY = b"12345678901234567890"
CSV_FILENAME = "totp_log.csv"


def main():
    print("Initializing...")

    start_timestamp = get_rtc_timestamp()
    if start_timestamp == 0:
        print("Failed to read RTC. Check wiring.")
        return

    with open(CSV_FILENAME, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["SYS UTC (INTERNET)", "RTC TIME", "TOTP CODE", "ELAPSED (s)"])

        print("-" * 75)
        print(
            f"{'SYS UTC (INTERNET)':<20} | {'RTC TIME':<10} | "
            f"{'TOTP CODE':<10} | {'ELAPSED (s)':<15}"
        )
        print("-" * 75)
        print(f"Logging data to {CSV_FILENAME}... Press Ctrl+C to stop.")

        last_processed_time = -1

        try:
            while True:
                current_timestamp = get_rtc_timestamp()
                if current_timestamp != last_processed_time:
                    elapsed_seconds = current_timestamp - start_timestamp
                    totp_code = generate_totp(
                        SECRET_KEY, elapsed_seconds, DEFAULT_TIMESTEP_SECONDS
                    )

                    rtc_str = datetime.fromtimestamp(
                        current_timestamp, timezone.utc
                    ).strftime("%H:%M:%S")
                    system_utc_now = datetime.now(timezone.utc).strftime(
                        "%H:%M:%S.%f"
                    )[:-3]

                    print(
                        f"{system_utc_now:<20} | {rtc_str:<10} | "
                        f"{totp_code:06d}    | {elapsed_seconds:<15}"
                    )
                    writer.writerow(
                        [system_utc_now, rtc_str, f"{totp_code:06d}", elapsed_seconds]
                    )
                    file.flush()

                    last_processed_time = current_timestamp

                time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nStopped logging. File saved.")


if __name__ == "__main__":
    main()
