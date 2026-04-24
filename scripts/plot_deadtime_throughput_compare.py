#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator


@dataclass(frozen=True)
class SimCase:
    key: str
    label: str
    color: str
    args: tuple[str, ...]


CASES = (
    SimCase("ring0", "512 + ring0", "#92DDF2", ("--architecture", "ring", "--signal-delay-steps", "0")),
    SimCase("ring50", "512 + ring50", "#96D6AE", ("--architecture", "ring", "--signal-delay-steps", "16")),
    SimCase("coalesced", "coalesced", "#F2682B", ("--architecture", "coalesced")),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot accepted and drained throughput for ring/coalesced models."
    )
    parser.add_argument("--rate-start", type=int, default=1000)
    parser.add_argument("--rate-stop", type=int, default=200000)
    parser.add_argument("--points", type=int, default=80)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--warmup-cycles", type=int, default=20000)
    parser.add_argument("--measure-cycles", type=int, default=200000)
    parser.add_argument("--clock-hz", type=float, default=62.5e6)
    parser.add_argument("--channels", type=int, default=40)
    parser.add_argument("--analysis-dir", default="data/output/analysis")
    parser.add_argument("--plot-dir", default="data/output/plots")
    parser.add_argument("--presentation-dir", default="")
    parser.add_argument("--skip-run", action="store_true")
    return parser.parse_args()


def run(cmd: list[str], cwd: Path) -> None:
    print("RUN", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        raise subprocess.CalledProcessError(result.returncode, cmd)


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 9,
            "xtick.labelsize": 7.3,
            "ytick.labelsize": 7.3,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.7,
            "figure.facecolor": "#131B24",
            "axes.facecolor": "#1C2834",
            "savefig.facecolor": "#131B24",
            "text.color": "#ECF1F4",
            "axes.labelcolor": "#ECF1F4",
            "axes.edgecolor": "#C4CDD5",
            "xtick.color": "#C4CDD5",
            "ytick.color": "#C4CDD5",
        }
    )


def load(path: Path) -> pd.DataFrame:
    return pd.read_csv(path).sort_values("rate_hz_per_channel").reset_index(drop=True)


def rate_khz(count: pd.Series, measure_seconds: float, channels: int) -> np.ndarray:
    return count.to_numpy(dtype=float) / float(channels) / measure_seconds / 1.0e3


def word_rate_mhz(count: pd.Series, measure_seconds: float, channels: int) -> np.ndarray:
    return count.to_numpy(dtype=float) / float(channels) / measure_seconds / 1.0e6


def write_outputs(fig: plt.Figure, prefix: Path) -> list[Path]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    outputs = [prefix.with_suffix(".png"), prefix.with_suffix(".pdf"), prefix.with_suffix(".svg")]
    fig.savefig(outputs[0], dpi=220)
    fig.savefig(outputs[1])
    fig.savefig(outputs[2])
    return outputs


def plot(
    csvs: dict[str, Path],
    out_prefix: Path,
    measure_seconds: float,
    channels: int,
    x_limit_khz: float | None = None,
    title_suffix: str = "",
) -> list[Path]:
    setup_style()
    fig, axes = plt.subplots(3, 1, figsize=(6.4, 6.0), constrained_layout=True)
    accepted_ax, word_ax, reject_ax = axes

    x_max = 0.0
    for case in CASES:
        frame = load(csvs[case.key])
        if x_limit_khz is not None:
            frame = frame[frame["rate_hz_per_channel"] <= x_limit_khz * 1.0e3].copy()
        x = frame["rate_hz_per_channel"].to_numpy(dtype=float) / 1.0e3
        if x.size == 0:
            continue
        x_max = max(x_max, float(np.max(x)))
        accepted = rate_khz(frame["accepted_total_mean"], measure_seconds, channels)
        sent_words = word_rate_mhz(frame["sent_word_total_mean"], measure_seconds, channels)
        generated = np.maximum(frame["generated_total_mean"].to_numpy(dtype=float), 1.0)
        full_pct = frame["full_counter_total_mean"].to_numpy(dtype=float) / generated * 100.0
        spacing_pct = frame["spacing_counter_total_mean"].to_numpy(dtype=float) / generated * 100.0

        accepted_ax.plot(x, accepted, color=case.color, linewidth=1.5, label=case.label)
        word_ax.plot(x, sent_words, color=case.color, linewidth=1.5, label=case.label)
        reject_ax.plot(x, full_pct, color=case.color, linewidth=1.25, linestyle="-", label=f"{case.label} full")
        reject_ax.plot(x, spacing_pct, color=case.color, linewidth=1.0, linestyle="--", alpha=0.75)

    accepted_ax.plot([0.0, x_max], [0.0, x_max], color="#C4CDD5", linewidth=0.8, linestyle=":", label="ideal accept")
    accepted_ax.set_title(f"Accepted trigger throughput{title_suffix}")
    accepted_ax.set_ylabel("Accepted rate/ch (kHz)")
    accepted_ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.38)

    word_ax.set_title(f"Drained output-word throughput{title_suffix}")
    word_ax.set_ylabel("Output words/ch (MHz)")
    word_ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.38)

    reject_ax.set_title(f"Reject causes{title_suffix}: solid = output-full, dashed = spacing")
    reject_ax.set_xlabel("Offered trigger rate/ch (kHz)")
    reject_ax.set_ylabel("Rejects / generated (%)")
    reject_ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.38)

    for ax in axes:
        ax.set_xlim(0.0, x_max * 1.02)
        if x_max <= 25.0:
            ax.xaxis.set_major_locator(MultipleLocator(2.0))
            ax.xaxis.set_minor_locator(MultipleLocator(1.0))
        else:
            ax.xaxis.set_major_locator(MultipleLocator(25.0))
            ax.xaxis.set_minor_locator(MultipleLocator(5.0))

    accepted_ax.yaxis.set_major_locator(MultipleLocator(2.0 if x_max <= 25.0 else 10.0))
    word_ax.yaxis.set_major_locator(MultipleLocator(0.25 if x_max <= 25.0 else 0.5))
    reject_ax.yaxis.set_major_locator(MultipleLocator(5.0 if x_max <= 25.0 else 20.0))

    legend = accepted_ax.legend(frameon=False, loc="upper left", fontsize=7.0)
    for text in legend.get_texts():
        text.set_color("#ECF1F4")

    reject_ax.text(
        0.985,
        0.04,
        "The dead-time fraction need not flatten; accepted and drained throughput are the saturation views.",
        transform=reject_ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=6.6,
        color="#C4CDD5",
    )

    return write_outputs(fig, out_prefix)


def copy_outputs(paths: list[Path], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, dest / path.name)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    analysis_dir = (repo_root / args.analysis_dir).resolve()
    plot_dir = (repo_root / args.plot_dir).resolve()
    analysis_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_run:
        run(["make", "ring_deadtime_sim"], repo_root)

    common = [
        "--rate-start",
        str(args.rate_start),
        "--rate-stop",
        str(args.rate_stop),
        "--points",
        str(args.points),
        "--repeats",
        str(args.repeats),
        "--warmup-cycles",
        str(args.warmup_cycles),
        "--measure-cycles",
        str(args.measure_cycles),
    ]

    csvs: dict[str, Path] = {}
    for case in CASES:
        csv_path = analysis_dir / f"deadtime_{case.key}_throughput_compare.csv"
        raw_path = analysis_dir / f"deadtime_{case.key}_throughput_compare_raw.csv"
        csvs[case.key] = csv_path
        if not args.skip_run:
            run(
                [
                    "./ring_deadtime_sim",
                    *case.args,
                    "--csv-out",
                    str(csv_path),
                    "--raw-csv-out",
                    str(raw_path),
                    *common,
                ],
                repo_root,
            )

    outputs = plot(
        csvs,
        plot_dir / "deadtime_ring_coalesced_throughput",
        float(args.measure_cycles) / float(args.clock_hz),
        args.channels,
    )
    outputs.extend(
        plot(
            csvs,
            plot_dir / "deadtime_ring_coalesced_throughput_zoom_0_20k",
            float(args.measure_cycles) / float(args.clock_hz),
            args.channels,
            x_limit_khz=20.0,
            title_suffix=" (0-20 kHz/ch zoom)",
        )
    )

    if args.presentation_dir:
        copy_outputs(outputs, Path(args.presentation_dir).expanduser().resolve())

    print("WROTE")
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
