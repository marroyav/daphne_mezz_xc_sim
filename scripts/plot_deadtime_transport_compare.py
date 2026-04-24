#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator


@dataclass(frozen=True)
class SeriesPair:
    key: str
    label: str
    two_lane_csv: str
    four_lane_csv: str
    color: str


SERIES = (
    SeriesPair("wave512", "512 waveform", "deadtime_arch_512_cpp.csv", "deadtime_arch_512_4lane_cpp.csv", "#C4CDD5"),
    SeriesPair("ring50", "512 + ring50", "deadtime_arch_512_ring50_cpp.csv", "deadtime_arch_512_ring50_4lane_cpp.csv", "#96D6AE"),
    SeriesPair("coalesced", "coalesced, current gate", "deadtime_coalesced_coalesced_compare.csv", "deadtime_coalesced_4lane_cpp.csv", "#F2682B"),
    SeriesPair("coalesced_open", "coalesced, relaxed gate", "deadtime_coalesced_open_coalesced_compare.csv", "deadtime_coalesced_open_4lane_cpp.csv", "#D8B365"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot 2-lane versus 4-lane dead-time comparisons for the stochastic models."
    )
    parser.add_argument("--analysis-dir", default="data/output/analysis")
    parser.add_argument("--plot-dir", default="data/output/plots")
    parser.add_argument("--presentation-dir", default="")
    parser.add_argument("--reference-rate-hz", type=float, default=4600.0)
    return parser.parse_args()


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
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
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
    frame = pd.read_csv(path).sort_values("rate_hz_per_channel").reset_index(drop=True)
    if "dead_fraction_std" not in frame.columns:
        frame["dead_fraction_std"] = 0.0
    return frame


def interp_dead(frame: pd.DataFrame, rate_hz: float) -> float:
    return float(
        np.interp(
            rate_hz,
            frame["rate_hz_per_channel"].to_numpy(dtype=float),
            frame["dead_fraction_mean"].to_numpy(dtype=float) * 100.0,
        )
    )


def write_outputs(fig: plt.Figure, prefix: Path) -> list[Path]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    outputs = [prefix.with_suffix(".png"), prefix.with_suffix(".pdf"), prefix.with_suffix(".svg")]
    fig.savefig(outputs[0], dpi=220)
    fig.savefig(outputs[1])
    fig.savefig(outputs[2])
    plt.close(fig)
    return outputs


def copy_outputs(paths: list[Path], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, dest / path.name)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    analysis_dir = (repo_root / args.analysis_dir).resolve()
    plot_dir = (repo_root / args.plot_dir).resolve()
    plot_dir.mkdir(parents=True, exist_ok=True)

    setup_style()
    fig, (curve_ax, bar_ax) = plt.subplots(
        2,
        1,
        figsize=(6.3, 5.35),
        gridspec_kw={"height_ratios": [2.1, 1.0]},
        constrained_layout=True,
    )

    frames: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    y_max = 0.0
    for spec in SERIES:
        two_lane = load(analysis_dir / spec.two_lane_csv)
        four_lane = load(analysis_dir / spec.four_lane_csv)
        frames[spec.key] = (two_lane, four_lane)

        x2 = two_lane["rate_hz_per_channel"].to_numpy(dtype=float) / 1.0e3
        y2 = two_lane["dead_fraction_mean"].to_numpy(dtype=float) * 100.0
        y2err = two_lane["dead_fraction_std"].to_numpy(dtype=float) * 100.0
        x4 = four_lane["rate_hz_per_channel"].to_numpy(dtype=float) / 1.0e3
        y4 = four_lane["dead_fraction_mean"].to_numpy(dtype=float) * 100.0
        y4err = four_lane["dead_fraction_std"].to_numpy(dtype=float) * 100.0

        y_max = max(y_max, float(np.max(y2 + y2err)), float(np.max(y4 + y4err)))
        curve_ax.plot(x2, y2, color=spec.color, linewidth=1.45, label=f"{spec.label}, 2 lanes")
        curve_ax.plot(x4, y4, color=spec.color, linewidth=1.15, linestyle="--", label=f"{spec.label}, 4 lanes")

    curve_ax.axvline(args.reference_rate_hz / 1.0e3, color="#C4CDD5", linewidth=0.8, linestyle="--", dashes=(3, 3))
    curve_ax.set_title("Transport scaling: 2 lanes (20 ch/lane) versus 4 lanes (10 ch/lane)")
    curve_ax.set_xlabel("Per-channel trigger rate (kHz)")
    curve_ax.set_ylabel("Dead time (%)")
    curve_ax.set_xlim(0.0, 20.2)
    curve_ax.set_ylim(0.0, max(52.0, y_max * 1.05))
    curve_ax.xaxis.set_major_locator(MultipleLocator(2.0))
    curve_ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    curve_ax.yaxis.set_major_locator(MultipleLocator(5.0))
    curve_ax.yaxis.set_minor_locator(MultipleLocator(2.5))
    curve_ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.35)
    legend = curve_ax.legend(frameon=False, loc="upper left", fontsize=6.8, ncol=2)
    for text in legend.get_texts():
        text.set_color("#ECF1F4")

    x = np.arange(len(SERIES), dtype=float)
    width = 0.34
    two_vals = []
    four_vals = []
    for spec in SERIES:
        two_lane, four_lane = frames[spec.key]
        two_vals.append(interp_dead(two_lane, args.reference_rate_hz))
        four_vals.append(interp_dead(four_lane, args.reference_rate_hz))

    bars2 = bar_ax.bar(x - width / 2.0, two_vals, width=width, color=[spec.color for spec in SERIES], alpha=0.90, label="2 lanes")
    bars4 = bar_ax.bar(x + width / 2.0, four_vals, width=width, color=[spec.color for spec in SERIES], alpha=0.45, hatch="//", edgecolor="#ECF1F4", linewidth=0.6, label="4 lanes")

    for bars in (bars2, bars4):
        for bar in bars:
            value = bar.get_height()
            bar_ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                value + 0.18,
                f"{value:.1f}",
                ha="center",
                va="bottom",
                fontsize=6.6,
            )

    bar_ax.set_title("Operating point at 4.6 kHz/ch")
    bar_ax.set_ylabel("Dead time (%)")
    bar_ax.set_xticks(
        x,
        ["512", "ring50", "coalesced", "coalesced\nrelaxed"],
    )
    bar_ax.yaxis.set_major_locator(MultipleLocator(2.0))
    bar_ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.35)
    legend = bar_ax.legend(frameon=False, loc="upper left", fontsize=6.8)
    for text in legend.get_texts():
        text.set_color("#ECF1F4")
    bar_ax.text(
        0.985,
        0.04,
        "Four lanes help the current ring path modestly.\nThey do not rescue the inherited coalesced output gate.",
        transform=bar_ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=6.5,
        color="#C4CDD5",
    )

    outputs = write_outputs(fig, plot_dir / "deadtime_transport_compare")
    if args.presentation_dir:
        copy_outputs(outputs, Path(args.presentation_dir).resolve())
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
