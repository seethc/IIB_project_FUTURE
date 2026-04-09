#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


CURRENT_RESOLUTION_A = 1e-8
CURRENT_HALF_ERROR_A = CURRENT_RESOLUTION_A / 2.0
CURRENT_STANDARD_UNCERTAINTY_A = CURRENT_HALF_ERROR_A / math.sqrt(3.0)
TIME_RESOLUTION_S = 0.2
TIME_HALF_ERROR_S = TIME_RESOLUTION_S / 2.0
TIME_STANDARD_UNCERTAINTY_S = TIME_HALF_ERROR_S / math.sqrt(3.0)
CURRENT_DECIMAL_STEP = Decimal("0.00000001")
FILENAME_PATTERN = re.compile(r"(current_log_\d{8}_\d{6}\.csv)")
OUTPUT_HEADER = [
    "File",
    "Total raw charge (mC)",
    "Worst-case Min (mC)",
    "Worst-case Max (mC)",
    "Statistical Min (mC)",
    "Statistical Max (mC)",
    "Current Floor (A)",
    "Area above floor (mC)",
    "Worst-case Min (mC)",
    "Worst-case Max (mC)",
    "Statistical Min (mC)",
    "Statistical Max (mC)",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill the FUTURE power spreadsheet from current log CSVs."
    )
    parser.add_argument(
        "--sheet",
        type=Path,
        required=True,
        help="Path to the input spreadsheet CSV.",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory containing current_log_*.csv files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the completed spreadsheet CSV.",
    )
    return parser.parse_args()


def quantize_current_for_error(current: float) -> float:
    return float(
        Decimal(str(current)).quantize(CURRENT_DECIMAL_STEP, rounding=ROUND_HALF_UP)
    )


def load_csv_series(csv_path: Path) -> tuple[list[float], list[float]]:
    times: list[float] = []
    currents: list[float] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            times.append(float(row["elapsed_seconds"]))
            currents.append(float(row["current_amps"]))

    if not times:
        raise ValueError(f"{csv_path.name} contains no data")

    return times, currents


def integrate_trapezoid(times: list[float], values: list[float]) -> float:
    area = 0.0
    for t1, t2, v1, v2 in zip(times, times[1:], values, values[1:]):
        dt = t2 - t1
        if dt < 0:
            raise ValueError("Time values must be non-decreasing")
        area += 0.5 * (v1 + v2) * dt
    return area


def integrate_relative_to_floor(
    times: list[float], currents: list[float], floor: float
) -> tuple[float, float]:
    signed_area = 0.0
    positive_area = 0.0

    for t1, t2, current1, current2 in zip(times, times[1:], currents, currents[1:]):
        dt = t2 - t1
        if dt < 0:
            raise ValueError("Time values must be non-decreasing")

        y1 = current1 - floor
        y2 = current2 - floor
        signed_area += 0.5 * (y1 + y2) * dt

        if y1 >= 0.0 and y2 >= 0.0:
            positive_area += 0.5 * (y1 + y2) * dt
            continue

        if y1 <= 0.0 and y2 <= 0.0:
            continue

        crossing_fraction = y1 / (y1 - y2)
        crossing_dt = crossing_fraction * dt

        if y1 > 0.0:
            positive_area += 0.5 * y1 * crossing_dt
        else:
            positive_area += 0.5 * y2 * (dt - crossing_dt)

    return signed_area, positive_area


def trapezoid_x_sensitivity_coefficients(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)

    coefficients = [0.0] * len(values)
    coefficients[0] = -0.5 * (values[0] + values[1])
    for index in range(1, len(values) - 1):
        coefficients[index] = 0.5 * (values[index - 1] - values[index + 1])
    coefficients[-1] = 0.5 * (values[-2] + values[-1])
    return coefficients


def trapezoid_y_sensitivity_coefficients(times: list[float]) -> list[float]:
    if len(times) < 2:
        return [0.0] * len(times)

    coefficients = [0.0] * len(times)
    coefficients[0] = 0.5 * (times[1] - times[0])
    for index in range(1, len(times) - 1):
        coefficients[index] = 0.5 * (times[index + 1] - times[index - 1])
    coefficients[-1] = 0.5 * (times[-1] - times[-2])
    return coefficients


def trapezoid_statistical_uncertainty(
    times: list[float],
    values: list[float],
    sigma_y: float,
    sigma_x: float,
) -> float:
    y_coefficients = trapezoid_y_sensitivity_coefficients(times)
    x_coefficients = trapezoid_x_sensitivity_coefficients(values)
    variance = sum((coefficient * sigma_y) ** 2 for coefficient in y_coefficients)
    variance += sum((coefficient * sigma_x) ** 2 for coefficient in x_coefficients)
    return math.sqrt(variance)


def trapezoid_time_uncertainty_from_point_error(
    values: list[float], half_time_error: float = TIME_HALF_ERROR_S
) -> float:
    coefficients = trapezoid_x_sensitivity_coefficients(values)
    return half_time_error * sum(abs(coefficient) for coefficient in coefficients)


def calculate_area_error_bounds(
    times: list[float], currents: list[float], floor: float
) -> dict[str, tuple[float, float]]:
    rounded_currents = [quantize_current_for_error(current) for current in currents]
    currents_min = [current - CURRENT_HALF_ERROR_A for current in rounded_currents]
    currents_max = [current + CURRENT_HALF_ERROR_A for current in rounded_currents]

    raw_min_current = integrate_trapezoid(times, currents_min)
    raw_max_current = integrate_trapezoid(times, currents_max)
    raw_time_uncertainty = trapezoid_time_uncertainty_from_point_error(rounded_currents)

    _, above_min_current = integrate_relative_to_floor(times, currents_min, floor)
    _, above_max_current = integrate_relative_to_floor(times, currents_max, floor)
    shifted_rounded_currents = [current - floor for current in rounded_currents]
    clipped_shifted_currents = [
        max(current_minus_floor, 0.0)
        for current_minus_floor in shifted_rounded_currents
    ]
    area_above_time_uncertainty = trapezoid_time_uncertainty_from_point_error(
        clipped_shifted_currents
    )

    raw_min = raw_min_current - raw_time_uncertainty
    raw_max = raw_max_current + raw_time_uncertainty
    above_min = max(0.0, above_min_current - area_above_time_uncertainty)
    above_max = above_max_current + area_above_time_uncertainty

    return {
        "total_charge": (raw_min, raw_max),
        "area_above": (above_min, above_max),
    }


def calculate_area_statistical_uncertainties(
    times: list[float], currents: list[float], floor: float
) -> dict[str, float]:
    rounded_currents = [quantize_current_for_error(current) for current in currents]
    shifted_rounded_currents = [current - floor for current in rounded_currents]
    clipped_shifted_currents = [
        max(current_minus_floor, 0.0)
        for current_minus_floor in shifted_rounded_currents
    ]

    return {
        "total_charge": trapezoid_statistical_uncertainty(
            times,
            rounded_currents,
            CURRENT_STANDARD_UNCERTAINTY_A,
            TIME_STANDARD_UNCERTAINTY_S,
        ),
        "area_above": trapezoid_statistical_uncertainty(
            times,
            clipped_shifted_currents,
            CURRENT_STANDARD_UNCERTAINTY_A,
            TIME_STANDARD_UNCERTAINTY_S,
        ),
    }


def robust_floor_from_window(
    times: list[float], currents: list[float], start_s: float = 50.0, end_s: float = 60.0
) -> float:
    window_currents = [
        current
        for time, current in zip(times, currents)
        if start_s <= time <= end_s
    ]
    if not window_currents:
        raise ValueError(f"No samples found in {start_s:.1f}-{end_s:.1f} s window")

    median_current = statistics.median(window_currents)
    absolute_deviations = [abs(current - median_current) for current in window_currents]
    mad = statistics.median(absolute_deviations)
    spike_threshold = median_current + max(6.0 * mad, CURRENT_RESOLUTION_A)
    filtered_currents = [
        current for current in window_currents if current <= spike_threshold
    ]

    # Fallback if the MAD-based upper-spike filter rejects too many points.
    if len(filtered_currents) < max(5, len(window_currents) // 4):
        sorted_currents = sorted(window_currents)
        keep_count = max(5, math.ceil(0.8 * len(sorted_currents)))
        filtered_currents = sorted_currents[:keep_count]

    return sum(filtered_currents) / len(filtered_currents)


def format_mc(value_coulombs: float) -> str:
    return f"{value_coulombs * 1000.0:.6f}"


def format_floor(value_amps: float) -> str:
    return f"{value_amps:.10f}"


def extract_filename(cell_value: str) -> str | None:
    match = FILENAME_PATTERN.search(cell_value)
    if match is None:
        return None
    return match.group(1)


def compute_row_values(logs_dir: Path, filename: str) -> dict[str, str]:
    csv_path = logs_dir / filename
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing log file: {csv_path}")

    times, currents = load_csv_series(csv_path)
    floor = robust_floor_from_window(times, currents)
    total_charge = integrate_trapezoid(times, currents)
    _, area_above_floor = integrate_relative_to_floor(times, currents, floor)
    worst_case_bounds = calculate_area_error_bounds(times, currents, floor)
    statistical_uncertainties = calculate_area_statistical_uncertainties(
        times, currents, floor
    )

    total_sigma = statistical_uncertainties["total_charge"]
    area_sigma = statistical_uncertainties["area_above"]

    total_stat_min = total_charge - total_sigma
    total_stat_max = total_charge + total_sigma
    area_stat_min = max(0.0, area_above_floor - area_sigma)
    area_stat_max = area_above_floor + area_sigma

    return {
        "Total raw charge (mC)": format_mc(total_charge),
        "Worst-case Min (mC)__raw": format_mc(worst_case_bounds["total_charge"][0]),
        "Worst-case Max (mC)__raw": format_mc(worst_case_bounds["total_charge"][1]),
        "Statistical Min (mC)__raw": format_mc(total_stat_min),
        "Statistical Max (mC)__raw": format_mc(total_stat_max),
        "Current Floor (A)": format_floor(floor),
        "Area above floor (mC)": format_mc(area_above_floor),
        "Worst-case Min (mC)__above": format_mc(worst_case_bounds["area_above"][0]),
        "Worst-case Max (mC)__above": format_mc(worst_case_bounds["area_above"][1]),
        "Statistical Min (mC)__above": format_mc(area_stat_min),
        "Statistical Max (mC)__above": format_mc(area_stat_max),
    }


def main() -> int:
    args = parse_args()
    logs_dir = args.logs_dir.resolve()
    sheet_path = args.sheet.resolve()
    output_path = args.output.resolve()

    with sheet_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        raise SystemExit("Spreadsheet CSV is empty")

    header = rows[0]
    if not header or header[0] != "File":
        raise SystemExit(
            f"Unexpected header first cell. Expected 'File', found: {header[0] if header else '<empty>'}"
        )

    updated_rows = [OUTPUT_HEADER]
    updated_count = 0
    skipped_rows: list[str] = []

    for row in rows[1:]:
        padded_row = row + [""] * (len(OUTPUT_HEADER) - len(row))
        filename = extract_filename(padded_row[0])
        if filename is None:
            updated_rows.append(padded_row[: len(OUTPUT_HEADER)])
            skipped_rows.append(padded_row[0])
            continue

        values = compute_row_values(logs_dir, filename)
        padded_row[1] = values["Total raw charge (mC)"]
        padded_row[2] = values["Worst-case Min (mC)__raw"]
        padded_row[3] = values["Worst-case Max (mC)__raw"]
        padded_row[4] = values["Statistical Min (mC)__raw"]
        padded_row[5] = values["Statistical Max (mC)__raw"]
        padded_row[6] = values["Current Floor (A)"]
        padded_row[7] = values["Area above floor (mC)"]
        padded_row[8] = values["Worst-case Min (mC)__above"]
        padded_row[9] = values["Worst-case Max (mC)__above"]
        padded_row[10] = values["Statistical Min (mC)__above"]
        padded_row[11] = values["Statistical Max (mC)__above"]
        updated_rows.append(padded_row[: len(OUTPUT_HEADER)])
        updated_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(updated_rows)

    print(f"Updated {updated_count} rows")
    print(f"Wrote {output_path}")
    if skipped_rows:
        print("Skipped rows with no detectable current log filename:")
        for value in skipped_rows:
            print(f"  {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
