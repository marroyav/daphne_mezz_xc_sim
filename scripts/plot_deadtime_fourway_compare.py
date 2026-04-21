#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import MultipleLocator


@dataclass(frozen=True)
class SeriesSpec:
    label: str
    path: str
    color: str
    linestyle: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot a four-way dead-time comparison from summary CSVs."
    )
    parser.add_argument("--wave1024-csv", required=True)
    parser.add_argument("--wave512-csv", required=True)
    parser.add_argument("--ring0-csv", required=True)
    parser.add_argument("--ring50-csv", required=True)
    parser.add_argument("--out-prefix", required=True)
    parser.add_argument(
        "--title",
        default="Stochastic Dead-Time Comparison",
        help="Figure title.",
    )
    return parser.parse_args()


def load_frame(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path).sort_values("rate_hz_per_channel").reset_index(drop=True)
    if "dead_fraction_mean" not in frame.columns and "dead_fraction" in frame.columns:
      frame["dead_fraction_mean"] = frame["dead_fraction"]
    if "dead_fraction_std" not in frame.columns:
      frame["dead_fraction_std"] = 0.0
    return frame


def main() -> int:
    args = parse_args()

    specs = [
        SeriesSpec("1024 waveform", args.wave1024_csv, "#202020", "-"),
        SeriesSpec("512 waveform", args.wave512_csv, "#7f7f7f", "-"),
        SeriesSpec("512 + ring0", args.ring0_csv, "#1f77b4", "-"),
        SeriesSpec("512 + ring50", args.ring50_csv, "#d62728", "-"),
    ]

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "font.size": 8,
            "axes.labelsize": 8,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.65,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.width": 0.65,
            "ytick.major.width": 0.65,
            "xtick.minor.width": 0.45,
            "ytick.minor.width": 0.45,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "xtick.minor.size": 1.8,
            "ytick.minor.size": 1.8,
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
        }
    )

    fig, ax = plt.subplots(figsize=(4.8, 3.2), constrained_layout=True)

    for spec in specs:
        frame = load_frame(spec.path)
        x = frame["rate_hz_per_channel"] / 1.0e3
        y = frame["dead_fraction_mean"] * 100.0
        yerr = frame["dead_fraction_std"] * 100.0

        ax.plot(
            x,
            y,
            color=spec.color,
            linestyle=spec.linestyle,
            linewidth=1.35,
            label=spec.label,
            zorder=2,
        )
        ax.fill_between(
            x,
            y - yerr,
            y + yerr,
            color=spec.color,
            alpha=0.10,
            linewidth=0.0,
            zorder=1,
        )

    ax.set_title(args.title, fontsize=8.5)
    ax.set_xlabel("Per-channel trigger rate (kHz)")
    ax.set_ylabel("Dead time (%)")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#d8d8d8", linewidth=0.55, alpha=0.35)
    ax.xaxis.set_major_locator(MultipleLocator(2.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(5.0))
    ax.yaxis.set_minor_locator(MultipleLocator(2.5))
    ax.set_xlim(left=0.0, right=20.2)
    ax.set_ylim(bottom=0.0)
    ax.legend(frameon=False, loc="upper left", fontsize=7.1)
    ax.text(
        0.985,
        0.02,
        "stochastic C++ model",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=6.6,
        color="#666666",
    )

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_prefix.with_suffix(".png"), dpi=220)
    fig.savefig(out_prefix.with_suffix(".pdf"))
    fig.savefig(out_prefix.with_suffix(".svg"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
