#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path


def parse_args():
    repo_root = Path(__file__).resolve().parents[2]
    default_fw = repo_root.parent / "daphne-firmware"
    parser = argparse.ArgumentParser(
        description="Run the grouped-source lane-serializer RTL dead-time study against the firmware branch."
    )
    parser.add_argument("--firmware-root", default=str(default_fw))
    parser.add_argument("--rate-start", type=int, default=1000)
    parser.add_argument("--rate-stop", type=int, default=20000)
    parser.add_argument("--points", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--warmup-cycles", type=int, default=20000)
    parser.add_argument("--measure-cycles", type=int, default=200000)
    parser.add_argument("--signal-delay-steps", type=int, default=0)
    parser.add_argument("--channel-count", type=int, default=40)
    parser.add_argument("--producer-count", type=int, default=5)
    parser.add_argument("--channels-per-producer", type=int, default=8)
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--raw-csv-out", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if args.channel_count != args.producer_count * args.channels_per_producer:
        raise ValueError("--channel-count must equal --producer-count * --channels-per-producer")

    csv_out = args.csv_out
    raw_csv_out = args.raw_csv_out
    if not csv_out:
        csv_out = (
            f"data/output/analysis/deadtime_grouped_lane_"
            f"src{args.producer_count}_ch{args.channels_per_producer}_hdl.csv"
        )
    if not raw_csv_out:
        raw_csv_out = (
            f"data/output/analysis/deadtime_grouped_lane_"
            f"src{args.producer_count}_ch{args.channels_per_producer}_hdl_raw.csv"
        )

    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "run_multichannel_deadtime_tb.py"),
        "--firmware-root",
        args.firmware_root,
        "--builder-variant",
        "lane",
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
        "--channel-count",
        str(args.channel_count),
        "--producer-count",
        str(args.producer_count),
        "--channels-per-producer",
        str(args.channels_per_producer),
        "--csv-out",
        csv_out,
        "--raw-csv-out",
        raw_csv_out,
    ]
    if args.resume:
        cmd.append("--resume")
    if args.skip_build:
        cmd.append("--skip-build")

    subprocess.run(cmd, cwd=repo_root, check=True)


if __name__ == "__main__":
    main()
