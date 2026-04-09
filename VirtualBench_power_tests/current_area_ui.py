#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import tkinter as tk
from bisect import bisect_left
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from plot_current_logs import DATA_DIR, TITLE_BY_FILE, load_csv_series


CURRENT_RESOLUTION_A = 1e-8
CURRENT_HALF_ERROR_A = CURRENT_RESOLUTION_A / 2.0
CURRENT_STANDARD_UNCERTAINTY_A = CURRENT_HALF_ERROR_A / math.sqrt(3.0)
TIME_RESOLUTION_S = 0.2
TIME_HALF_ERROR_S = TIME_RESOLUTION_S / 2.0
TIME_STANDARD_UNCERTAINTY_S = TIME_HALF_ERROR_S / math.sqrt(3.0)
CURRENT_DECIMAL_STEP = Decimal("0.00000001")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactively set a current floor and integrate a current log."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Optional initial CSV filename to select.",
    )
    parser.add_argument(
        "--floor",
        type=float,
        default=None,
        help="Optional initial current floor in amps.",
    )
    parser.add_argument(
        "--mapped-only",
        action="store_true",
        help="Only list CSVs that have a provided title mapping.",
    )
    return parser.parse_args()


def build_csv_list(mapped_only: bool) -> list[Path]:
    csv_paths = sorted(DATA_DIR.glob("current_log_*.csv"))
    if mapped_only:
        csv_paths = [csv_path for csv_path in csv_paths if csv_path.name in TITLE_BY_FILE]
    return csv_paths


def get_csv_display_label(csv_path: Path, index: int | None = None) -> str:
    annotation = TITLE_BY_FILE.get(csv_path.name)
    index_prefix = f"[{index:02d}] " if index is not None else ""
    if annotation:
        return f"{index_prefix}{annotation} | {csv_path.name}"
    return f"{index_prefix}{csv_path.name}"


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def format_floor_value(value: float) -> str:
    return f"{value:.10f}"


def quantize_current_for_error(current: float) -> float:
    return float(
        Decimal(str(current)).quantize(CURRENT_DECIMAL_STEP, rounding=ROUND_HALF_UP)
    )


def interpolate_series_value(
    times: list[float], values: list[float], target_time: float
) -> float:
    if len(times) != len(values):
        raise ValueError("Times and values must have the same length")
    if not times:
        raise ValueError("Cannot interpolate an empty series")

    if target_time <= times[0]:
        return values[0]
    if target_time >= times[-1]:
        return values[-1]

    right_index = bisect_left(times, target_time)
    if right_index < len(times) and math.isclose(
        times[right_index], target_time, rel_tol=0.0, abs_tol=1e-12
    ):
        return values[right_index]

    left_index = max(0, right_index - 1)
    t1 = times[left_index]
    t2 = times[right_index]
    v1 = values[left_index]
    v2 = values[right_index]
    if math.isclose(t1, t2, rel_tol=0.0, abs_tol=1e-15):
        return v1

    fraction = (target_time - t1) / (t2 - t1)
    return v1 + fraction * (v2 - v1)


def extract_series_window(
    times: list[float],
    values: list[float],
    start_time: float,
    end_time: float,
) -> tuple[list[float], list[float]]:
    if len(times) != len(values):
        raise ValueError("Times and values must have the same length")
    if not times:
        return [], []
    if end_time < times[0] or start_time > times[-1]:
        return [], []

    window_start = max(start_time, times[0])
    window_end = min(end_time, times[-1])
    if window_end < window_start:
        return [], []

    window_times = [window_start]
    window_values = [interpolate_series_value(times, values, window_start)]

    for time, value in zip(times, values):
        if window_start < time < window_end:
            window_times.append(time)
            window_values.append(value)

    end_value = interpolate_series_value(times, values, window_end)
    if math.isclose(window_times[-1], window_end, rel_tol=0.0, abs_tol=1e-12):
        window_values[-1] = end_value
    else:
        window_times.append(window_end)
        window_values.append(end_value)

    return window_times, window_values


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


def format_charge(coulombs: float) -> str:
    magnitude = abs(coulombs)
    units = [
        (1.0, "C"),
        (1e-3, "mC"),
        (1e-6, "uC"),
        (1e-9, "nC"),
        (1e-12, "pC"),
    ]
    for scale, unit in units:
        if magnitude >= scale or scale == 1e-12:
            return f"{coulombs / scale:.6g} {unit}"
    return f"{coulombs:.6g} C"


def format_area(area: float) -> str:
    return f"{area:.6g} A*s ({format_charge(area)})"


def format_area_range(lower: float, upper: float) -> str:
    return f"{format_area(lower)} to {format_area(upper)}"


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


def trapezoid_time_uncertainty_from_point_error(
    values: list[float], half_time_error: float = TIME_HALF_ERROR_S
) -> float:
    # Worst-case bound: sum the absolute x-sensitivities, assuming all point
    # time errors push in the same direction.
    coefficients = trapezoid_x_sensitivity_coefficients(values)
    return half_time_error * sum(abs(coefficient) for coefficient in coefficients)


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


def format_uncertainty(area_sigma: float) -> str:
    return f"+/- {format_area(area_sigma)}"

def calculate_area_error_bounds(
    times: list[float], currents: list[float], floor: float
) -> dict[str, tuple[float, float]]:
    # Keep the nominal calculations unchanged. For bounds only, quantize the
    # currents to the DMM resolution (10 nA -> 8 decimal places in amps),
    # apply +/- half a least-significant digit vertically, and model time
    # uncertainty as horizontal uncertainty on each sample point (+/- 0.1 s).
    if len(times) != len(currents):
        raise ValueError("Times and currents must have the same length")

    rounded_currents = [quantize_current_for_error(current) for current in currents]
    currents_min = [current - CURRENT_HALF_ERROR_A for current in rounded_currents]
    currents_max = [current + CURRENT_HALF_ERROR_A for current in rounded_currents]

    raw_min_current = integrate_trapezoid(times, currents_min)
    raw_max_current = integrate_trapezoid(times, currents_max)
    raw_time_uncertainty = trapezoid_time_uncertainty_from_point_error(rounded_currents)

    net_min_current, above_min_current = integrate_relative_to_floor(
        times, currents_min, floor
    )
    net_max_current, above_max_current = integrate_relative_to_floor(
        times, currents_max, floor
    )
    shifted_rounded_currents = [current - floor for current in rounded_currents]
    clipped_shifted_currents = [
        max(current_minus_floor, 0.0)
        for current_minus_floor in shifted_rounded_currents
    ]
    net_time_uncertainty = trapezoid_time_uncertainty_from_point_error(
        shifted_rounded_currents
    )
    area_above_time_uncertainty = trapezoid_time_uncertainty_from_point_error(
        clipped_shifted_currents
    )

    raw_min = raw_min_current - raw_time_uncertainty
    raw_max = raw_max_current + raw_time_uncertainty
    net_min = net_min_current - net_time_uncertainty
    net_max = net_max_current + net_time_uncertainty
    above_min = max(0.0, above_min_current - area_above_time_uncertainty)
    above_max = above_max_current + area_above_time_uncertainty

    return {
        "area_above": (above_min, above_max),
        "net_area": (net_min, net_max),
        "total_charge": (raw_min, raw_max),
    }


def calculate_area_statistical_uncertainties(
    times: list[float], currents: list[float], floor: float
) -> dict[str, float]:
    # First-order statistical propagation: treat current and time errors on each
    # point as independent random uncertainties and combine their contributions
    # in quadrature.
    if len(times) != len(currents):
        raise ValueError("Times and currents must have the same length")

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
        "net_area": trapezoid_statistical_uncertainty(
            times,
            shifted_rounded_currents,
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


class CurrentAreaApp:
    def __init__(
        self,
        root: tk.Tk,
        csv_paths: list[Path],
        initial_csv: str | None,
        initial_floor: float | None,
    ) -> None:
        if not csv_paths:
            raise ValueError("No CSV files were found to display")

        self.root = root
        self.csv_paths = csv_paths
        self.csv_lookup = {csv_path.name: csv_path for csv_path in csv_paths}
        self.display_to_csv: dict[str, Path] = {}
        self.csv_to_display: dict[str, str] = {}
        for index, csv_path in enumerate(csv_paths, start=1):
            display_label = get_csv_display_label(csv_path, index=index)
            self.display_to_csv[display_label] = csv_path
            self.csv_to_display[csv_path.name] = display_label
        self.pending_initial_floor = initial_floor

        self.selected_csv_var = tk.StringVar()
        self.floor_entry_var = tk.StringVar()
        self.avg_window_start_var = tk.StringVar(value="0.0")
        self.avg_window_end_var = tk.StringVar(value="10.0")
        self.calc_range_button_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.filename_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.area_above_var = tk.StringVar(value="Nominal: -")
        self.area_above_bounds_var = tk.StringVar(value="Worst-case min/max: -")
        self.area_above_stat_var = tk.StringVar(value="Statistical (RSS, 1sigma): -")
        self.net_area_var = tk.StringVar(value="Nominal: -")
        self.net_area_bounds_var = tk.StringVar(value="Worst-case min/max: -")
        self.net_area_stat_var = tk.StringVar(value="Statistical (RSS, 1sigma): -")
        self.total_charge_var = tk.StringVar(value="Nominal: -")
        self.total_charge_bounds_var = tk.StringVar(value="Worst-case min/max: -")
        self.total_charge_stat_var = tk.StringVar(
            value="Statistical (RSS, 1sigma): -"
        )
        self.floor_value_var = tk.StringVar(value="Current floor: -")

        self.current_path: Path | None = None
        self.times: list[float] = []
        self.currents: list[float] = []
        self.floor_min = 0.0
        self.floor_max = 1.0
        self.current_floor = 0.0
        self.is_syncing_floor = False
        self.use_average_window_for_calculations = False

        default_csv = self.resolve_initial_csv(initial_csv)
        self.selected_csv_var.set(self.csv_to_display[default_csv])
        self.update_calc_range_button_text()

        self.build_ui()
        self.load_selected_csv()

    def resolve_initial_csv(self, initial_csv: str | None) -> str:
        if initial_csv is None:
            return self.csv_paths[0].name

        csv_name = Path(initial_csv).name
        if csv_name in self.csv_lookup:
            return csv_name

        return self.csv_paths[0].name

    def build_ui(self) -> None:
        self.root.title("VirtualBench Current Area Tool")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.root, padding=12)
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(5, weight=1)

        ttk.Label(controls, text="CSV file").grid(row=0, column=0, sticky="w")
        self.csv_combo = ttk.Combobox(
            controls,
            textvariable=self.selected_csv_var,
            values=[self.csv_to_display[csv_path.name] for csv_path in self.csv_paths],
            state="readonly",
            width=72,
        )
        self.csv_combo.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.csv_combo.bind("<<ComboboxSelected>>", self.on_csv_selected)

        ttk.Button(controls, text="Plot CSV", command=self.load_selected_csv).grid(
            row=0, column=2, sticky="w", padx=(0, 16)
        )

        ttk.Label(controls, text="Current floor (A)").grid(row=0, column=3, sticky="w")
        self.floor_entry = ttk.Entry(
            controls, textvariable=self.floor_entry_var, width=18
        )
        self.floor_entry.grid(row=0, column=4, sticky="w", padx=(8, 8))
        self.floor_entry.bind("<Return>", self.apply_floor_entry)
        self.floor_entry.bind("<FocusOut>", self.apply_floor_entry)

        ttk.Button(controls, text="Apply Floor", command=self.apply_floor_entry).grid(
            row=0, column=5, sticky="w", padx=(0, 8)
        )

        ttk.Label(controls, text="Floor slider").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.floor_scale = tk.Scale(
            controls,
            orient=tk.HORIZONTAL,
            from_=0.0,
            to=1.0,
            resolution=1e-9,
            showvalue=False,
            command=self.on_floor_slider_changed,
            length=700,
        )
        self.floor_scale.grid(row=1, column=1, columnspan=4, sticky="ew", pady=(6, 0))

        ttk.Button(controls, text="Use Min Current", command=self.use_min_current).grid(
            row=1, column=5, sticky="w", padx=(0, 8), pady=(6, 0)
        )
        ttk.Button(controls, text="Reset View", command=self.reset_view).grid(
            row=1, column=7, sticky="w", pady=(6, 0)
        )

        info_frame = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        info_frame.grid(row=1, column=0, sticky="nsew")
        info_frame.columnconfigure(0, weight=3)
        info_frame.columnconfigure(1, weight=2)
        info_frame.rowconfigure(0, weight=1)

        plot_frame = ttk.Frame(info_frame)
        plot_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(1, weight=1)

        self.figure = Figure(figsize=(9, 6), dpi=100)
        self.ax = self.figure.add_subplot(111)

        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.grid(row=0, column=0, sticky="ew")

        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=1, column=0, sticky="nsew")

        self.toolbar = NavigationToolbar2Tk(
            self.canvas, toolbar_frame, pack_toolbar=False
        )
        self.toolbar.update()
        self.toolbar.grid(row=0, column=0, sticky="w")

        sidebar = ttk.Frame(info_frame)
        sidebar.grid(row=0, column=1, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)

        avg_window_frame = ttk.Frame(sidebar)
        avg_window_frame.grid(row=0, column=0, sticky="ew")
        avg_window_frame.columnconfigure(5, weight=1)

        ttk.Label(avg_window_frame, text="Avg window (s)").grid(
            row=0, column=0, sticky="w"
        )
        self.avg_window_start_entry = ttk.Entry(
            avg_window_frame, textvariable=self.avg_window_start_var, width=8
        )
        self.avg_window_start_entry.grid(row=0, column=1, sticky="w", padx=(8, 4))
        self.avg_window_start_entry.bind("<Return>", self.on_average_window_changed)
        self.avg_window_start_entry.bind("<FocusOut>", self.on_average_window_changed)

        ttk.Label(avg_window_frame, text="to").grid(row=0, column=2, sticky="w")
        self.avg_window_end_entry = ttk.Entry(
            avg_window_frame, textvariable=self.avg_window_end_var, width=8
        )
        self.avg_window_end_entry.grid(row=0, column=3, sticky="w", padx=(4, 8))
        self.avg_window_end_entry.bind("<Return>", self.on_average_window_changed)
        self.avg_window_end_entry.bind("<FocusOut>", self.on_average_window_changed)

        ttk.Button(
            avg_window_frame,
            text="Use Avg Window",
            command=self.use_average_window,
        ).grid(row=0, column=4, sticky="w")

        ttk.Button(
            avg_window_frame,
            textvariable=self.calc_range_button_var,
            command=self.toggle_calculation_range,
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

        ttk.Label(
            sidebar,
            textvariable=self.filename_var,
            font=("TkDefaultFont", 10, "bold"),
            wraplength=380,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))

        ttk.Label(
            sidebar,
            textvariable=self.title_var,
            wraplength=380,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(6, 10))

        ttk.Separator(sidebar, orient="horizontal").grid(
            row=3, column=0, sticky="ew", pady=(0, 10)
        )

        ttk.Label(
            sidebar,
            textvariable=self.summary_var,
            wraplength=380,
            justify="left",
        ).grid(row=4, column=0, sticky="w")

        ttk.Label(
            sidebar,
            textvariable=self.floor_value_var,
            wraplength=380,
            justify="left",
        ).grid(row=5, column=0, sticky="w", pady=(10, 0))

        ttk.Separator(sidebar, orient="horizontal").grid(
            row=6, column=0, sticky="ew", pady=(12, 10)
        )

        ttk.Label(
            sidebar,
            text="Raw Charge",
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=7, column=0, sticky="w")

        ttk.Label(
            sidebar,
            textvariable=self.total_charge_var,
            wraplength=380,
            justify="left",
        ).grid(row=8, column=0, sticky="w", pady=(6, 0))

        ttk.Label(
            sidebar,
            textvariable=self.total_charge_bounds_var,
            wraplength=380,
            justify="left",
        ).grid(row=9, column=0, sticky="w", pady=(4, 0))

        ttk.Label(
            sidebar,
            textvariable=self.total_charge_stat_var,
            wraplength=380,
            justify="left",
        ).grid(row=10, column=0, sticky="w", pady=(4, 0))

        ttk.Separator(sidebar, orient="horizontal").grid(
            row=11, column=0, sticky="ew", pady=(12, 10)
        )

        ttk.Label(
            sidebar,
            text="Net Area Wrt Floor",
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=12, column=0, sticky="w")

        ttk.Label(
            sidebar,
            textvariable=self.net_area_bounds_var,
            wraplength=380,
            justify="left",
        ).grid(row=14, column=0, sticky="w", pady=(4, 0))

        ttk.Label(
            sidebar,
            textvariable=self.net_area_var,
            wraplength=380,
            justify="left",
        ).grid(row=13, column=0, sticky="w", pady=(6, 0))

        ttk.Label(
            sidebar,
            textvariable=self.net_area_stat_var,
            wraplength=380,
            justify="left",
        ).grid(row=15, column=0, sticky="w", pady=(4, 0))

        ttk.Separator(sidebar, orient="horizontal").grid(
            row=16, column=0, sticky="ew", pady=(12, 10)
        )

        ttk.Label(
            sidebar,
            text="Area Above Floor",
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=17, column=0, sticky="w")

        ttk.Separator(sidebar, orient="horizontal").grid(
            row=21, column=0, sticky="ew", pady=(12, 10)
        )

        self.status_label = ttk.Label(
            sidebar,
            textvariable=self.status_var,
            foreground="#444444",
            wraplength=380,
            justify="left",
        )
        self.status_label.grid(row=23, column=0, sticky="w", pady=(12, 0))

        ttk.Label(
            sidebar,
            textvariable=self.area_above_var,
            wraplength=380,
            justify="left",
        ).grid(row=18, column=0, sticky="w", pady=(6, 0))

        ttk.Label(
            sidebar,
            textvariable=self.area_above_bounds_var,
            wraplength=380,
            justify="left",
        ).grid(row=19, column=0, sticky="w", pady=(4, 0))

        ttk.Label(
            sidebar,
            textvariable=self.area_above_stat_var,
            wraplength=380,
            justify="left",
        ).grid(row=20, column=0, sticky="w", pady=(4, 0))

        ttk.Label(
            sidebar,
            text=(
                "Use the toolbar to zoom and pan. Each section shows the unchanged "
                "nominal result, a worst-case bound, and a statistical RSS 1sigma "
                "uncertainty based on 10 nA current resolution and +/- 0.1 s "
                "horizontal uncertainty on each sample point. The light blue band "
                "marks the chosen time window used by 'Use Avg Window', and it can "
                "also be used as the calculation range."
            ),
            wraplength=380,
            justify="left",
        ).grid(row=22, column=0, sticky="w")

    def set_status(self, message: str, *, is_error: bool = False) -> None:
        self.status_var.set(message)
        self.status_label.configure(foreground="#aa0000" if is_error else "#444444")

    def on_csv_selected(self, _event=None) -> None:
        self.load_selected_csv()

    def load_selected_csv(self) -> None:
        selected_label = self.selected_csv_var.get()
        csv_path = self.display_to_csv[selected_label]
        try:
            times, currents = load_csv_series(csv_path)
        except Exception as exc:
            self.set_status(f"Could not load {csv_path.name}: {exc}", is_error=True)
            self.root.bell()
            return

        self.current_path = csv_path
        self.times = times
        self.currents = currents
        self.filename_var.set(csv_path.name)
        self.title_var.set(TITLE_BY_FILE.get(csv_path.name, csv_path.stem))
        self.set_status("")

        self.configure_floor_controls()
        self.update_plot()
        self.calculate_area()

    def configure_floor_controls(self) -> None:
        data_min = min(self.currents)
        data_max = max(self.currents)
        span = data_max - data_min
        margin = span * 0.15 if span > 0 else max(abs(data_min) * 0.15, 1e-9)

        self.floor_min = data_min - margin
        self.floor_max = data_max + margin
        self.floor_scale.configure(
            from_=self.floor_min,
            to=self.floor_max,
            resolution=-1,
            digits=16,
        )

        if self.pending_initial_floor is not None:
            floor = self.pending_initial_floor
            self.pending_initial_floor = None
        else:
            floor = data_min

        self.set_floor_value(clamp(floor, self.floor_min, self.floor_max))

    def set_floor_value(self, floor: float) -> None:
        self.current_floor = floor
        self.is_syncing_floor = True
        self.floor_scale.set(floor)
        self.floor_entry_var.set(format_floor_value(floor))
        self.is_syncing_floor = False

    def get_floor_value(self) -> float:
        return self.current_floor

    def on_floor_slider_changed(self, value: str) -> None:
        if self.is_syncing_floor:
            return
        floor = float(value)
        self.current_floor = floor
        self.floor_entry_var.set(format_floor_value(floor))
        self.update_plot(preserve_limits=True)
        self.calculate_area()

    def apply_floor_entry(self, _event=None) -> None:
        if not self.currents:
            return

        raw_text = self.floor_entry_var.get().strip()
        if not raw_text:
            self.set_status("Enter a current floor in amps.", is_error=True)
            return

        try:
            floor = float(raw_text)
        except ValueError:
            self.set_status(f"Could not parse floor value: {raw_text}", is_error=True)
            self.root.bell()
            return

        floor = clamp(floor, self.floor_min, self.floor_max)
        self.set_floor_value(floor)
        self.set_status("")
        self.update_plot(preserve_limits=True)
        self.calculate_area()

    def use_min_current(self) -> None:
        if not self.currents:
            return
        self.set_floor_value(min(self.currents))
        self.update_plot(preserve_limits=True)
        self.calculate_area()

    def parse_average_window(
        self, *, show_error: bool = False
    ) -> tuple[float, float] | None:
        raw_start = self.avg_window_start_var.get().strip()
        raw_end = self.avg_window_end_var.get().strip()
        try:
            start_time = float(raw_start)
            end_time = float(raw_end)
        except ValueError:
            if show_error:
                self.set_status(
                    "Average window start/end must be valid numbers in seconds.",
                    is_error=True,
                )
                self.root.bell()
            return None

        if start_time < 0.0 or end_time < 0.0 or end_time <= start_time:
            if show_error:
                self.set_status(
                    "Average window must satisfy 0 <= start < end.",
                    is_error=True,
                )
                self.root.bell()
            return None

        return start_time, end_time

    def on_average_window_changed(self, _event=None) -> None:
        if self.current_path is None:
            return
        if self.parse_average_window(show_error=False) is None:
            return
        self.set_status("")
        self.update_plot(preserve_limits=True)
        self.calculate_area()

    def update_calc_range_button_text(self) -> None:
        if self.use_average_window_for_calculations:
            self.calc_range_button_var.set("Calculations: Chosen Time Window")
            return
        self.calc_range_button_var.set("Calculations: Full Range")

    def toggle_calculation_range(self) -> None:
        next_mode_uses_window = not self.use_average_window_for_calculations
        if next_mode_uses_window and self.parse_average_window(show_error=True) is None:
            return

        self.use_average_window_for_calculations = next_mode_uses_window
        self.update_calc_range_button_text()
        self.update_plot(preserve_limits=True)
        self.calculate_area()

    def get_calculation_series(
        self, *, show_error: bool = False
    ) -> tuple[list[float], list[float], str] | None:
        if not self.times or not self.currents:
            return None

        if not self.use_average_window_for_calculations:
            return (
                self.times,
                self.currents,
                "Calculation range: full trace "
                f"({self.times[0]:.6g}-{self.times[-1]:.6g} s)",
            )

        average_window = self.parse_average_window(show_error=show_error)
        if average_window is None:
            return None

        window_start, window_end = average_window
        calc_times, calc_currents = extract_series_window(
            self.times, self.currents, window_start, window_end
        )
        if not calc_times:
            if show_error:
                self.set_status(
                    "The chosen time window does not overlap the loaded trace.",
                    is_error=True,
                )
                self.root.bell()
            return None

        requested_range = f"{window_start:g}-{window_end:g} s"
        actual_range = f"{calc_times[0]:.6g}-{calc_times[-1]:.6g} s"
        if requested_range == actual_range:
            return (
                calc_times,
                calc_currents,
                f"Calculation range: chosen time window ({actual_range})",
            )

        return (
            calc_times,
            calc_currents,
            "Calculation range: chosen time window "
            f"(requested {requested_range}, using {actual_range})",
        )

    def use_average_window(self) -> None:
        if not self.currents:
            return

        average_window = self.parse_average_window(show_error=True)
        if average_window is None:
            return

        start_time, end_time = average_window
        window_currents = [
            current
            for time, current in zip(self.times, self.currents)
            if start_time <= time <= end_time
        ]
        if not window_currents:
            self.set_status(
                "Could not compute average floor because the selected window has no samples.",
                is_error=True,
            )
            self.root.bell()
            return

        average_floor = sum(window_currents) / len(window_currents)
        self.set_floor_value(clamp(average_floor, self.floor_min, self.floor_max))
        self.set_status(
            f"Floor set to the average current over {start_time:g}-{end_time:g} s."
        )
        self.update_plot(preserve_limits=True)
        self.calculate_area()

    def update_plot(self, preserve_limits: bool = False) -> None:
        if self.current_path is None:
            return

        floor = self.get_floor_value()
        where_above = [current >= floor for current in self.currents]
        where_below = [current < floor for current in self.currents]
        average_window = self.parse_average_window(show_error=False)
        window_label = "Chosen time window"
        if self.use_average_window_for_calculations:
            window_label += " (also calc range)"
        saved_limits: tuple[tuple[float, float], tuple[float, float]] | None = None
        if preserve_limits and self.ax.has_data():
            saved_limits = (self.ax.get_xlim(), self.ax.get_ylim())

        self.ax.clear()
        self.ax.plot(
            self.times,
            self.currents,
            color="tab:blue",
            linewidth=1.2,
            label="Measured current",
        )
        self.ax.axhline(
            floor,
            color="tab:red",
            linestyle="--",
            linewidth=1.2,
            label=f"Floor = {format_floor_value(floor)} A",
        )
        if average_window is not None:
            window_start, window_end = average_window
            self.ax.axvspan(
                window_start,
                window_end,
                color="tab:cyan",
                alpha=0.10,
                label=window_label,
            )
            self.ax.axvline(
                window_start,
                color="tab:cyan",
                linestyle=":",
                linewidth=1.0,
            )
            self.ax.axvline(
                window_end,
                color="tab:cyan",
                linestyle=":",
                linewidth=1.0,
            )
        if any(where_above):
            self.ax.fill_between(
                self.times,
                [floor] * len(self.times),
                self.currents,
                where=where_above,
                interpolate=True,
                color="tab:green",
                alpha=0.28,
                label="Positive wrt floor",
            )
        if any(where_below):
            self.ax.fill_between(
                self.times,
                [floor] * len(self.times),
                self.currents,
                where=where_below,
                interpolate=True,
                color="tab:red",
                alpha=0.22,
                label="Negative wrt floor",
            )

        title = TITLE_BY_FILE.get(self.current_path.name, self.current_path.stem)
        self.ax.set_title(f"{self.current_path.name}\n{title}", fontsize=10)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Current (A)")
        self.ax.grid(True, alpha=0.3)
        self.ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
        self.ax.legend(loc="upper right")
        if saved_limits is not None:
            xlim, ylim = saved_limits
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)

        self.canvas.draw_idle()

    def calculate_area(self) -> None:
        if self.current_path is None:
            return

        floor = self.get_floor_value()
        calculation_series = self.get_calculation_series(show_error=True)
        if calculation_series is None:
            return

        calc_times, calc_currents, range_summary = calculation_series
        try:
            signed_area, positive_area = integrate_relative_to_floor(
                calc_times, calc_currents, floor
            )
            # This is the integral of the original current trace, before removing the floor.
            total_charge = integrate_trapezoid(calc_times, calc_currents)
            error_bounds = calculate_area_error_bounds(calc_times, calc_currents, floor)
            statistical_uncertainties = calculate_area_statistical_uncertainties(
                calc_times, calc_currents, floor
            )
        except Exception as exc:
            self.set_status(f"Could not calculate area: {exc}", is_error=True)
            self.root.bell()
            return

        duration = calc_times[-1] - calc_times[0] if len(calc_times) >= 2 else 0.0
        self.summary_var.set(
            "\n".join(
                [
                    range_summary,
                    f"Samples used: {len(calc_times)}",
                    f"Duration: {duration:.6g} s",
                    f"Current min: {min(calc_currents):.6g} A",
                    f"Current max: {max(calc_currents):.6g} A",
                ]
            )
        )
        self.floor_value_var.set(f"Current floor: {format_floor_value(floor)} A")
        self.total_charge_var.set(f"Nominal: {format_area(total_charge)}")
        self.total_charge_bounds_var.set(
            f"Worst-case min/max: {format_area_range(*error_bounds['total_charge'])}"
        )
        self.total_charge_stat_var.set(
            "Statistical (RSS, 1sigma): "
            f"{format_uncertainty(statistical_uncertainties['total_charge'])}"
        )
        self.net_area_var.set(
            f"Nominal: {format_area(signed_area)}"
        )
        self.net_area_bounds_var.set(
            f"Worst-case min/max: {format_area_range(*error_bounds['net_area'])}"
        )
        self.net_area_stat_var.set(
            "Statistical (RSS, 1sigma): "
            f"{format_uncertainty(statistical_uncertainties['net_area'])}"
        )
        self.area_above_var.set(f"Nominal: {format_area(positive_area)}")
        self.area_above_bounds_var.set(
            "Worst-case min/max: "
            f"{format_area_range(*error_bounds['area_above'])}"
        )
        self.area_above_stat_var.set(
            "Statistical (RSS, 1sigma): "
            f"{format_uncertainty(statistical_uncertainties['area_above'])}"
        )
        self.set_status(
            "Nominal values are unchanged. Worst-case min/max act like systematic "
            "bounds; statistical values are RSS 1sigma uncertainties."
        )

    def reset_view(self) -> None:
        self.update_plot(preserve_limits=False)


def main() -> int:
    args = parse_args()
    csv_paths = build_csv_list(args.mapped_only)
    if not csv_paths:
        raise SystemExit("No current_log CSV files were found.")

    root = tk.Tk()
    CurrentAreaApp(root, csv_paths, args.csv, args.floor)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
