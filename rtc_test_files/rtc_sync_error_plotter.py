import argparse
import os

import numpy as np
import pandas as pd


DEFAULT_RUNS = ("20260305", "20260304_1", "20260304_2", "20260303_2")
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


def calculate_error(run_dir, align_initial_offset=True):
    totp_path = os.path.join(run_dir, "TOTPprocessed.csv")
    at_path = os.path.join(run_dir, "ATprocessed.csv")

    if not os.path.exists(totp_path):
        raise FileNotFoundError(f"Could not find {totp_path}")
    if not os.path.exists(at_path):
        raise FileNotFoundError(f"Could not find {at_path}")

    totp_df, totp_x, totp_y = load_elapsed_csv(totp_path)
    at_df, at_x, at_y = load_elapsed_csv(at_path)

    if align_initial_offset:
        totp_df = remove_initial_offset(totp_df, totp_x, totp_y)
        at_df = remove_initial_offset(at_df, at_x, at_y)

    overlap_start = max(totp_df[totp_x].min(), at_df[at_x].min())
    overlap_end = min(totp_df[totp_x].max(), at_df[at_x].max())
    at_overlap = at_df[(at_df[at_x] >= overlap_start) & (at_df[at_x] <= overlap_end)].copy()

    if at_overlap.empty:
        raise ValueError(f"No overlapping UTC elapsed range in {run_dir}")

    totp_at_at_samples = np.interp(
        at_overlap[at_x].to_numpy(),
        totp_df[totp_x].to_numpy(),
        totp_df[totp_y].to_numpy(),
    )

    error = totp_at_at_samples - at_overlap[at_y].to_numpy()
    return at_overlap[at_x].to_numpy(), error


def test_duration_label(x):
    hours = max(1, round(x.max() / 3600))
    return f"{hours} hour test"


def fit_polynomial(x, y, order):
    x_center = x - x.mean()
    x_scale = max(np.abs(x_center).max(), 1.0)
    x_normalised = x_center / x_scale
    coefficients = np.polyfit(x_normalised, y, order)
    return np.poly1d(coefficients), x.mean(), x_scale


def calculate_percent_error(x, error):
    valid = x > 0
    return x[valid], (error[valid] / x[valid]) * 100


def plot_reference_lines(ax_error, ax_percent, x_max):
    reference_x = np.array([0, x_max])

    for label, drift_after_year, color in REFERENCE_DRIFTS:
        slope = drift_after_year / SECONDS_PER_YEAR
        percent_error = slope * 100
        ax_error.plot(
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


def plot_runs(base_dir, runs, output_path, fit_order=4, show=True, align_initial_offset=True):
    import matplotlib.pyplot as plt

    fig, (ax_error, ax_percent) = plt.subplots(
        2,
        1,
        figsize=(12, 10),
        sharex=True,
        constrained_layout=True,
    )
    fig.set_constrained_layout_pads(w_pad=0.04, h_pad=0.04, hspace=0.06)
    ax_ppm = None if fit_order == 1 else ax_error.twinx()
    all_x = []
    all_error = []
    all_percent_x = []
    all_percent_error = []

    for run in runs:
        run_dir = os.path.join(base_dir, run)
        x, error = calculate_error(
            run_dir,
            align_initial_offset=align_initial_offset,
        )
        label = test_duration_label(x)
        error_points = ax_error.scatter(x, error, s=8, alpha=0.22, label=label)
        percent_x, percent_error = calculate_percent_error(x, error)
        color = error_points.get_facecolors()[0]
        ax_percent.scatter(percent_x, percent_error, s=8, alpha=0.22, color=color, label=label)
        all_x.append(x)
        all_error.append(error)
        all_percent_x.append(percent_x)
        all_percent_error.append(percent_error)

    all_x = np.concatenate(all_x)
    all_error = np.concatenate(all_error)
    all_percent_x = np.concatenate(all_percent_x)
    all_percent_error = np.concatenate(all_percent_error)

    polynomial, x_mean, x_scale = fit_polynomial(all_x, all_error, fit_order)
    fit_x = np.linspace(all_x.min(), all_x.max(), 1000)
    fit_x_normalised = (fit_x - x_mean) / x_scale
    fitted_error = polynomial(fit_x_normalised)
    fit_gradient = polynomial.deriv()(fit_x_normalised) / x_scale

    if fit_order == 1:
        slope_sec_per_hour = fit_gradient[0] * 3600
        slope_ppm = fit_gradient[0] * 1_000_000
        fit_label = f"Average Error: {slope_sec_per_hour:.3f} sec/hour"
    else:
        fit_label = f"Average Error (order {fit_order})"

    ax_error.plot(
        fit_x,
        fitted_error,
        color="black",
        linewidth=2.5,
        label=fit_label,
    )
    if ax_ppm:
        fitted_ppm = fit_gradient * 1_000_000
        ax_ppm.plot(
            fit_x,
            fitted_ppm,
            color="darkgreen",
            linewidth=2,
            linestyle="--",
            label="Average error in ppm",
        )

    ax_error.axhline(0, color="black", linewidth=1, alpha=0.5)
    ax_error.set_xlabel("UTC Elapsed (s)", labelpad=4)
    ax_error.set_ylabel("Clock Drift\n(RPi/Unix time - ATtiny time) (s)", labelpad=6)
    if ax_ppm:
        ax_ppm.axhline(0, color="darkgreen", linewidth=1, alpha=0.25)
        ax_ppm.set_ylabel("Clock error (ppm)", labelpad=6)
    ax_error.set_title("RTC Synchronisation Average Error", pad=6)
    ax_error.grid(True, alpha=0.35)

    percent_polynomial, percent_x_mean, percent_x_scale = fit_polynomial(
        all_percent_x,
        all_percent_error,
        fit_order,
    )
    percent_fit_x = np.linspace(all_percent_x.min(), all_percent_x.max(), 1000)
    percent_fit_x_normalised = (percent_fit_x - percent_x_mean) / percent_x_scale
    fitted_percent_error = percent_polynomial(percent_fit_x_normalised)

    ax_percent.plot(
        percent_fit_x,
        fitted_percent_error,
        color="black",
        linewidth=2.5,
        label=f"Average % error",
    )
    plot_reference_lines(ax_error, ax_percent, all_x.max())

    ax_percent.axhline(0, color="black", linewidth=1, alpha=0.5)
    ax_percent.set_xlabel("UTC Elapsed (s)", labelpad=4)
    ax_percent.set_ylabel("% error", labelpad=6)
    ax_percent.set_title("RTC Synchronisation % Error", pad=6)
    ax_percent.grid(True, alpha=0.35)

    error_handles, error_labels = ax_error.get_legend_handles_labels()
    ppm_handles, ppm_labels = ax_ppm.get_legend_handles_labels() if ax_ppm else ([], [])
    ax_error.legend(error_handles + ppm_handles, error_labels + ppm_labels, title="Test run", fontsize=9)
    ax_percent.legend(title="Test run", fontsize=9)

    if output_path:
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
        print(f"Saved plot to {output_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(
        description="Plot AT minus TOTP elapsed-time error for multiple RTC sync test runs."
    )
    parser.add_argument(
        "--base-dir",
        default=script_dir,
        help="Directory containing the run folders. Defaults to this script's directory.",
    )
    parser.add_argument(
        "--runs",
        nargs="+",
        default=list(DEFAULT_RUNS),
        help="Run folders to plot.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional PNG output path. If omitted, no PNG is saved.",
    )
    parser.add_argument(
        "--fit-order",
        type=int,
        choices=range(1, 5),
        default=4,
        metavar="1-4",
        help="Polynomial order for the average error fit. Defaults to 4.",
    )
    parser.add_argument(
        "--no-align",
        action="store_true",
        help="Do not remove the initial elapsed-time offset from each data source.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open the Matplotlib window.",
    )

    args = parser.parse_args()
    output_path = args.output or None

    plot_runs(
        args.base_dir,
        args.runs,
        output_path,
        fit_order=args.fit_order,
        show=not args.no_show,
        align_initial_offset=not args.no_align,
    )


if __name__ == "__main__":
    main()
