#!/usr/bin/env python3
from __future__ import annotations

import argparse
import colorsys
import math
import random
import re
import tkinter as tk
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from zipfile import ZipFile

from matplotlib import colors as mcolors
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

try:
    from plot_current_logs import DATA_DIR, TITLE_BY_FILE, load_csv_series
except ModuleNotFoundError:
    from VirtualBench_power_tests.plot_current_logs import (
        DATA_DIR,
        TITLE_BY_FILE,
        load_csv_series,
    )


DEFAULT_SPREADSHEET = (
    Path.home() / "Dropbox" / "PC" / "Downloads" / "FUTURE Calcs.xlsx"
)
POWER_SHEET_NAME = "Power"
XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
CELL_REF_PATTERN = re.compile(r"([A-Z]+)(\d+)")
FILE_PATTERN = re.compile(r"(current_log_\d{8}_\d{6}\.csv)")
WINDOW_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*s",
    re.IGNORECASE,
)
ALIGNMENT_MODES = (
    "Raw time",
    "Align averaging window start",
    "Align peak in chosen window",
)


@dataclass
class AveragingWindow:
    start_s: float
    end_s: float
    source: str


@dataclass
class SpreadsheetTraceEntry:
    filename: str
    file_label: str
    mode_name: str
    avg_current_a: float | None
    charge_mc: float | None
    notes: str
    weight: float | None
    windows: list[AveragingWindow] = field(default_factory=list)
    uses_full_trace: bool = False


@dataclass
class ModePreset:
    name: str
    description: str = ""
    trace_entries: list[SpreadsheetTraceEntry] = field(default_factory=list)
    weighted_mean_avg_current_a: float | None = None
    weighted_mean_charge_mc: float | None = None
    weighted_mean_notes: str = ""


@dataclass
class TraceRecord:
    index: int
    csv_path: Path
    title: str
    label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive UI for grouped current-log comparisons using the Power "
            "spreadsheet presets."
        )
    )
    parser.add_argument(
        "--spreadsheet",
        type=Path,
        default=DEFAULT_SPREADSHEET,
        help=f"Path to FUTURE Calcs.xlsx. Default: {DEFAULT_SPREADSHEET}",
    )
    parser.add_argument(
        "--sheet",
        type=str,
        default=POWER_SHEET_NAME,
        help=f"Worksheet name to read. Default: {POWER_SHEET_NAME}",
    )
    return parser.parse_args()


def shorten_label(label: str, max_length: int = 84) -> str:
    if len(label) <= max_length:
        return label
    return f"{label[: max_length - 3]}..."


def format_current(value_a: float | None) -> str:
    if value_a is None:
        return "-"

    magnitude = abs(value_a)
    units = [
        (1.0, "A"),
        (1e-3, "mA"),
        (1e-6, "uA"),
        (1e-9, "nA"),
        (1e-12, "pA"),
    ]
    for scale, unit in units:
        if magnitude >= scale or scale == 1e-12:
            return f"{value_a / scale:.6g} {unit}"
    return f"{value_a:.6g} A"


def format_charge_mc(value_mc: float | None) -> str:
    if value_mc is None:
        return "-"
    return f"{value_mc:.6g} mC"


def format_signed_seconds(value_s: float) -> str:
    return f"{value_s:+.3f} s"


def color_distance_rgb(color_a: tuple[float, float, float], color_b: tuple[float, float, float]) -> float:
    return math.sqrt(
        (color_a[0] - color_b[0]) ** 2
        + (color_a[1] - color_b[1]) ** 2
        + (color_a[2] - color_b[2]) ** 2
    )


def generate_distinct_random_colors(count: int, seed: int = 20260516) -> list[str]:
    if count <= 0:
        return []

    rng = random.Random(seed + count * 97)
    colors: list[tuple[float, float, float]] = []
    min_distance = 0.50
    max_attempts = 12000
    attempts = 0

    while len(colors) < count and attempts < max_attempts:
        rgb = colorsys.hsv_to_rgb(
            rng.random(),
            rng.uniform(0.55, 0.90),
            rng.uniform(0.55, 0.95),
        )
        if not colors or color_distance_rgb(rgb, colors[-1]) >= min_distance:
            colors.append(rgb)
        attempts += 1

    fallback_threshold = 0.30
    while len(colors) < count:
        rgb = colorsys.hsv_to_rgb(
            rng.random(),
            rng.uniform(0.50, 0.90),
            rng.uniform(0.50, 0.95),
        )
        if not colors or color_distance_rgb(rgb, colors[-1]) >= fallback_threshold:
            colors.append(rgb)

    return [mcolors.to_hex(rgb) for rgb in colors]


def parse_optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def excel_column_to_number(column_name: str) -> int:
    result = 0
    for char in column_name:
        result = result * 26 + (ord(char) - 64)
    return result


def build_trace_records() -> list[TraceRecord]:
    trace_records: list[TraceRecord] = []
    for index, csv_path in enumerate(sorted(DATA_DIR.glob("current_log_*.csv")), start=1):
        title = TITLE_BY_FILE.get(csv_path.name, csv_path.stem)
        label = f"[{index:02d}] {title} | {csv_path.name}"
        trace_records.append(
            TraceRecord(index=index, csv_path=csv_path, title=title, label=label)
        )
    return trace_records


def parse_shared_strings(xml_root: ET.Element) -> list[str]:
    strings: list[str] = []
    for item in xml_root.findall("main:si", XLSX_NS):
        parts = [node.text or "" for node in item.iterfind(".//main:t", XLSX_NS)]
        strings.append("".join(parts))
    return strings


def find_sheet_path(workbook_zip: ZipFile, sheet_name: str) -> str:
    workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))

    rel_map: dict[str, str] = {}
    for relation in rels_root:
        rel_id = relation.attrib.get("Id")
        target = relation.attrib.get("Target")
        if rel_id and target:
            rel_map[rel_id] = target

    sheets = workbook_root.find("main:sheets", XLSX_NS)
    if sheets is None:
        raise ValueError("Workbook is missing a sheets collection")

    for sheet in sheets:
        if sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        if rel_id is None or rel_id not in rel_map:
            break
        return f"xl/{rel_map[rel_id]}"

    raise ValueError(f"Could not find worksheet named {sheet_name!r}")


def load_sheet_rows(workbook_path: Path, sheet_name: str) -> dict[int, dict[int, str]]:
    with ZipFile(workbook_path) as workbook_zip:
        shared_strings = parse_shared_strings(
            ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
        )
        sheet_path = find_sheet_path(workbook_zip, sheet_name)
        sheet_root = ET.fromstring(workbook_zip.read(sheet_path))

    rows: dict[int, dict[int, str]] = {}
    for cell in sheet_root.findall(".//main:c", XLSX_NS):
        cell_ref = cell.attrib.get("r")
        if cell_ref is None:
            continue

        match = CELL_REF_PATTERN.fullmatch(cell_ref)
        if match is None:
            continue

        column_index = excel_column_to_number(match.group(1))
        row_index = int(match.group(2))
        cell_type = cell.attrib.get("t")
        value_node = cell.find("main:v", XLSX_NS)

        value = ""
        if cell_type == "s" and value_node is not None:
            value = shared_strings[int(value_node.text)]
        elif cell_type == "inlineStr":
            value = "".join(
                text_node.text or ""
                for text_node in cell.iterfind(".//main:t", XLSX_NS)
            )
        elif value_node is not None and value_node.text is not None:
            value = value_node.text

        rows.setdefault(row_index, {})[column_index] = value

    return rows


def extract_filename(cell_value: str | None) -> str | None:
    if not cell_value:
        return None
    match = FILE_PATTERN.search(cell_value)
    if match is None:
        return None
    return match.group(1)


def parse_windows_from_notes(notes: str) -> list[AveragingWindow]:
    windows: list[AveragingWindow] = []
    for match in WINDOW_PATTERN.finditer(notes):
        start_s = float(match.group(1))
        end_s = float(match.group(2))
        if end_s > start_s:
            windows.append(
                AveragingWindow(start_s=start_s, end_s=end_s, source=match.group(0))
            )
    return windows


def parse_mode_presets(
    workbook_path: Path,
    sheet_name: str,
    trace_records: dict[str, TraceRecord],
) -> tuple[list[ModePreset], dict[str, SpreadsheetTraceEntry]]:
    rows = load_sheet_rows(workbook_path, sheet_name)
    mode_presets: list[ModePreset] = []
    entry_by_filename: dict[str, SpreadsheetTraceEntry] = {}

    current_preset: ModePreset | None = None
    for row_index in sorted(rows):
        row = rows[row_index]
        mode_value = (row.get(14) or "").strip()
        avg_current = parse_optional_float(row.get(15))
        charge_mc = parse_optional_float(row.get(16))
        notes = (row.get(17) or "").strip()
        weight = parse_optional_float(row.get(18))
        file_label = (row.get(19) or "").strip()

        if row_index == 1:
            continue

        if mode_value == "Plugged-in LCD":
            break

        if mode_value == "Weighted Mean":
            if current_preset is not None:
                current_preset.weighted_mean_avg_current_a = avg_current
                current_preset.weighted_mean_charge_mc = charge_mc
                current_preset.weighted_mean_notes = notes
                mode_presets.append(current_preset)
            current_preset = None
            continue

        if mode_value and not mode_value.startswith("("):
            current_preset = ModePreset(name=mode_value)

        if current_preset is None:
            continue

        if mode_value.startswith("("):
            current_preset.description = (
                mode_value
                if not current_preset.description
                else f"{current_preset.description} {mode_value}"
            )

        filename = extract_filename(file_label)
        if filename is None:
            continue
        if filename not in trace_records:
            continue

        windows = parse_windows_from_notes(notes)
        entry = SpreadsheetTraceEntry(
            filename=filename,
            file_label=file_label,
            mode_name=current_preset.name,
            avg_current_a=avg_current,
            charge_mc=charge_mc,
            notes=notes,
            weight=weight,
            windows=windows,
            uses_full_trace=not windows,
        )
        current_preset.trace_entries.append(entry)
        entry_by_filename[filename] = entry

    return mode_presets, entry_by_filename


def interpolate_value(times: list[float], values: list[float], target_time: float) -> float:
    if target_time <= times[0]:
        return values[0]
    if target_time >= times[-1]:
        return values[-1]

    for left_index in range(len(times) - 1):
        t1 = times[left_index]
        t2 = times[left_index + 1]
        if t1 <= target_time <= t2:
            if math.isclose(t1, t2, rel_tol=0.0, abs_tol=1e-15):
                return values[left_index]
            fraction = (target_time - t1) / (t2 - t1)
            return values[left_index] + fraction * (
                values[left_index + 1] - values[left_index]
            )

    return values[-1]


def extract_window_series(
    times: list[float],
    values: list[float],
    start_s: float,
    end_s: float,
) -> tuple[list[float], list[float]]:
    if not times or end_s <= start_s or end_s < times[0] or start_s > times[-1]:
        return [], []

    window_start = max(start_s, times[0])
    window_end = min(end_s, times[-1])
    if window_end <= window_start:
        return [], []

    result_times = [window_start]
    result_values = [interpolate_value(times, values, window_start)]

    for time, value in zip(times, values):
        if window_start < time < window_end:
            result_times.append(time)
            result_values.append(value)

    end_value = interpolate_value(times, values, window_end)
    if math.isclose(result_times[-1], window_end, rel_tol=0.0, abs_tol=1e-12):
        result_values[-1] = end_value
    else:
        result_times.append(window_end)
        result_values.append(end_value)

    return result_times, result_values


def integrate_trapezoid(times: list[float], values: list[float]) -> float:
    area = 0.0
    for t1, t2, v1, v2 in zip(times, times[1:], values, values[1:]):
        dt = t2 - t1
        if dt < 0:
            raise ValueError("Time values must be non-decreasing")
        area += 0.5 * (v1 + v2) * dt
    return area


def find_peak_time(
    times: list[float], currents: list[float], window_start: float, window_end: float
) -> float | None:
    best_time: float | None = None
    best_current: float | None = None
    for time, current in zip(times, currents):
        if not (window_start <= time <= window_end):
            continue
        if best_current is None or current > best_current:
            best_current = current
            best_time = time
    return best_time


class ModeTraceComparisonApp:
    def __init__(
        self,
        root: tk.Tk,
        spreadsheet_path: Path,
        sheet_name: str,
    ) -> None:
        self.root = root
        self.spreadsheet_path = spreadsheet_path
        self.sheet_name = sheet_name

        self.trace_records = build_trace_records()
        self.trace_by_filename = {
            trace.csv_path.name: trace for trace in self.trace_records
        }
        self.mode_presets, self.entry_by_filename = parse_mode_presets(
            spreadsheet_path,
            sheet_name,
            self.trace_by_filename,
        )
        if not self.trace_records:
            raise ValueError("No current_log_*.csv files were found in the data directory")

        self.trace_cache: dict[str, tuple[list[float], list[float]]] = {}
        self.trace_vars: dict[str, tk.BooleanVar] = {
            trace.csv_path.name: tk.BooleanVar(value=False) for trace in self.trace_records
        }

        self.preset_lookup = {preset.name: preset for preset in self.mode_presets}
        self.preset_var = tk.StringVar(
            value=self.mode_presets[0].name if self.mode_presets else "Manual selection"
        )
        self.alignment_mode_var = tk.StringVar(value=ALIGNMENT_MODES[0])
        self.align_window_start_var = tk.StringVar(value="0.0")
        self.align_window_end_var = tk.StringVar(value="60.0")
        self.show_avg_windows_var = tk.BooleanVar(value=True)
        self.show_avg_levels_var = tk.BooleanVar(value=True)
        self.plot_title_var = tk.StringVar()
        self.chart_width_var = tk.StringVar(value="11.0")
        self.chart_height_var = tk.StringVar(value="7.0")
        self.manual_shift_target_var = tk.StringVar()
        self.manual_shift_step_var = tk.StringVar(value="0.5")
        self.summary_var = tk.StringVar()
        self.selection_count_var = tk.StringVar(value="Selected traces: 0")
        self.status_var = tk.StringVar()
        self.status_label: ttk.Label | None = None
        self.manual_shift_display_to_filename: dict[str, str] = {}
        self.manual_offsets_s: dict[str, float] = {}
        self.trace_color_var_by_filename: dict[str, tk.StringVar] = {}
        self.trace_label_var_by_filename: dict[str, tk.StringVar] = {}
        self.trace_order_var_by_filename: dict[str, tk.StringVar] = {}
        self.default_trace_color_by_filename: dict[str, str] = {}
        self.overall_avg_label_var = tk.StringVar(value="Average current")
        self.overall_avg_color_var = tk.StringVar(value="#111111")
        self.legend_artist_to_group: dict[object, tuple[str, str]] = {}
        self.group_key_to_artists: dict[tuple[str, str], list[object]] = {}
        self.group_key_to_legend_artists: dict[
            tuple[str, str], tuple[object, object]
        ] = {}
        self.group_visibility: dict[tuple[str, str], bool] = {}
        self.customization_inner: ttk.Frame | None = None

        self.figure = Figure(figsize=(11, 7), dpi=100)
        self.figure.subplots_adjust(left=0.08, right=0.97, bottom=0.08, top=0.92)
        self.ax = self.figure.add_subplot(111)

        self.build_ui()
        self.refresh_manual_shift_targets()
        self.refresh_customization_controls()
        if self.mode_presets:
            self.apply_preset()
        else:
            self.update_summary()
            self.update_plot()

    def build_ui(self) -> None:
        self.root.title("VirtualBench Mode Trace Comparison")
        self.root.geometry("1650x980")
        self.root.minsize(1250, 760)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=4)
        main_frame.columnconfigure(1, weight=2)
        main_frame.rowconfigure(0, weight=1)

        plot_frame = ttk.Frame(main_frame)
        plot_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(1, weight=1)

        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.grid(row=0, column=0, sticky="ew")

        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self.canvas.mpl_connect("pick_event", self.on_plot_pick)

        self.toolbar = NavigationToolbar2Tk(
            self.canvas, toolbar_frame, pack_toolbar=False
        )
        self.toolbar.update()
        self.toolbar.grid(row=0, column=0, sticky="w")

        sidebar_host = ttk.Frame(main_frame)
        sidebar_host.grid(row=0, column=1, sticky="nsew")
        sidebar_host.columnconfigure(0, weight=1)
        sidebar_host.rowconfigure(0, weight=1)

        sidebar_canvas = tk.Canvas(sidebar_host, highlightthickness=0)
        sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        sidebar_scrollbar = ttk.Scrollbar(
            sidebar_host, orient="vertical", command=sidebar_canvas.yview
        )
        sidebar_scrollbar.grid(row=0, column=1, sticky="ns")
        sidebar_canvas.configure(yscrollcommand=sidebar_scrollbar.set)

        sidebar = ttk.Frame(sidebar_canvas)
        sidebar.columnconfigure(0, weight=1)
        self.sidebar_window_id = sidebar_canvas.create_window(
            (0, 0), window=sidebar, anchor="nw"
        )

        def on_sidebar_configure(_event=None) -> None:
            sidebar_canvas.configure(scrollregion=sidebar_canvas.bbox("all"))

        def on_sidebar_canvas_configure(event) -> None:
            sidebar_canvas.itemconfigure(self.sidebar_window_id, width=event.width)

        sidebar.bind("<Configure>", on_sidebar_configure)
        sidebar_canvas.bind("<Configure>", on_sidebar_canvas_configure)

        preset_frame = ttk.LabelFrame(sidebar, text="Preset")
        preset_frame.grid(row=0, column=0, sticky="ew")
        preset_frame.columnconfigure(0, weight=1)

        preset_values = [preset.name for preset in self.mode_presets]
        if not preset_values:
            preset_values = ["Manual selection"]
        self.preset_combo = ttk.Combobox(
            preset_frame,
            textvariable=self.preset_var,
            values=preset_values,
            state="readonly",
        )
        self.preset_combo.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(4, 4))
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)
        ttk.Button(preset_frame, text="Apply Preset", command=self.apply_preset).grid(
            row=0, column=1, sticky="w", pady=(4, 4)
        )

        action_frame = ttk.Frame(sidebar)
        action_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        action_frame.columnconfigure(0, weight=1)

        ttk.Button(action_frame, text="Plot Selected", command=self.update_plot).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(action_frame, text="Select All", command=self.select_all).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )
        ttk.Button(action_frame, text="Clear All", command=self.clear_selection).grid(
            row=0, column=2, sticky="ew", padx=(6, 0)
        )

        alignment_frame = ttk.LabelFrame(sidebar, text="Alignment")
        alignment_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        alignment_frame.columnconfigure(1, weight=1)

        ttk.Label(alignment_frame, text="Mode").grid(row=0, column=0, sticky="w")
        alignment_combo = ttk.Combobox(
            alignment_frame,
            textvariable=self.alignment_mode_var,
            values=list(ALIGNMENT_MODES),
            state="readonly",
        )
        alignment_combo.grid(row=0, column=1, sticky="ew", pady=(4, 4))
        alignment_combo.bind("<<ComboboxSelected>>", lambda _event: self.update_plot())

        ttk.Label(alignment_frame, text="Chosen window (s)").grid(
            row=1, column=0, sticky="w"
        )
        range_frame = ttk.Frame(alignment_frame)
        range_frame.grid(row=1, column=1, sticky="ew", pady=(2, 6))
        self.align_window_start_entry = ttk.Entry(
            range_frame, textvariable=self.align_window_start_var, width=8
        )
        self.align_window_start_entry.grid(row=0, column=0, sticky="w")
        self.align_window_start_entry.bind("<Return>", lambda _event: self.update_plot())
        self.align_window_start_entry.bind(
            "<FocusOut>", lambda _event: self.update_plot()
        )
        ttk.Label(range_frame, text="to").grid(row=0, column=1, sticky="w", padx=4)
        self.align_window_end_entry = ttk.Entry(
            range_frame, textvariable=self.align_window_end_var, width=8
        )
        self.align_window_end_entry.grid(row=0, column=2, sticky="w")
        self.align_window_end_entry.bind("<Return>", lambda _event: self.update_plot())
        self.align_window_end_entry.bind("<FocusOut>", lambda _event: self.update_plot())

        ttk.Label(
            alignment_frame,
            text=(
                "Raw time keeps each trace unchanged. Averaging-window start makes each "
                "trace's spreadsheet averaging segment begin at t=0. Peak alignment "
                "uses the chosen window below and moves each trace so that the largest "
                "peak in that window lands at t=0."
            ),
            wraplength=350,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 4))

        display_frame = ttk.LabelFrame(sidebar, text="Display")
        display_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(
            display_frame,
            text="Emphasize spreadsheet averaging segments",
            variable=self.show_avg_windows_var,
            command=self.update_plot,
        ).grid(row=0, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            display_frame,
            text="Draw average current level for each highlighted window",
            variable=self.show_avg_levels_var,
            command=self.update_plot,
        ).grid(row=1, column=0, sticky="w", pady=(4, 4))
        ttk.Label(
            display_frame,
            text=(
                "This uses the exact time span recorded in the spreadsheet notes, "
                "for example 'Used 35-60s no-LCD portion'. Each emphasized segment "
                "is drawn thicker in its own trace color, with start/end markers."
            ),
            wraplength=350,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(0, 4))

        title_frame = ttk.LabelFrame(sidebar, text="Plot Title")
        title_frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        title_frame.columnconfigure(0, weight=1)

        self.plot_title_entry = ttk.Entry(
            title_frame, textvariable=self.plot_title_var
        )
        self.plot_title_entry.grid(row=0, column=0, sticky="ew", pady=(4, 0))
        self.plot_title_entry.bind("<Return>", lambda _event: self.update_plot())
        self.plot_title_entry.bind("<FocusOut>", lambda _event: self.update_plot())

        ttk.Label(
            title_frame,
            text=(
                "Leave blank to use the automatic preset/manual title, or type a "
                "custom title for the chart."
            ),
            wraplength=350,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 4))

        chart_frame = ttk.LabelFrame(sidebar, text="Chart Size")
        chart_frame.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        chart_frame.columnconfigure(1, weight=1)

        ttk.Label(chart_frame, text="Width (in)").grid(row=0, column=0, sticky="w")
        self.chart_width_entry = ttk.Entry(
            chart_frame, textvariable=self.chart_width_var, width=10
        )
        self.chart_width_entry.grid(row=0, column=1, sticky="w", pady=(4, 0))
        self.chart_width_entry.bind("<Return>", lambda _event: self.apply_chart_size())
        self.chart_width_entry.bind(
            "<FocusOut>", lambda _event: self.apply_chart_size()
        )

        ttk.Label(chart_frame, text="Height (in)").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.chart_height_entry = ttk.Entry(
            chart_frame, textvariable=self.chart_height_var, width=10
        )
        self.chart_height_entry.grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.chart_height_entry.bind("<Return>", lambda _event: self.apply_chart_size())
        self.chart_height_entry.bind(
            "<FocusOut>", lambda _event: self.apply_chart_size()
        )

        ttk.Button(
            chart_frame, text="Apply Chart Size", command=self.apply_chart_size
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 4))

        ttk.Label(
            chart_frame,
            text=(
                "Set the embedded chart size in inches so you can match a report "
                "aspect ratio more closely."
            ),
            wraplength=350,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="w")

        ttk.Label(
            sidebar,
            textvariable=self.selection_count_var,
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=6, column=0, sticky="w", pady=(10, 0))

        ttk.Label(
            sidebar,
            textvariable=self.summary_var,
            wraplength=380,
            justify="left",
        ).grid(row=7, column=0, sticky="ew", pady=(6, 0))

        customization_frame = ttk.LabelFrame(
            sidebar, text="Legend Labels And Colors"
        )
        customization_frame.grid(row=8, column=0, sticky="ew", pady=(10, 0))
        customization_frame.columnconfigure(0, weight=1)
        self.customization_inner = ttk.Frame(customization_frame)
        self.customization_inner.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self.customization_inner.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(
            sidebar,
            textvariable=self.status_var,
            wraplength=380,
            justify="left",
            foreground="#444444",
        )
        self.status_label.grid(row=9, column=0, sticky="ew", pady=(10, 0))

        selection_frame = ttk.LabelFrame(sidebar, text="Manual Trace Selection")
        selection_frame.grid(row=10, column=0, sticky="ew", pady=(10, 0))
        selection_frame.columnconfigure(0, weight=1)

        shift_frame = ttk.Frame(selection_frame)
        shift_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(4, 6))
        shift_frame.columnconfigure(0, weight=1)

        self.manual_shift_target_combo = ttk.Combobox(
            shift_frame,
            textvariable=self.manual_shift_target_var,
            state="readonly",
            width=40,
        )
        self.manual_shift_target_combo.grid(row=0, column=0, sticky="ew")

        ttk.Button(
            shift_frame, text="Shift Left", command=lambda: self.shift_manual_target(-1)
        ).grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Button(
            shift_frame, text="Shift Right", command=lambda: self.shift_manual_target(1)
        ).grid(row=0, column=2, sticky="w", padx=(6, 0))
        ttk.Button(
            shift_frame, text="Reset Shift", command=self.reset_manual_shift_target
        ).grid(row=0, column=3, sticky="w", padx=(6, 0))

        ttk.Label(shift_frame, text="Step (s)").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.manual_shift_step_entry = ttk.Entry(
            shift_frame, textvariable=self.manual_shift_step_var, width=8
        )
        self.manual_shift_step_entry.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))

        self.selection_inner = ttk.Frame(selection_frame)
        self.selection_inner.columnconfigure(0, weight=1)
        self.selection_inner.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))

        for row_index, trace in enumerate(self.trace_records):
            ttk.Checkbutton(
                self.selection_inner,
                text=shorten_label(trace.label, 110),
                variable=self.trace_vars[trace.csv_path.name],
                command=self.on_selection_changed,
            ).grid(row=row_index, column=0, sticky="ew", padx=4, pady=2)

    def set_status(self, message: str, *, is_error: bool = False) -> None:
        self.status_var.set(message)
        if self.status_label is not None:
            self.status_label.configure(foreground="#aa0000" if is_error else "#444444")

    def get_series(self, filename: str) -> tuple[list[float], list[float]]:
        if filename not in self.trace_cache:
            trace = self.trace_by_filename[filename]
            self.trace_cache[filename] = load_csv_series(trace.csv_path)
        return self.trace_cache[filename]

    def get_selected_filenames(self) -> list[str]:
        return [
            trace.csv_path.name
            for trace in self.trace_records
            if self.trace_vars[trace.csv_path.name].get()
        ]

    def parse_alignment_window(self) -> tuple[float, float] | None:
        try:
            start_s = float(self.align_window_start_var.get().strip())
            end_s = float(self.align_window_end_var.get().strip())
        except ValueError:
            self.set_status("Alignment window start/end must be valid numbers.", is_error=True)
            self.root.bell()
            return None

        if start_s < 0.0 or end_s <= start_s:
            self.set_status(
                "Alignment window must satisfy 0 <= start < end.",
                is_error=True,
            )
            self.root.bell()
            return None

        return start_s, end_s

    def on_preset_selected(self, _event=None) -> None:
        self.update_summary()

    def get_manual_shift_target_label(self, filename: str) -> str:
        trace = self.trace_by_filename[filename]
        return f"[{trace.index:02d}] {shorten_label(trace.title, 52)}"

    def refresh_manual_shift_targets(self) -> None:
        selected_filenames = self.get_selected_filenames()
        self.manual_shift_display_to_filename = {
            self.get_manual_shift_target_label(filename): filename
            for filename in selected_filenames
        }
        values = list(self.manual_shift_display_to_filename)
        self.manual_shift_target_combo.configure(values=values)

        current_label = self.manual_shift_target_var.get()
        if current_label in self.manual_shift_display_to_filename:
            return
        if values:
            self.manual_shift_target_var.set(values[0])
        else:
            self.manual_shift_target_var.set("")

    def get_default_trace_label(self, filename: str) -> str:
        trace = self.trace_by_filename[filename]
        return f"[{trace.index:02d}] {trace.title}"

    def ensure_trace_style_vars(self, filenames: list[str]) -> None:
        default_colors = generate_distinct_random_colors(len(filenames))
        for filename, default_color in zip(filenames, default_colors):
            previous_default = self.default_trace_color_by_filename.get(filename)
            color_var = self.trace_color_var_by_filename.get(filename)
            if color_var is None:
                color_var = tk.StringVar(value=default_color)
                self.trace_color_var_by_filename[filename] = color_var
            elif previous_default is None or color_var.get().strip() == previous_default:
                color_var.set(default_color)
            self.default_trace_color_by_filename[filename] = default_color

            if filename not in self.trace_label_var_by_filename:
                self.trace_label_var_by_filename[filename] = tk.StringVar(
                    value=self.get_default_trace_label(filename)
                )
            if filename not in self.trace_order_var_by_filename:
                self.trace_order_var_by_filename[filename] = tk.StringVar(
                    value=str(self.trace_by_filename[filename].index)
                )

    def refresh_customization_controls(self) -> None:
        if self.customization_inner is None:
            return

        selected_filenames = self.get_selected_filenames()
        self.ensure_trace_style_vars(selected_filenames)

        for child in self.customization_inner.winfo_children():
            child.destroy()

        if not selected_filenames:
            ttk.Label(
                self.customization_inner,
                text="Select one or more traces to edit their legend labels and colors.",
                wraplength=340,
                justify="left",
            ).grid(row=0, column=0, sticky="w")
            return

        avg_frame = ttk.Frame(self.customization_inner)
        avg_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        avg_frame.columnconfigure(1, weight=1)

        ttk.Label(
            avg_frame,
            text="Overall average line",
            font=("TkDefaultFont", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(avg_frame, text="Color").grid(row=1, column=0, sticky="w", pady=(4, 0))
        avg_color_entry = ttk.Entry(
            avg_frame, textvariable=self.overall_avg_color_var, width=14
        )
        avg_color_entry.grid(row=1, column=1, sticky="ew", pady=(4, 0))

        ttk.Label(avg_frame, text="Legend label").grid(
            row=2, column=0, sticky="w", pady=(4, 0)
        )
        avg_label_entry = ttk.Entry(
            avg_frame, textvariable=self.overall_avg_label_var
        )
        avg_label_entry.grid(row=2, column=1, sticky="ew", pady=(4, 0))

        for widget in (avg_color_entry, avg_label_entry):
            widget.bind("<Return>", lambda _event: self.update_plot())
            widget.bind("<FocusOut>", lambda _event: self.update_plot())

        for row_index, filename in enumerate(selected_filenames, start=1):
            trace = self.trace_by_filename[filename]
            entry = self.entry_by_filename.get(filename)
            row_frame = ttk.Frame(self.customization_inner)
            row_frame.grid(row=row_index, column=0, sticky="ew", pady=(0, 8))
            row_frame.columnconfigure(1, weight=1)
            row_frame.columnconfigure(3, weight=0)

            ttk.Label(
                row_frame,
                text=f"[{trace.index:02d}] {shorten_label(trace.title, 48)}",
                font=("TkDefaultFont", 9, "bold"),
                wraplength=330,
                justify="left",
            ).grid(row=0, column=0, columnspan=2, sticky="w")

            ttk.Label(row_frame, text="Color").grid(row=1, column=0, sticky="w", pady=(4, 0))
            color_entry = ttk.Entry(
                row_frame,
                textvariable=self.trace_color_var_by_filename[filename],
                width=14,
            )
            color_entry.grid(row=1, column=1, sticky="ew", pady=(4, 0))

            ttk.Label(row_frame, text="Order").grid(
                row=1, column=2, sticky="w", padx=(8, 0), pady=(4, 0)
            )
            order_entry = ttk.Entry(
                row_frame,
                textvariable=self.trace_order_var_by_filename[filename],
                width=8,
            )
            order_entry.grid(row=1, column=3, sticky="w", pady=(4, 0))

            ttk.Label(row_frame, text="Trace label").grid(
                row=2, column=0, sticky="w", pady=(4, 0)
            )
            trace_label_entry = ttk.Entry(
                row_frame,
                textvariable=self.trace_label_var_by_filename[filename],
            )
            trace_label_entry.grid(row=2, column=1, sticky="ew", pady=(4, 0))

            note_text = "Full trace"
            if entry is not None and entry.windows:
                note_text = ", ".join(
                    f"{window.start_s:g}-{window.end_s:g}s" for window in entry.windows
                )
            ttk.Label(
                row_frame,
                text=f"Averaging segment: {note_text}",
                wraplength=330,
                justify="left",
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

            for widget in (color_entry, order_entry, trace_label_entry):
                widget.bind("<Return>", lambda _event: self.update_plot())
                widget.bind("<FocusOut>", lambda _event: self.update_plot())

    def get_resolved_trace_color(
        self, filename: str, warning_messages: list[str]
    ) -> str:
        fallback = self.default_trace_color_by_filename.get(filename, "#1f77b4")
        color_var = self.trace_color_var_by_filename.get(filename)
        raw_color = color_var.get().strip() if color_var is not None else fallback
        try:
            return mcolors.to_hex(mcolors.to_rgb(raw_color))
        except ValueError:
            warning_messages.append(
                f"{filename} has invalid color {raw_color!r}; using {fallback}."
            )
            if color_var is not None:
                color_var.set(fallback)
            return fallback

    def get_trace_label_text(self, filename: str) -> str:
        label_var = self.trace_label_var_by_filename.get(filename)
        if label_var is None:
            return self.get_default_trace_label(filename)
        text = label_var.get().strip()
        return text or self.get_default_trace_label(filename)

    def get_trace_draw_order_value(
        self, filename: str, warning_messages: list[str]
    ) -> float:
        order_var = self.trace_order_var_by_filename.get(filename)
        if order_var is None:
            return float(self.trace_by_filename[filename].index)

        raw_value = order_var.get().strip()
        if not raw_value:
            default_value = float(self.trace_by_filename[filename].index)
            order_var.set(str(self.trace_by_filename[filename].index))
            return default_value

        try:
            return float(raw_value)
        except ValueError:
            default_value = float(self.trace_by_filename[filename].index)
            warning_messages.append(
                f"{filename} has invalid order {raw_value!r}; using {default_value:g}."
            )
            order_var.set(str(self.trace_by_filename[filename].index))
            return default_value

    def get_overall_average_label_text(self) -> str:
        text = self.overall_avg_label_var.get().strip()
        return text or "Average current"

    def get_plot_title_text(self, preset: ModePreset | None, alignment_mode: str) -> str:
        custom_title = self.plot_title_var.get().strip()
        if custom_title:
            return custom_title

        title = "Selected current traces"
        if preset is not None:
            title = f"{preset.name} mode comparison"
        if alignment_mode != "Raw time":
            title += f" | {alignment_mode}"
        return title

    def get_resolved_average_color(self, warning_messages: list[str]) -> str:
        raw_color = self.overall_avg_color_var.get().strip() or "#111111"
        try:
            return mcolors.to_hex(mcolors.to_rgb(raw_color))
        except ValueError:
            fallback = "#111111"
            warning_messages.append(
                f"Overall average line has invalid color {raw_color!r}; using {fallback}."
            )
            self.overall_avg_color_var.set(fallback)
            return fallback

    def get_selection_average_line(
        self, selected_filenames: list[str]
    ) -> tuple[float | None, str]:
        preset = self.preset_lookup.get(self.preset_var.get().strip())
        if preset is not None:
            preset_filenames = {entry.filename for entry in preset.trace_entries}
            if (
                preset.weighted_mean_avg_current_a is not None
                and set(selected_filenames) == preset_filenames
            ):
                return preset.weighted_mean_avg_current_a, "preset spreadsheet weighted mean"

        total_area = 0.0
        total_duration = 0.0
        for filename in selected_filenames:
            times, currents = self.get_series(filename)
            entry = self.entry_by_filename.get(filename)
            averaging_windows = (
                entry.windows
                if entry is not None and entry.windows
                else [AveragingWindow(start_s=times[0], end_s=times[-1], source="Full trace")]
            )
            for averaging_window in averaging_windows:
                window_times, window_currents = extract_window_series(
                    times,
                    currents,
                    averaging_window.start_s,
                    averaging_window.end_s,
                )
                if len(window_times) < 2:
                    continue
                total_area += integrate_trapezoid(window_times, window_currents)
                total_duration += window_times[-1] - window_times[0]

        if total_duration <= 0.0:
            return None, "no valid averaging window data"
        return total_area / total_duration, "combined selected windowed average"

    def parse_manual_shift_step(self) -> float | None:
        raw_step = self.manual_shift_step_var.get().strip()
        try:
            step_s = float(raw_step)
        except ValueError:
            self.set_status("Manual shift step must be a valid number in seconds.", is_error=True)
            self.root.bell()
            return None

        if step_s <= 0.0:
            self.set_status("Manual shift step must be greater than 0 s.", is_error=True)
            self.root.bell()
            return None

        return step_s

    def parse_chart_size(self) -> tuple[float, float] | None:
        try:
            width_in = float(self.chart_width_var.get().strip())
            height_in = float(self.chart_height_var.get().strip())
        except ValueError:
            self.set_status("Chart width/height must be valid numbers in inches.", is_error=True)
            self.root.bell()
            return None

        if width_in <= 0.0 or height_in <= 0.0:
            self.set_status("Chart width/height must be greater than 0.", is_error=True)
            self.root.bell()
            return None

        return width_in, height_in

    def apply_chart_size(self) -> None:
        chart_size = self.parse_chart_size()
        if chart_size is None:
            return

        width_in, height_in = chart_size
        self.figure.set_size_inches(width_in, height_in, forward=True)
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.configure(
            width=max(200, int(width_in * self.figure.dpi)),
            height=max(160, int(height_in * self.figure.dpi)),
        )
        self.canvas.draw_idle()
        self.set_status(
            f"Chart size set to {width_in:.3g} x {height_in:.3g} inches."
        )

    def get_manual_shift_target_filename(self) -> str | None:
        target_label = self.manual_shift_target_var.get().strip()
        if not target_label:
            self.set_status("Choose a selected trace as the manual shift target.", is_error=True)
            self.root.bell()
            return None
        filename = self.manual_shift_display_to_filename.get(target_label)
        if filename is None:
            self.set_status(
                "The chosen manual shift target is no longer selected.",
                is_error=True,
            )
            self.root.bell()
            return None
        return filename

    def shift_manual_target(self, direction: int) -> None:
        filename = self.get_manual_shift_target_filename()
        if filename is None:
            return

        step_s = self.parse_manual_shift_step()
        if step_s is None:
            return

        shift_delta = direction * step_s
        new_offset = self.manual_offsets_s.get(filename, 0.0) + shift_delta
        self.manual_offsets_s[filename] = new_offset
        trace = self.trace_by_filename[filename]
        self.update_summary()
        self.update_plot()
        self.set_status(
            f"Manual shift for [{trace.index:02d}] {trace.title} is now {format_signed_seconds(new_offset)}."
        )

    def reset_manual_shift_target(self) -> None:
        filename = self.get_manual_shift_target_filename()
        if filename is None:
            return

        self.manual_offsets_s[filename] = 0.0
        trace = self.trace_by_filename[filename]
        self.update_summary()
        self.update_plot()
        self.set_status(f"Reset manual shift for [{trace.index:02d}] {trace.title}.")

    def apply_preset(self) -> None:
        preset_name = self.preset_var.get().strip()
        preset = self.preset_lookup.get(preset_name)
        if preset is None:
            self.set_status("No spreadsheet preset is selected.")
            return

        selected_filenames = {entry.filename for entry in preset.trace_entries}
        for filename, variable in self.trace_vars.items():
            variable.set(filename in selected_filenames)

        self.on_selection_changed()
        self.update_plot()
        self.set_status(
            f"Selected {len(selected_filenames)} traces from the {preset.name} spreadsheet preset."
        )

    def select_all(self) -> None:
        for variable in self.trace_vars.values():
            variable.set(True)
        self.on_selection_changed()

    def clear_selection(self) -> None:
        for variable in self.trace_vars.values():
            variable.set(False)
        self.on_selection_changed()
        self.update_plot()

    def on_selection_changed(self) -> None:
        count = len(self.get_selected_filenames())
        self.selection_count_var.set(f"Selected traces: {count}")
        self.refresh_manual_shift_targets()
        self.refresh_customization_controls()
        self.update_summary()

    def update_summary(self) -> None:
        selected_filenames = self.get_selected_filenames()
        preset = self.preset_lookup.get(self.preset_var.get().strip())

        lines: list[str] = []
        if preset is not None:
            lines.append(f"Preset: {preset.name}")
            if preset.description:
                lines.append(preset.description)
            if preset.weighted_mean_avg_current_a is not None:
                lines.append(
                    "Weighted mean current: "
                    f"{format_current(preset.weighted_mean_avg_current_a)}"
                )
            if preset.weighted_mean_charge_mc is not None:
                lines.append(
                    "Weighted mean charge: "
                    f"{format_charge_mc(preset.weighted_mean_charge_mc)}"
                )
            if preset.weighted_mean_notes:
                lines.append(f"Weighted mean note: {preset.weighted_mean_notes}")

        if selected_filenames:
            average_value_a, average_source = self.get_selection_average_line(
                selected_filenames
            )
            lines.append(
                "Displayed average line: "
                + (
                    f"{format_current(average_value_a)} ({average_source})"
                    if average_value_a is not None
                    else f"- ({average_source})"
                )
            )
            lines.append("")
            lines.append("Selected traces:")
            for filename in selected_filenames:
                trace = self.trace_by_filename[filename]
                entry = self.entry_by_filename.get(filename)
                line = f"[{trace.index:02d}] {shorten_label(trace.title, 58)}"
                if entry is not None and entry.avg_current_a is not None:
                    line += f" | avg {format_current(entry.avg_current_a)}"
                if entry is not None and entry.charge_mc is not None:
                    line += f" | charge {format_charge_mc(entry.charge_mc)}"
                if entry is not None and entry.windows:
                    window_parts = [
                        f"{window.start_s:g}-{window.end_s:g}s" for window in entry.windows
                    ]
                    line += f" | window {', '.join(window_parts)}"
                elif entry is not None and entry.uses_full_trace:
                    line += " | full trace"
                manual_shift = self.manual_offsets_s.get(filename, 0.0)
                if not math.isclose(manual_shift, 0.0, rel_tol=0.0, abs_tol=1e-12):
                    line += f" | manual shift {format_signed_seconds(manual_shift)}"
                order_var = self.trace_order_var_by_filename.get(filename)
                if order_var is not None:
                    line += f" | order {order_var.get().strip() or self.trace_by_filename[filename].index}"
                lines.append(line)

        if not lines:
            lines.append(
                "Choose a spreadsheet preset or tick traces manually, then press "
                "'Plot Selected'."
            )

        self.summary_var.set("\n".join(lines))

    def compute_alignment_offset(
        self,
        filename: str,
        times: list[float],
        currents: list[float],
        alignment_window: tuple[float, float] | None,
    ) -> tuple[float, str | None]:
        mode = self.alignment_mode_var.get()
        entry = self.entry_by_filename.get(filename)

        if mode == "Raw time":
            return 0.0, None

        if mode == "Align averaging window start":
            if entry is not None and entry.windows:
                return entry.windows[0].start_s, None
            return times[0], f"{filename} has no spreadsheet window; used trace start."

        if alignment_window is None:
            return 0.0, "Alignment window is required for the chosen alignment mode."

        window_start, window_end = alignment_window
        if mode == "Align peak in chosen window":
            peak_time = find_peak_time(times, currents, window_start, window_end)
            if peak_time is None:
                return times[0], f"{filename} has no samples in the chosen alignment window."
            return peak_time, None

        return 0.0, None

    def set_group_visibility(
        self, group_key: tuple[str, str], visible: bool
    ) -> None:
        self.group_visibility[group_key] = visible
        for artist in self.group_key_to_artists.get(group_key, []):
            artist.set_visible(visible)
        self.sync_legend_entry(group_key)

    def sync_legend_entry(self, group_key: tuple[str, str]) -> None:
        legend_artists = self.group_key_to_legend_artists.get(group_key)
        if legend_artists is None:
            return
        visible = self.group_visibility.get(group_key, True)
        alpha = 1.0 if visible else 0.2
        legend_handle, legend_text = legend_artists
        if hasattr(legend_handle, "set_alpha"):
            legend_handle.set_alpha(alpha)
        if hasattr(legend_text, "set_alpha"):
            legend_text.set_alpha(alpha)

    def on_plot_pick(self, event) -> None:
        group_key = self.legend_artist_to_group.get(event.artist)
        if group_key is None:
            return
        current_visible = self.group_visibility.get(group_key, True)
        self.set_group_visibility(group_key, not current_visible)
        self.canvas.draw_idle()

    def update_plot(self) -> None:
        selected_filenames = self.get_selected_filenames()
        self.ax.clear()
        self.legend_artist_to_group = {}
        self.group_key_to_artists = {}
        self.group_key_to_legend_artists = {}

        if not selected_filenames:
            self.ax.set_title("No traces selected")
            self.ax.set_xlabel("Time (s)")
            self.ax.set_ylabel("Current (A)")
            self.ax.grid(True, alpha=0.3)
            self.canvas.draw_idle()
            return

        alignment_mode = self.alignment_mode_var.get()
        alignment_window: tuple[float, float] | None = None
        if alignment_mode == "Align peak in chosen window":
            alignment_window = self.parse_alignment_window()
            if alignment_window is None:
                return

        average_value_a, average_source = self.get_selection_average_line(
            selected_filenames
        )
        legend_group_keys: list[tuple[str, str]] = []
        warning_messages: list[str] = []
        ordered_trace_entries = sorted(
            [
                (
                    self.get_trace_draw_order_value(filename, warning_messages),
                    self.trace_by_filename[filename].index,
                    filename,
                )
                for filename in selected_filenames
            ],
            key=lambda item: (item[0], item[1]),
        )
        max_trace_draw_order = (
            max(entry[0] for entry in ordered_trace_entries)
            if ordered_trace_entries
            else 0.0
        )

        for draw_order, _trace_index, filename in ordered_trace_entries:
            trace = self.trace_by_filename[filename]
            times, currents = self.get_series(filename)
            color = self.get_resolved_trace_color(filename, warning_messages)
            alignment_offset, warning = self.compute_alignment_offset(
                filename, times, currents, alignment_window
            )
            if warning:
                warning_messages.append(warning)
            manual_offset = self.manual_offsets_s.get(filename, 0.0)
            aligned_times = [time - alignment_offset + manual_offset for time in times]

            trace_group_key = ("trace", filename)
            (base_line,) = self.ax.plot(
                aligned_times,
                currents,
                color=color,
                linewidth=1.0,
                alpha=0.45 if self.show_avg_windows_var.get() else 0.9,
                label=self.get_trace_label_text(filename),
                zorder=2.0 + draw_order,
            )
            trace_artists: list[object] = [base_line]
            legend_group_keys.append(trace_group_key)

            entry = self.entry_by_filename.get(filename)
            if entry is not None and self.show_avg_windows_var.get():
                highlight_windows = (
                    entry.windows
                    if entry.windows
                    else [
                        AveragingWindow(
                            start_s=times[0], end_s=times[-1], source="Full trace"
                        )
                    ]
                )
                for highlight_window in highlight_windows:
                    segment_times, segment_currents = extract_window_series(
                        times,
                        currents,
                        highlight_window.start_s,
                        highlight_window.end_s,
                    )
                    if not segment_times:
                        continue

                    segment_times = [
                        time - alignment_offset + manual_offset
                        for time in segment_times
                    ]
                    (segment_line,) = self.ax.plot(
                        segment_times,
                        segment_currents,
                        color=color,
                        linewidth=2.2,
                        alpha=0.95,
                        zorder=3.0 + draw_order,
                    )
                    trace_artists.append(segment_line)

            self.group_key_to_artists[trace_group_key] = trace_artists
            self.group_visibility.setdefault(trace_group_key, True)

        if self.show_avg_levels_var.get() and average_value_a is not None:
            overall_average_group_key = ("overall_average", "__selection__")
            average_line = self.ax.axhline(
                average_value_a,
                color=self.get_resolved_average_color(warning_messages),
                linestyle="--",
                linewidth=1.6,
                alpha=0.95,
                label="_nolegend_",
                zorder=max_trace_draw_order + 1000.0,
            )
            self.group_key_to_artists[overall_average_group_key] = [average_line]
            self.group_visibility.setdefault(overall_average_group_key, True)

        preset = self.preset_lookup.get(self.preset_var.get().strip())
        self.ax.set_title(self.get_plot_title_text(preset, alignment_mode))
        self.ax.set_xlabel("Aligned time (s)" if alignment_mode != "Raw time" else "Time (s)")
        self.ax.set_ylabel("Current (A)")
        self.ax.grid(True, alpha=0.3)
        self.ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

        if legend_group_keys:
            legend = self.ax.legend(
                loc="upper right",
                fontsize=7,
                frameon=True,
                ncol=2 if len(legend_group_keys) > 12 else 1,
                borderaxespad=0.6,
                handlelength=1.8,
            )
            legend.set_draggable(True)
            legend_handles = getattr(legend, "legend_handles", None)
            if legend_handles is None:
                legend_handles = getattr(legend, "legendHandles", [])
            legend_texts = legend.get_texts()
            for group_key, legend_handle, legend_text in zip(
                legend_group_keys, legend_handles, legend_texts
            ):
                if hasattr(legend_handle, "set_picker"):
                    legend_handle.set_picker(True)
                if hasattr(legend_handle, "set_pickradius"):
                    legend_handle.set_pickradius(8)
                if hasattr(legend_text, "set_picker"):
                    legend_text.set_picker(True)
                self.legend_artist_to_group[legend_handle] = group_key
                self.legend_artist_to_group[legend_text] = group_key
                self.group_key_to_legend_artists[group_key] = (legend_handle, legend_text)
                self.set_group_visibility(group_key, self.group_visibility.get(group_key, True))

        if warning_messages:
            unique_messages = []
            seen = set()
            for message in warning_messages:
                if message not in seen:
                    unique_messages.append(message)
                    seen.add(message)
            self.set_status(" | ".join(unique_messages[:4]))
        else:
            self.set_status(
                "Windows are read from the spreadsheet notes, not calculated here. "
                f"The single average line is the {average_source}. Click legend items "
                "to hide/show either a trace or the average line. You can also drag "
                "the legend inside the plot."
            )

        self.canvas.draw_idle()


def main() -> int:
    args = parse_args()
    spreadsheet_path = args.spreadsheet.resolve()
    if not spreadsheet_path.exists():
        raise SystemExit(f"Spreadsheet not found: {spreadsheet_path}")

    root = tk.Tk()
    ModeTraceComparisonApp(root, spreadsheet_path, args.sheet)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
