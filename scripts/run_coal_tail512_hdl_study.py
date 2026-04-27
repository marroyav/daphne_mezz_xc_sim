#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path


def parse_args():
    repo_root = Path(__file__).resolve().parents[2]
    default_fw = repo_root.parent / "daphne-firmware-bram"
    parser = argparse.ArgumentParser(
        description="Run the coal-tail512 RTL-wrapping dead-time study against the live firmware branch."
    )
    parser.add_argument("--firmware-root", default=str(default_fw))
    parser.add_argument("--rate-start", type=int, default=1000)
    parser.add_argument("--rate-stop", type=int, default=14000)
    parser.add_argument("--points", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--warmup-cycles", type=int, default=20000)
    parser.add_argument("--measure-cycles", type=int, default=200000)
    parser.add_argument("--signal-delay-steps", type=int, default=0)
    parser.add_argument("--frame-extend-hold-cycles", type=int, default=8)
    parser.add_argument(
        "--csv-out",
        default="data/output/analysis/deadtime_coal_tail512_hdl.csv",
    )
    parser.add_argument(
        "--raw-csv-out",
        default="data/output/analysis/deadtime_coal_tail512_hdl_raw.csv",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "run_multichannel_deadtime_tb.py"),
        "--firmware-root",
        args.firmware_root,
        "--builder-variant",
        "ring",
        "--rate-start",
        str(args.rate_start),
        "--rate-stop",
        str(args.rate_stop),
        "--points",
        str(args.points),
        "--repeats",
        str(args.repeats),
        "--jobs",
        str(args.jobs),
        "--warmup-cycles",
        str(args.warmup_cycles),
        "--measure-cycles",
        str(args.measure_cycles),
        "--signal-delay-steps",
        str(args.signal_delay_steps),
        "--frame-extend-hold-cycles",
        str(args.frame_extend_hold_cycles),
        "--csv-out",
        args.csv_out,
        "--raw-csv-out",
        args.raw_csv_out,
    ]
    if args.resume:
        cmd.append("--resume")
    if args.skip_build:
        cmd.append("--skip-build")

    subprocess.run(cmd, cwd=repo_root, check=True)


if __name__ == "__main__":
    main()
