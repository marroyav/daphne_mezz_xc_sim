#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the stochastic dead-time optimization study and render the comparison figures."
    )
    parser.add_argument("--rate-start", type=int, default=200)
    parser.add_argument("--rate-stop", type=int, default=20000)
    parser.add_argument("--points", type=int, default=120)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--warmup-cycles", type=int, default=20000)
    parser.add_argument("--measure-cycles", type=int, default=200000)
    parser.add_argument("--analysis-dir", default="data/output/analysis")
    parser.add_argument("--plot-dir", default="data/output/plots")
    parser.add_argument("--reference-rate-hz", type=float, default=4600.0)
    parser.add_argument("--skip-run", action="store_true")
    return parser.parse_args()


def run(cmd: list[str], cwd: Path) -> None:
    print("RUN", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    analysis_dir = (repo_root / args.analysis_dir).resolve()
    plot_dir = (repo_root / args.plot_dir).resolve()
    analysis_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    common = [
        "--rate-start", str(args.rate_start),
        "--rate-stop", str(args.rate_stop),
        "--points", str(args.points),
        "--repeats", str(args.repeats),
        "--warmup-cycles", str(args.warmup_cycles),
        "--measure-cycles", str(args.measure_cycles),
    ]

    if not args.skip_run:
        run(["make", "ring_deadtime_sim"], repo_root)

        four_lane_cases = (
            (
                "deadtime_arch_512_4lane_cpp.csv",
                "deadtime_arch_512_4lane_cpp_raw.csv",
                ["--architecture", "legacy", "--frame-samples", "512", "--record-words", "120", "--builder-busy-cycles", "525"],
            ),
            (
                "deadtime_arch_512_ring50_4lane_cpp.csv",
                "deadtime_arch_512_ring50_4lane_cpp_raw.csv",
                ["--architecture", "ring", "--signal-delay-steps", "16"],
            ),
            (
                "deadtime_coalesced_4lane_cpp.csv",
                "deadtime_coalesced_4lane_cpp_raw.csv",
                ["--architecture", "coalesced"],
            ),
            (
                "deadtime_coalesced_open_4lane_cpp.csv",
                "deadtime_coalesced_open_4lane_cpp_raw.csv",
                ["--architecture", "coalesced", "--prog-full-thresh", "1000000"],
            ),
        )

        for csv_name, raw_name, extra in four_lane_cases:
            run(
                [
                    "./ring_deadtime_sim",
                    "--lanes", "4",
                    "--channels-per-lane", "10",
                    "--csv-out", str(analysis_dir / csv_name),
                    "--raw-csv-out", str(analysis_dir / raw_name),
                    *extra,
                    *common,
                ],
                repo_root,
            )

    run(
        [
            "python3",
            "scripts/run_deadtime_fourway_compare.py",
            "--rate-start", str(args.rate_start),
            "--rate-stop", str(args.rate_stop),
            "--points", str(args.points),
            "--repeats", str(args.repeats),
            "--warmup-cycles", str(args.warmup_cycles),
            "--measure-cycles", str(args.measure_cycles),
        ],
        repo_root,
    )
    run(
        [
            "python3",
            "scripts/plot_deadtime_coalesced_compare.py",
            "--rate-start", str(args.rate_start),
            "--rate-stop", str(args.rate_stop),
            "--points", str(max(args.points - 30, 90)),
            "--repeats", str(args.repeats),
            "--warmup-cycles", str(args.warmup_cycles),
            "--measure-cycles", str(args.measure_cycles),
        ],
        repo_root,
    )
    run(
        [
            "python3",
            "scripts/plot_deadtime_throughput_compare.py",
            "--rate-start", "500",
            "--rate-stop", "200000",
            "--points", "80",
            "--repeats", str(args.repeats),
            "--warmup-cycles", str(args.warmup_cycles),
            "--measure-cycles", str(args.measure_cycles),
        ],
        repo_root,
    )
    run(
        [
            "python3",
            "scripts/plot_deadtime_argument_figures.py",
            "--reference-rate-hz", str(args.reference_rate_hz),
        ],
        repo_root,
    )
    run(
        [
            "python3",
            "scripts/plot_deadtime_transport_compare.py",
            "--reference-rate-hz", str(args.reference_rate_hz),
        ],
        repo_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
