#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from plot_current_logs import DATA_DIR, TITLE_BY_FILE, load_csv_series


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open all VirtualBench current logs on one interactive figure."
    )
    parser.add_argument(
        "--mapped-only",
        action="store_true",
        help="Only include CSVs that have a provided title mapping.",
    )
    parser.add_argument(
        "--max-label-length",
        type=int,
        default=72,
        help="Maximum legend label length before truncation. Default: 72",
    )
    return parser.parse_args()


def build_trace_list(mapped_only: bool) -> list[tuple[Path, str]]:
    traces: list[tuple[Path, str]] = []
    for csv_path in sorted(DATA_DIR.glob("current_log_*.csv")):
        if mapped_only and csv_path.name not in TITLE_BY_FILE:
            continue
        traces.append((csv_path, TITLE_BY_FILE.get(csv_path.name, csv_path.stem)))
    return traces


def shorten_label(label: str, max_length: int) -> str:
    if max_length < 8 or len(label) <= max_length:
        return label
    return f"{label[: max_length - 3]}..."


def set_all_visibility(lines, visible: bool) -> None:
    for line in lines:
        line.set_visible(visible)


def sync_legend_entry(line, legend_handle, legend_text) -> None:
    alpha = 1.0 if line.get_visible() else 0.2
    legend_handle.set_alpha(alpha)
    legend_text.set_alpha(alpha)


def main() -> int:
    args = parse_args()
    traces = build_trace_list(args.mapped_only)
    if not traces:
        raise SystemExit("No current_log CSV files matched the requested filters.")

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.subplots_adjust(left=0.07, right=0.63, bottom=0.08, top=0.92)

    try:
        fig.canvas.manager.set_window_title("VirtualBench Current Logs")
    except Exception:
        pass

    cmap = plt.get_cmap("nipy_spectral")
    lines = []
    display_labels: list[str] = []

    for index, (csv_path, full_label) in enumerate(traces, start=1):
        times, currents = load_csv_series(csv_path)
        color = cmap((index - 1) / max(1, len(traces) - 1))
        display_label = f"[{index:02d}] {shorten_label(full_label, args.max_label_length)}"
        (line,) = ax.plot(
            times,
            currents,
            linewidth=1.0,
            alpha=0.9,
            color=color,
            label=display_label,
        )
        lines.append(line)
        display_labels.append(display_label)
        print(f"[{index:02d}] {csv_path.name} | {full_label}")

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Current (A)")
    ax.set_title("VirtualBench current logs")
    ax.grid(True, alpha=0.3)
    ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

    legend = ax.legend(
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        fontsize=7,
        frameon=True,
        ncol=1,
        borderaxespad=0.0,
        handlelength=1.8,
    )

    legend_handles = legend.legend_handles
    legend_texts = legend.get_texts()
    artist_to_line = {}
    line_to_legend = {}

    for line, legend_handle, legend_text in zip(lines, legend_handles, legend_texts):
        legend_handle.set_picker(True)
        legend_handle.set_pickradius(8)
        legend_text.set_picker(True)
        artist_to_line[legend_handle] = line
        artist_to_line[legend_text] = line
        line_to_legend[line] = (legend_handle, legend_text)
        sync_legend_entry(line, legend_handle, legend_text)

    def redraw() -> None:
        for plot_line, (legend_handle, legend_text) in line_to_legend.items():
            sync_legend_entry(plot_line, legend_handle, legend_text)
        fig.canvas.draw_idle()

    def isolate_line(target_line) -> None:
        for plot_line in lines:
            plot_line.set_visible(plot_line is target_line)

    def on_pick(event) -> None:
        picked_line = artist_to_line.get(event.artist)
        if picked_line is None:
            return

        mouse_button = getattr(event.mouseevent, "button", None)
        if mouse_button == 3:
            isolate_line(picked_line)
        else:
            picked_line.set_visible(not picked_line.get_visible())
        redraw()

    def on_key_press(event) -> None:
        if event.key == "a":
            set_all_visibility(lines, True)
        elif event.key == "n":
            set_all_visibility(lines, False)
        elif event.key == "i":
            for line in lines:
                line.set_visible(not line.get_visible())
        else:
            return
        redraw()

    fig.canvas.mpl_connect("pick_event", on_pick)
    fig.canvas.mpl_connect("key_press_event", on_key_press)

    fig.text(
        0.07,
        0.02,
        "Click a legend item to toggle a trace. Right-click a legend item to isolate it. "
        "Press 'a' to show all, 'n' to hide all, and 'i' to invert visibility.",
        fontsize=9,
    )

    plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
