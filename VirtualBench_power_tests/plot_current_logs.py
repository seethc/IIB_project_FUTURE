#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = DATA_DIR / "plots"

TITLE_BY_FILE = {
    "current_log_20260326_154908.csv": "sleep_only.ino with LCD unplugged halfway through",
    "current_log_20260326_155546.csv": "sleep_with_overflow (PER = 19 so overflows every 20 ticks or 5s) no LCD",
    "current_log_20260326_155840.csv": "sleep_with_overflow (PER = 19 so overflows every 20 ticks or 5s) with LCD unplugged halfway through",
    "current_log_20260326_160309.csv": "sleep_with_overflow (PER = 79 so overflows every 80 ticks or 20s) no LCD",
    "current_log_20260326_161021.csv": "sleep_with_overflow (PER = 79 so overflows every 80 ticks or 20s) no? WITH? LCD",
    "current_log_20260326_161249.csv": "sleep_with_overflow (PER = 79 so overflows every 80 ticks or 20s) with LCD unplugged halfway through",
    "current_log_20260326_162059.csv": "crypto_only before update no LCD",
    "current_log_20260326_163114.csv": "crypto_only after update no LCD",
    "current_log_20260326_163304.csv": "crypto_only after update with LCD unplugged halfway through",
    "current_log_20260326_164214.csv": "crypto_display (window = 5s) with LCD",
    "current_log_20260326_164330.csv": "crypto_display (window = 5s) with LCD  unplugged halfway through",
    "current_log_20260326_164452.csv": "crypto_display (window = 5s) no LCD",
    "current_log_20260326_164816.csv": "display_numbers_only (every 5s) with LCD",
    "current_log_20260326_164925.csv": "display_numbers_only (every 5s) with LCD unplugged halfway through",
    "current_log_20260326_165031.csv": "display_numbers_only (every 5s) no LCD",
    "current_log_20260326_165234.csv": "display_text_shapes (every 5s) with LCD",
    "current_log_20260326_165342.csv": "display_text_shapes (every 5s) with LCD unplugged halfway through",
    "current_log_20260326_165445.csv": "display_text_shapes (every 5s) no LCD",
    "current_log_20260327_135509.csv": "display only???",
    "current_log_20260327_145558.csv": "ATtiny1616 code sleep for 20s then turned on for 30s generating codes (no LCD)",
    "current_log_20260327_150040.csv": "ATtiny1616 code sleep for 20s then turned on for 30s generating codes (with LCD)",
    "current_log_20260327_152546.csv": "display only (pin 5 wired to GND via 2.2uF cap)",
    "current_log_20260327_153454.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 1 (we changed code to calculate crypto once and then turn off, leaving only display functions on for 30s) 3.0V",
    "current_log_20260327_153601.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 2 3.0V",
    "current_log_20260327_153710.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 3 3.0V",
    "current_log_20260327_160831.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 1 2.6V (lowest voltage before it stops working)",
    "current_log_20260327_161048.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 2 2.6V",
    "current_log_20260327_161223.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 3 2.6V",
    "current_log_20260327_161838.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 1 3.3V (highest voltage of fresh CR2032)",
    "current_log_20260327_162050.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 2 3.3V",
    "current_log_20260327_162203.csv": "ATtiny1616 code (sleep for 20s then turned on for 30s generating 1 code (with LCD) test 3 3.3V",
    "current_log_20260327_163848.csv": "sleep_with_overflow (PER = 79 so overflows every 80 ticks or 20s) no LCD test 2",
    "current_log_20260327_164210.csv": "sleep_with_overflow (PER = 79 so overflows every 80 ticks or 20s) with LCD unplugged halfway through test 2",
    "current_log_20260327_164320.csv": "sleep_with_overflow (PER = 79 so overflows every 80 ticks or 20s) with LCD test 1? 2?",
    "current_log_20260327_164829.csv": "new main.cpp with LCD no button press",
    "current_log_20260327_164940.csv": "new main.cpp with LCD unplugged halfway through no button press",
    "current_log_20260327_165042.csv": "new main.cpp no LCD no button press",
    "current_log_20260327_165304.csv": "new main.cpp with LCD button press at 20s",
    "current_log_20260327_165416.csv": "new main.cpp with LCD unplugged halfway through button press at 20s",
    "current_log_20260327_165610.csv": "new main.cpp no LCD button press at 20s test 1",
    "current_log_20260327_165718.csv": "new main.cpp no LCD button press at 20s (and at 30s) test 2",
    "current_log_20260519_153539.csv": "test (main.cpp sleep + probe plugged in)",
    "current_log_20260519_153831.csv": "main2.cpp sleep test 6",
    "current_log_20260519_154000.csv": "main2.cpp sleep test 7",
    "current_log_20260519_154202.csv": "main2.cpp sleep test 8",
    "current_log_20260519_154421.csv": "main2.cpp button press 20s",
    "current_log_20260519_154529.csv": "main2.cpp button press 20s test 2",
    "current_log_20260519_154644.csv": "main2.cpp button press 20s test 3",
    "current_log_20260519_154757.csv": "main2.cpp sleep test 9",
    "current_log_20260519_154909.csv": "main2.cpp sleep test 10",
    "current_log_20260519_155027.csv": "main2.cpp button press 20s test 4",
    "current_log_20260519_155145.csv": "main2.cpp button press 20s test 5",
    "current_log_20260519_155516.csv": "no power - noise floor",
    "current_log_20260519_155645.csv": "no power - noise floor test 2",
    "current_log_20260519_155752.csv": "no power - noise floor test 3",
    "current_log_20260519_155949.csv": "no power, 3V turned on at 30s (sleep_only.cpp loaded)",
    "current_log_20260519_160647.csv": "no power, 3V turned on at 30s (main2.cpp loaded)",
    "current_log_20260519_160800.csv": "no power, 3V turned on at 30s (main2.cpp loaded) test 2",
    "current_log_20260519_160912.csv": "no power, 3V turned on at 30s (main2.cpp loaded) test 3",
    "current_log_20260519_161023.csv": "main2.cpp button press 20s test 6",
    "current_log_20260519_161133.csv": "main2.cpp sleep test 1",
    "current_log_20260519_161243.csv": "main2.cpp sleep test 2",
    "current_log_20260519_161421.csv": "main2.cpp sleep test 3",
    "current_log_20260519_161751.csv": "main2.cpp button press 20s test 7",
    "current_log_20260519_161902.csv": "main2.cpp button press 20s test 8",
    "current_log_20260519_162331.csv": "main2.cpp button press at 10s (it reset, did not compute code)",
    "current_log_20260519_162459.csv": "main2.cpp button press at 10s (it reset), button press at 20s (for code)",
    "current_log_20260519_162630.csv": "main2.cpp button press 10s (didn't reset this time)",
    "current_log_20260519_162949.csv": "main2.cpp sleep test 4",
    "current_log_20260519_163054.csv": "main2.cpp sleep test 5",
    "current_log_20260519_164520.csv": "main2.cpp button press 20s test 9",
    "current_log_20260519_164609.csv": "main2.cpp button press 20s test 10",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot VirtualBench current logs and save each plot as a PNG."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to save the PNG files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--mapped-only",
        action="store_true",
        help="Plot only CSVs that have a provided title mapping.",
    )
    return parser.parse_args()


def load_csv_series(csv_path: Path) -> tuple[list[float], list[float]]:
    times: list[float] = []
    currents: list[float] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{csv_path.name} is missing a CSV header row")

        expected_columns = {"elapsed_seconds", "current_amps"}
        actual_columns = {column.strip() for column in reader.fieldnames if column}
        if actual_columns != expected_columns:
            raise ValueError(
                f"{csv_path.name} has columns {sorted(actual_columns)} but expected "
                f"{sorted(expected_columns)}"
            )

        for row in reader:
            times.append(float(row["elapsed_seconds"]))
            currents.append(float(row["current_amps"]))

    if not times:
        raise ValueError(f"{csv_path.name} contains no data rows")

    return times, currents


def get_pyplot(backend: str | None = None):
    import matplotlib

    if backend is not None:
        matplotlib.use(backend)

    import matplotlib.pyplot as plt

    return plt


def plot_current_log(csv_path: Path, title: str, output_dir: Path, plt) -> Path:
    times, currents = load_csv_series(csv_path)

    fig, ax = plt.subplots(figsize=(15, 6), dpi=150)
    ax.plot(times, currents, color="tab:blue", linewidth=1.0)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Current (A)")
    ax.grid(True, alpha=0.3)
    ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
    fig.suptitle(title, fontsize=10, wrap=True)
    fig.tight_layout(rect=(0, 0, 1, 0.94))

    output_path = output_dir / f"{csv_path.stem}.png"
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    plt = get_pyplot("Agg")

    all_csvs = sorted(DATA_DIR.glob("current_log_*.csv"))
    missing_from_disk = [
        csv_name for csv_name in sorted(TITLE_BY_FILE) if not (DATA_DIR / csv_name).exists()
    ]
    plotted_paths: list[Path] = []
    skipped_unmatched: list[str] = []

    titles_to_plot: dict[str, str] = {}
    for csv_path in all_csvs:
        if args.mapped_only and csv_path.name not in TITLE_BY_FILE:
            continue
        titles_to_plot[csv_path.name] = TITLE_BY_FILE.get(csv_path.name, csv_path.stem)

    for csv_name, title in sorted(titles_to_plot.items()):
        csv_path = DATA_DIR / csv_name
        output_path = plot_current_log(csv_path, title, output_dir, plt)
        plotted_paths.append(output_path)
        print(f"Saved {output_path}")

    skipped_unmatched = [
        csv_path.name
        for csv_path in all_csvs
        if csv_path.name not in TITLE_BY_FILE
    ]

    print()
    print(f"Plotted {len(plotted_paths)} CSV files into {output_dir}")

    if missing_from_disk:
        print("Missing CSV files referenced in the title mapping:")
        for csv_name in missing_from_disk:
            print(f"  {csv_name}")

    if skipped_unmatched and args.mapped_only:
        print("Skipped CSV files with no provided title mapping:")
        for csv_name in skipped_unmatched:
            print(f"  {csv_name}")
        print("Run without --mapped-only to plot those using their filename stems as titles.")
    elif skipped_unmatched:
        print("Used filename stems as plot titles for CSV files with no provided title mapping:")
        for csv_name in skipped_unmatched:
            print(f"  {csv_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
