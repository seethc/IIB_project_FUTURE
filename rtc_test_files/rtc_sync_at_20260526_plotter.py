import argparse
import os

import numpy as np
import pandas as pd


DEFAULT_RUN_DIR = "20260526"
DEFAULT_AT_FILES = (
    "ATprocessed1.csv",
    "ATprocessed2.csv",
    "ATprocessed3.csv",
    "ATprocessed4.csv",
)
DATASET_LABELS = {
    "ATprocessed1.csv": "6 hour ambient temp. test (~20 C)",
    "ATprocessed2.csv": "1 hour direct sunlight test",
    "ATprocessed3.csv": "15 hour warm temp. test (~30 C)",
    "ATprocessed4.csv": "26 hour ambient temp. test",
}
SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60
REFERENCE_DRIFTS = (
    ("30 sec/year", 30, "red"),
    ("30 min/year", 30 * 60, "blue"),
    ("12 hours/year", 12 * 60 * 60, "green"),
    ("1 day/year", 24 * 60 * 60, "gold"),
)


def find_time_columns(df):
    df.columns = df.columns.str.strip()
    x_col = next((col for col in df.columns if "utc elapsed" in col.lower()), df.columns[0])
    y_col = next((col for col in df.columns if col != x_col), df.columns[1])
    return x_col, y_col


def load_elapsed_csv(path):
    df = pd.read_csv(path)
    x_col, y_col = find_time_columns(df)

    df = df[[x_col, y_col]].copy()
    df[x_col] = pd.to_numeric(df[x_col], errors="coerce").astype(float)
    df[y_col] = pd.to_numeric(df[y_col], errors="coerce").astype(float)
    df = df.dropna().sort_values(x_col)
    df = df.drop_duplicates(subset=x_col, keep="first").reset_index(drop=True)
    return df, x_col, y_col


def remove_initial_offset(df, x_col, y_col):
    df = df.copy()
    positive_elapsed = df[y_col] > 0

    if positive_elapsed.any():
        start_idx = positive_elapsed.idxmax()
        offset = df.loc[start_idx, y_col] - df.loc[start_idx, x_col]
        df.loc[start_idx:, y_col] = df.loc[start_idx:, y_col] - offset

    return df


def load_clock_drift(path, align_initial_offset=True):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Could not find {path}")

    df, x_col, y_col = load_elapsed_csv(path)
    if align_initial_offset:
        df = remove_initial_offset(df, x_col, y_col)

    utc_elapsed = df[x_col].to_numpy()
    at_elapsed = df[y_col].to_numpy()
    drift = at_elapsed - utc_elapsed
    return utc_elapsed, at_elapsed, drift


def sample_time_weights(x):
    if len(x) == 1:
        return np.ones_like(x)

    weights = np.empty_like(x)
    weights[0] = max((x[1] - x[0]) / 2, 0)
    weights[-1] = max((x[-1] - x[-2]) / 2, 0)
    if len(x) > 2:
        weights[1:-1] = np.maximum((x[2:] - x[:-2]) / 2, 0)
    return weights


def estimate_constant_drift_rate(x, drift):
    valid = x > 0
    x = x[valid]
    drift = drift[valid]

    if len(x) == 0:
        return 0.0

    weights = sample_time_weights(x)
    denominator = np.sum(weights * x * x)
    if denominator == 0:
        return 0.0

    return np.sum(weights * x * drift) / denominator


def calculate_percent_error(x, drift):
    valid = x > 0
    return x[valid], (drift[valid] / x[valid]) * 100


def test_duration_label(path, at_elapsed):
    filename = os.path.basename(path)
    if filename in DATASET_LABELS:
        return DATASET_LABELS[filename]

    hours = max(1, round(at_elapsed.max() / 3600))
    return f"{os.path.splitext(filename)[0]} ({hours} hour test)"


def plot_reference_lines(ax_drift, ax_percent, x_max):
    reference_x = np.array([0, x_max])

    for label, drift_after_year, color in REFERENCE_DRIFTS:
        slope = drift_after_year / SECONDS_PER_YEAR
        percent_error = slope * 100
        ax_drift.plot(
            reference_x,
            slope * reference_x,
            color=color,
            linestyle="--",
            linewidth=1.8,
            alpha=0.9,
            label=label,
        )
        ax_percent.axhline(
            percent_error,
            color=color,
            linestyle="--",
            linewidth=1.8,
            alpha=0.9,
            label=label,
        )


def find_at_files(at_paths, at_dir):
    if at_paths:
        return at_paths

    paths = [os.path.join(at_dir, filename) for filename in DEFAULT_AT_FILES]
    missing = [path for path in paths if not os.path.exists(path)]
    if missing:
        missing_text = ", ".join(missing)
        raise FileNotFoundError(f"Could not find required file(s): {missing_text}")
    return paths


def plot_at_files(at_paths, output_path, show=True, align_initial_offset=False):
    import matplotlib.pyplot as plt
    from matplotlib.widgets import CheckButtons

    fig, (ax_drift, ax_percent) = plt.subplots(
        2,
        1,
        figsize=(12, 10),
        sharex=True,
    )
    fig.subplots_adjust(left=0.1, right=0.76, top=0.95, bottom=0.08, hspace=0.35)
    checkbox_ax = fig.add_axes([0.79, 0.68, 0.19, 0.22])
    checkbox_ax.set_title("Datasets", fontsize=10)
    datasets = []
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]

    for index, at_path in enumerate(at_paths):
        x, at_elapsed, drift = load_clock_drift(
            at_path,
            align_initial_offset=align_initial_offset,
        )
        percent_x, percent_error = calculate_percent_error(x, drift)
        datasets.append(
            {
                "path": at_path,
                "label": test_duration_label(at_path, at_elapsed),
                "x": x,
                "at_elapsed": at_elapsed,
                "drift": drift,
                "percent_x": percent_x,
                "percent_error": percent_error,
                "color": color_cycle[index % len(color_cycle)],
                "selected": True,
            }
        )

    checkbox = CheckButtons(
        checkbox_ax,
        [dataset["label"] for dataset in datasets],
        [dataset["selected"] for dataset in datasets],
    )
    for label, dataset in zip(checkbox.labels, datasets):
        label.set_fontsize(8)
        label.set_color(dataset["color"])

    def selected_datasets():
        return [dataset for dataset in datasets if dataset["selected"]]

    def draw_plot():
        ax_drift.clear()
        ax_percent.clear()

        selected = selected_datasets()
        if not selected:
            ax_drift.text(
                0.5,
                0.5,
                "Select at least one dataset",
                transform=ax_drift.transAxes,
                ha="center",
                va="center",
            )
            ax_drift.set_title("20260526 AT Clock Drift", pad=6)
            ax_percent.set_title("20260526 AT % Error", pad=6)
            fig.canvas.draw_idle()
            return

        all_x = []
        all_drift = []

        for dataset in selected:
            ax_drift.scatter(
                dataset["x"],
                dataset["drift"],
                s=18,
                alpha=0.45,
                color=dataset["color"],
                label=dataset["label"],
            )
            ax_percent.scatter(
                dataset["percent_x"],
                dataset["percent_error"],
                s=18,
                alpha=0.45,
                color=dataset["color"],
                label=dataset["label"],
            )
            all_x.append(dataset["x"])
            all_drift.append(dataset["drift"])

        all_x = np.concatenate(all_x)
        all_drift = np.concatenate(all_drift)

        drift_rate = estimate_constant_drift_rate(all_x, all_drift)
        fit_x = np.array([0, all_x.max()])
        fitted_drift = drift_rate * fit_x
        slope_sec_per_hour = drift_rate * 3600
        slope_ppm = drift_rate * 1_000_000
        percent_error = drift_rate * 100
        fit_label = f"Average Error: {slope_sec_per_hour:.3f} sec/hour, {slope_ppm:.1f} ppm"

        ax_drift.plot(fit_x, fitted_drift, color="black", linewidth=2.5, label=fit_label)

        ax_percent.axhline(
            percent_error,
            color="black",
            linewidth=2.5,
            label=f"Average % error ({slope_ppm:.1f} ppm)",
        )
        plot_reference_lines(ax_drift, ax_percent, all_x.max())

        ax_drift.axhline(0, color="black", linewidth=1, alpha=0.5)
        ax_drift.set_xlabel("UTC Elapsed (s)", labelpad=4)
        ax_drift.set_ylabel("Clock Drift\n(AT elapsed - UTC elapsed) (s)", labelpad=6)
        ax_drift.set_title("20260526 AT Clock Drift from CSV Columns", pad=6)
        ax_drift.grid(True, alpha=0.35)

        ax_percent.axhline(0, color="black", linewidth=1, alpha=0.5)
        ax_percent.set_xlabel("UTC Elapsed (s)", labelpad=4)
        ax_percent.set_ylabel("% error", labelpad=6)
        ax_percent.set_title("20260526 AT % Error", pad=6)
        ax_percent.grid(True, alpha=0.35)

        ax_drift.relim()
        ax_drift.autoscale_view()
        ax_percent.relim()
        ax_percent.autoscale_view()

        drift_handles, drift_labels = ax_drift.get_legend_handles_labels()
        ax_drift.legend(
            drift_handles,
            drift_labels,
            title="Test run",
            fontsize=8,
        )
        ax_percent.legend(title="Test run", fontsize=8)
        fig.canvas.draw_idle()

    def on_dataset_toggled(label):
        for dataset in datasets:
            if dataset["label"] == label:
                dataset["selected"] = not dataset["selected"]
                break
        draw_plot()

    checkbox.on_clicked(on_dataset_toggled)
    draw_plot()

    if output_path:
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
        print(f"Saved plot to {output_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_at_dir = os.path.join(script_dir, DEFAULT_RUN_DIR)

    parser = argparse.ArgumentParser(
        description="Plot clock drift from ATprocessed CSV files in rtc_test_files/20260526."
    )
    parser.add_argument(
        "--at",
        nargs="+",
        help="Specific ATprocessed CSV path(s). Defaults to every ATprocessed*.csv in 20260526.",
    )
    parser.add_argument(
        "--at-dir",
        default=default_at_dir,
        help="Directory containing ATprocessed CSV files.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional PNG output path. If omitted, no PNG is saved.",
    )
    parser.add_argument(
        "--align-initial-offset",
        action="store_true",
        help="Align the first positive AT elapsed value to UTC elapsed before plotting.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open the Matplotlib window.",
    )

    args = parser.parse_args()
    at_paths = find_at_files(args.at, args.at_dir)
    plot_at_files(
        at_paths,
        args.output or None,
        show=not args.no_show,
        align_initial_offset=args.align_initial_offset,
    )


if __name__ == "__main__":
    main()
