#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the four-way stochastic dead-time comparison and generate the plot."
    )
    parser.add_argument("--rate-start", type=int, default=200)
    parser.add_argument("--rate-stop", type=int, default=20000)
    parser.add_argument("--points", type=int, default=120)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmup-cycles", type=int, default=20000)
    parser.add_argument("--measure-cycles", type=int, default=200000)
    parser.add_argument(
        "--analysis-dir",
        default="data/output/analysis",
        help="Directory for generated CSV outputs.",
    )
    parser.add_argument(
        "--plot-prefix",
        default="data/output/plots/deadtime_arch_fourway_cpp",
        help="Output prefix for the comparison plot.",
    )
    return parser.parse_args()


def run(cmd: list[str], cwd: Path) -> None:
    print("RUN", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    analysis_dir = (repo_root / args.analysis_dir).resolve()
    analysis_dir.mkdir(parents=True, exist_ok=True)
    plot_prefix = (repo_root / args.plot_prefix).resolve()
    plot_prefix.parent.mkdir(parents=True, exist_ok=True)

    run(["make", "ring_deadtime_sim"], repo_root)

    common = [
        "--rate-start", str(args.rate_start),
        "--rate-stop", str(args.rate_stop),
        "--points", str(args.points),
        "--repeats", str(args.repeats),
        "--warmup-cycles", str(args.warmup_cycles),
        "--measure-cycles", str(args.measure_cycles),
    ]

    paths = {
        "wave1024": analysis_dir / "deadtime_arch_1024_cpp.csv",
        "wave512": analysis_dir / "deadtime_arch_512_cpp.csv",
        "ring0": analysis_dir / "deadtime_arch_512_ring0_cpp.csv",
        "ring50": analysis_dir / "deadtime_arch_512_ring50_cpp.csv",
    }

    run(
        [
            "./ring_deadtime_sim",
            "--architecture", "legacy",
            "--frame-samples", "1024",
            "--record-words", "232",
            "--builder-busy-cycles", "1037",
            "--csv-out", str(paths["wave1024"]),
            "--raw-csv-out", str(analysis_dir / "deadtime_arch_1024_cpp_raw.csv"),
            *common,
        ],
        repo_root,
    )
    run(
        [
            "./ring_deadtime_sim",
            "--architecture", "legacy",
            "--frame-samples", "512",
            "--record-words", "120",
            "--builder-busy-cycles", "525",
            "--csv-out", str(paths["wave512"]),
            "--raw-csv-out", str(analysis_dir / "deadtime_arch_512_cpp_raw.csv"),
            *common,
        ],
        repo_root,
    )
    run(
        [
            "./ring_deadtime_sim",
            "--architecture", "ring",
            "--signal-delay-steps", "0",
            "--csv-out", str(paths["ring0"]),
            "--raw-csv-out", str(analysis_dir / "deadtime_arch_512_ring0_cpp_raw.csv"),
            *common,
        ],
        repo_root,
    )
    run(
        [
            "./ring_deadtime_sim",
            "--architecture", "ring",
            "--signal-delay-steps", "16",
            "--csv-out", str(paths["ring50"]),
            "--raw-csv-out", str(analysis_dir / "deadtime_arch_512_ring50_cpp_raw.csv"),
            *common,
        ],
        repo_root,
    )

    run(
        [
            "python3",
            "scripts/plot_deadtime_fourway_compare.py",
            "--wave1024-csv", str(paths["wave1024"]),
            "--wave512-csv", str(paths["wave512"]),
            "--ring0-csv", str(paths["ring0"]),
            "--ring50-csv", str(paths["ring50"]),
            "--out-prefix", str(plot_prefix),
            "--title", "1024 vs 512 vs 512+ring0 vs 512+ring50",
        ],
        repo_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
