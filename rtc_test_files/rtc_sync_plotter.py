import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os
import numpy as np

def plot_data(totp_path, at_path):
    if not os.path.exists(totp_path):
        print(f"Error: Could not find '{totp_path}'")
        return
        
    if not os.path.exists(at_path):
        print(f"Error: Could not find '{at_path}'")
        return

    print(f"Loading {totp_path}...")
    df_totp = pd.read_csv(totp_path)
    print(f"Loading {at_path}...")
    df_at = pd.read_csv(at_path)

    # Clean columns to avoid hidden spaces
    df_totp.columns = df_totp.columns.str.strip()
    df_at.columns = df_at.columns.str.strip()

    # Identify X and Y columns
    def get_cols(df):
        x_col = next((col for col in df.columns if 'utc elapsed' in col.lower()), df.columns[0])
        y_col = next((col for col in df.columns if col != x_col), df.columns[1])
        return x_col, y_col

    totp_x, totp_y = get_cols(df_totp)
    at_x, at_y = get_cols(df_at)

    def remove_initial_offset(df, x_col, y_col):
        # Ensure columns are float so we can subtract floats without TypeError
        # Use pd.to_numeric with errors='coerce' to handle #VALUE! and other errors
        df[x_col] = pd.to_numeric(df[x_col], errors='coerce').astype(float)
        df[y_col] = pd.to_numeric(df[y_col], errors='coerce').astype(float)
        
        # Find the first row where elapsed time > 0
        mask = df[y_col] > 0
        if mask.any():
            start_idx = mask.idxmax()
            # Calculate the offset to align y with x at this point
            offset = df.loc[start_idx, y_col] - df.loc[start_idx, x_col]
            # Subtract this offset from all y values from here onwards
            df.loc[start_idx:, y_col] -= offset
        return df

    df_totp = remove_initial_offset(df_totp, totp_x, totp_y)
    df_at = remove_initial_offset(df_at, at_x, at_y)

    plt.figure(figsize=(12, 7))

    # Plot TOTP data as a thin, pale line (not the main focus)
    plt.plot(df_totp[totp_x], df_totp[totp_y], label=f'TOTP ({totp_y})', color='#cfcfcf', linestyle='-', linewidth=1, alpha=0.7)

    # Prepare AT vs TOTP comparison for coloring
    # Interpolate TOTP y-values at AT x positions (NaN where out-of-range)
    try:
        totp_interp_at_atx = np.interp(df_at[at_x], df_totp[totp_x], df_totp[totp_y], left=np.nan, right=np.nan)
    except Exception:
        totp_interp_at_atx = np.full(len(df_at), np.nan)

    diffs = np.abs(df_at[at_y] - totp_interp_at_atx)

    # AT bounds to plot (seconds) and bright colors for clarity
    bounds = [15, 30, 900, 1800]  # 15s, 30s, 15min, 30min
    bound_labels = ['AT ±15s', 'AT ±30s', 'AT ±15min', 'AT ±30min']
    bound_colors = ['#2ca02c', '#1f77b4', '#ff7f0e', '#d62728']

    # Plot bounds as dashed lines (in order from largest to smallest for visibility)
    for b, lbl, col in zip(bounds[::-1], bound_labels[::-1], bound_colors[::-1]):
        plt.plot(df_at[at_x], df_at[at_y] + b, color=col, linestyle='--', alpha=0.3, label=lbl)
        plt.plot(df_at[at_x], df_at[at_y] - b, color=col, linestyle='--', alpha=0.3)

    # Color AT points/segments by smallest threshold that TOTP lies within (bright, distinct colors)
    thresholds = [15, 30, 900, 1800]
    thresh_colors = {15: '#2ca02c', 30: '#1f77b4', 900: '#ff7f0e', 1800: '#d62728'}

    # Plot AT segments for each threshold (plot stricter masks last so they appear on top)
    remaining_mask = np.ones(len(df_at), dtype=bool)
    for t in sorted(thresholds, reverse=True):
        mask = (diffs <= t) & remaining_mask & (~np.isnan(diffs))
        if mask.any():
            # Label in seconds or minutes depending on threshold
            if t >= 60:
                label = f'AT within ±{t//60}min'
            else:
                label = f'AT within ±{t}s'
            plt.plot(df_at[at_x][mask], df_at[at_y][mask], color=thresh_colors[t], marker='+', linestyle='-', markersize=5, linewidth=1.25, alpha=0.95, label=label)
            remaining_mask[mask] = False

    # Plot any remaining AT points (outside all thresholds)
    if remaining_mask.any():
        plt.plot(df_at[at_x][remaining_mask], df_at[at_y][remaining_mask], color='#7f7f7f', marker='+', linestyle='-', markersize=4, alpha=0.7, label='AT outside thresholds')

    plt.xlabel('UTC Elapsed (s)')
    plt.ylabel('Elapsed (s)')
    plt.title('TOTP vs AT Time Synchronization')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    
    plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot TOTP and AT processed CSV data.")
    parser.add_argument("-t", "--totp", type=str, default="TOTPprocessed.csv", help="Path to TOTP processed CSV (default: TOTPprocessed.csv)")
    parser.add_argument("-a", "--at", type=str, default="ATprocessed.csv", help="Path to AT processed CSV (default: ATprocessed.csv)")
    parser.add_argument("-d", "--dir", type=str, help="Directory containing both CSV files (optional)")
    
    args = parser.parse_args()
    
    totp_file = args.totp
    at_file = args.at
    
    if args.dir:
        # If --dir is provided, prefix the files with this directory
        totp_file = os.path.join(args.dir, os.path.basename(args.totp))
        at_file = os.path.join(args.dir, os.path.basename(args.at))
        
    plot_data(totp_file, at_file)
