import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os

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
        # Ensure column is float so we can subtract floats from it without TypeError
        df[y_col] = df[y_col].astype(float)
        
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

    # Plot TOTP data
    plt.plot(df_totp[totp_x], df_totp[totp_y], label=f'TOTP ({totp_y})', color='blue', marker='.', linestyle='-', markersize=2)
    # Add bounds (+/- 15s)
    plt.plot(df_totp[totp_x], df_totp[totp_y] + 15, color='blue', linestyle='--', alpha=0.3, label='TOTP +15s')
    plt.plot(df_totp[totp_x], df_totp[totp_y] - 15, color='blue', linestyle='--', alpha=0.3, label='TOTP -15s')
    plt.fill_between(df_totp[totp_x], df_totp[totp_y] - 15, df_totp[totp_y] + 15, color='blue', alpha=0.05)

    # Plot AT data
    plt.plot(df_at[at_x], df_at[at_y], label=f'AT ({at_y})', color='red', marker='+', linestyle='-', markersize=4, alpha=0.7)
    # Add bounds (+/- 15s)
    plt.plot(df_at[at_x], df_at[at_y] + 15, color='red', linestyle='--', alpha=0.3, label='AT +15s')
    plt.plot(df_at[at_x], df_at[at_y] - 15, color='red', linestyle='--', alpha=0.3, label='AT -15s')
    plt.fill_between(df_at[at_x], df_at[at_y] - 15, df_at[at_y] + 15, color='red', alpha=0.05)

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
