#!/usr/bin/env python3
"""
Poll NI VirtualBench DMM current readings and save them to a simple CSV.

This script uses the third-party `pyvirtualbench` wrapper that NI references in:
https://www.ni.com/en/support/documentation/supplemental/16/python-resources-for-ni-hardware-and-software.html
https://knowledge.ni.com/KnowledgeArticleDetails?id=kA00Z000000kHUFSA2&l=en-US

Example:
    py -3.13 .\\VirtualBench_power_tests\\virtualbench_current_logger.py ^
        --device VB8012-30C4175 ^
        --interval 0.2 ^
        --duration 60

If pyvirtualbench is not installed on your Python path, point the script at the
folder containing `pyvirtualbench.py`:
    py -3.13 .\\VirtualBench_power_tests\\virtualbench_current_logger.py ^
        --device VB8012-30C4175 ^
        --pyvirtualbench-path C:\\path\\to\\armstrap-pyvirtualbench
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DEVICE_NAME = "VB8012-30C4175"
DEFAULT_CURRENT_RANGE_A = 0.1
DEFAULT_INTERVAL_S = 0.2
NI_PREFS_PATH = (
    Path.home()
    / "AppData"
    / "Local"
    / "National Instruments"
    / "NI-VirtualBench"
    / "ni-virtualbench-preferences.vbconfig"
)
COMMON_NI_DLL_DIRS = [
    Path(r"C:\Program Files (x86)\National Instruments\Shared\ExternalCompilerSupport\C"),
    Path(r"C:\Program Files\National Instruments\Shared\ExternalCompilerSupport\C"),
]


def detect_device_name() -> str | None:
    try:
        if not NI_PREFS_PATH.exists():
            return None
        payload = json.loads(NI_PREFS_PATH.read_text(encoding="utf-8"))
        return payload.get("Device Configuration", {}).get("Device Name")
    except Exception:
        return None


def add_common_ni_dll_dirs() -> None:
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        return

    for dll_dir in COMMON_NI_DLL_DIRS:
        if dll_dir.exists():
            add_dll_directory(str(dll_dir))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log NI VirtualBench DMM current readings to CSV."
    )
    detected_device_name = detect_device_name()
    parser.add_argument(
        "--device",
        default=os.environ.get(
            "VIRTUALBENCH_DEVICE", detected_device_name or DEFAULT_DEVICE_NAME
        ),
        help=(
            "VirtualBench device name as shown in NI MAX / VirtualBench File > About. "
            f"Default: {detected_device_name or DEFAULT_DEVICE_NAME}"
        ),
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_S,
        help=f"Seconds between samples. Default: {DEFAULT_INTERVAL_S}",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional total logging duration in seconds. If omitted, log until Ctrl+C.",
    )
    parser.add_argument(
        "--range",
        dest="current_range",
        type=float,
        default=DEFAULT_CURRENT_RANGE_A,
        help=(
            "DMM current range in amps. Typical ATTiny work is usually fine on 0.1 A. "
            f"Default: {DEFAULT_CURRENT_RANGE_A}"
        ),
    )
    parser.add_argument(
        "--no-autorange",
        action="store_true",
        help="Disable autorange and force the provided --range value.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV output path. Defaults to VirtualBench_power_tests/current_log_YYYYMMDD_HHMMSS.csv",
    )
    parser.add_argument(
        "--pyvirtualbench-path",
        type=Path,
        default=None,
        help="Folder containing pyvirtualbench.py if it is not already importable.",
    )
    return parser.parse_args()


def load_pyvirtualbench(extra_path: Path | None) -> tuple[Any, Any, Any]:
    if extra_path is not None:
        sys.path.insert(0, str(extra_path.resolve()))

    add_common_ni_dll_dirs()

    try:
        from pyvirtualbench import DmmFunction, PyVirtualBench, PyVirtualBenchException
    except ImportError as exc:
        raise SystemExit(
            "Could not import `pyvirtualbench`.\n"
            "Install/copy the pyVirtualBench wrapper from GitHub, or pass "
            "`--pyvirtualbench-path` to the folder containing `pyvirtualbench.py`.\n"
            "NI also notes that the NI-VirtualBench driver must be installed."
        ) from exc

    return PyVirtualBench, DmmFunction, PyVirtualBenchException


def format_missing_runtime_message(exc: Exception) -> str:
    ni_paths_text = "\n".join(f"  - {path}" for path in COMMON_NI_DLL_DIRS)
    detected_device_name = detect_device_name()
    detected_device_line = (
        f"\nDetected device name from NI preferences: {detected_device_name}"
        if detected_device_name
        else ""
    )
    return (
        "The Python wrapper is installed, but the NI VirtualBench ANSI C runtime is missing.\n"
        f"Original loader error: {exc}\n\n"
        "What to install/check:\n"
        "1. Install NI VirtualBench Software / driver.\n"
        "2. During install, make sure `ANSI C Support` is selected.\n"
        "3. After install, one of these folders should exist:\n"
        f"{ni_paths_text}\n"
        "4. Then rerun this script; you do not need `--pyvirtualbench-path` anymore."
        f"{detected_device_line}"
    )


def build_output_path(requested_path: Path | None) -> Path:
    if requested_path is not None:
        return requested_path.resolve()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        Path(__file__).resolve().parent / f"current_log_{timestamp}.csv"
    ).resolve()


def validate_args(args: argparse.Namespace) -> None:
    if args.interval <= 0:
        raise SystemExit("--interval must be > 0")
    if args.duration is not None and args.duration <= 0:
        raise SystemExit("--duration must be > 0 when provided")
    if args.current_range <= 0:
        raise SystemExit("--range must be > 0")


def main() -> int:
    args = parse_args()
    validate_args(args)

    output_path = build_output_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    PyVirtualBench, DmmFunction, PyVirtualBenchException = load_pyvirtualbench(
        args.pyvirtualbench_path
    )

    autorange = not args.no_autorange
    virtualbench = None
    dmm = None
    sample_count = 0
    start_perf = 0.0

    print(f"Connecting to VirtualBench device: {args.device}")
    print(
        f"Configuring DMM for DC current, autorange={autorange}, "
        f"range={args.current_range:g} A"
    )
    print(f"Writing samples to: {output_path}")

    try:
        try:
            virtualbench = PyVirtualBench(args.device)
        except OSError as exc:
            if "nilcicapi" in str(exc).lower():
                print(format_missing_runtime_message(exc), file=sys.stderr)
                return 1
            raise
        dmm = virtualbench.acquire_digital_multimeter()
        dmm.configure_measurement(
            DmmFunction.DC_CURRENT,
            autorange,
            args.current_range,
        )

        start_perf = time.perf_counter()
        next_sample_at = start_perf

        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["elapsed_seconds", "current_amps"])

            while True:
                now = time.perf_counter()
                elapsed = now - start_perf

                if args.duration is not None and elapsed >= args.duration:
                    break

                current_amps = float(dmm.read())
                if math.isnan(current_amps) or math.isinf(current_amps):
                    raise RuntimeError(
                        f"VirtualBench returned a non-finite current reading: {current_amps!r}"
                    )

                writer.writerow([f"{elapsed:.6f}", f"{current_amps:.9f}"])
                csv_file.flush()

                sample_count += 1
                print(f"{elapsed:9.3f} s, {current_amps: .9f} A")

                next_sample_at += args.interval
                sleep_time = next_sample_at - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    next_sample_at = time.perf_counter()

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except PyVirtualBenchException as exc:
        print(f"VirtualBench error/warning {exc.status}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Logger failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if dmm is not None:
            try:
                dmm.release()
            except Exception:
                pass
        if virtualbench is not None:
            try:
                virtualbench.release()
            except Exception:
                pass

    total_elapsed = time.perf_counter() - start_perf if start_perf else 0.0
    print(
        f"Saved {sample_count} samples over {total_elapsed:.3f} s to {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
