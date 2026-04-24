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
class Series:
    key: str
    label: str
    csv_name: str
    color: str
    linestyle: str = "-"


SERIES = (
    Series("wave1024", "1024 waveform", "deadtime_arch_1024_cpp.csv", "#F2682B"),
    Series("wave512", "512 waveform", "deadtime_arch_512_cpp.csv", "#C4CDD5"),
    Series("ring0", "512 + ring0", "deadtime_arch_512_ring0_cpp.csv", "#92DDF2"),
    Series("ring50", "512 + ring50", "deadtime_arch_512_ring50_cpp.csv", "#96D6AE"),
    Series(
        "coalesced",
        "coalesced, current gate",
        "deadtime_coalesced_coalesced_compare.csv",
        "#EBCB8B",
    ),
)

OPERATING_POINT_EXTRA = Series(
    "coalesced_open",
    "coalesced, relaxed gate",
    "deadtime_coalesced_open_coalesced_compare.csv",
    "#D8B365",
    "--",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render compact dead-time argument figures for the presentation."
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
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "xtick.minor.width": 0.45,
            "ytick.minor.width": 0.45,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "xtick.minor.size": 1.8,
            "ytick.minor.size": 1.8,
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
    if "dead_fraction_mean" not in frame.columns and "dead_fraction" in frame.columns:
        frame["dead_fraction_mean"] = frame["dead_fraction"]
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


def save_all(fig: plt.Figure, prefix: Path) -> list[Path]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    outputs = []
    for suffix in (".png", ".pdf", ".svg"):
        path = prefix.with_suffix(suffix)
        if suffix == ".png":
            fig.savefig(path, dpi=220)
        else:
            fig.savefig(path)
        outputs.append(path)
    plt.close(fig)
    return outputs


def plot_architecture(
    frames: dict[str, pd.DataFrame],
    out_prefix: Path,
    reference_rate_hz: float,
) -> list[Path]:
    fig, ax = plt.subplots(figsize=(5.7, 3.15), constrained_layout=True)

    y_max = 0.0
    for spec in SERIES:
        frame = frames[spec.key]
        x = frame["rate_hz_per_channel"].to_numpy(dtype=float) / 1.0e3
        y = frame["dead_fraction_mean"].to_numpy(dtype=float) * 100.0
        yerr = frame["dead_fraction_std"].to_numpy(dtype=float) * 100.0
        y_max = max(y_max, float((y + yerr).max()))
        ax.plot(x, y, color=spec.color, linewidth=1.45, linestyle=spec.linestyle, label=spec.label)
        ax.fill_between(x, y - yerr, y + yerr, color=spec.color, alpha=0.10, linewidth=0.0)

    ref_x = reference_rate_hz / 1.0e3
    ax.axvline(ref_x, color="#C4CDD5", linestyle="--", linewidth=0.8, dashes=(3, 3))
    ax.text(ref_x + 0.12, 0.96, "FD-HD", transform=ax.get_xaxis_transform(),
            rotation=90, ha="left", va="top", fontsize=6.8, color="#C4CDD5")

    refs = [f"{spec.label}: {interp_dead(frames[spec.key], reference_rate_hz):.1f}%" for spec in SERIES]
    ax.text(
        0.985,
        0.975,
        "\n".join(refs),
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=6.4,
        bbox={
            "boxstyle": "round,pad=0.24",
            "facecolor": "#1C2834",
            "edgecolor": "#556779",
            "linewidth": 0.6,
            "alpha": 0.96,
        },
    )

    ax.set_title("Architecture comparison with coalesced non-overlap probe")
    ax.set_xlabel("Per-channel trigger rate (kHz)")
    ax.set_ylabel("Dead time (%)")
    ax.set_xlim(0.0, 20.2)
    ax.set_ylim(0.0, max(38.0, y_max * 1.05))
    ax.xaxis.set_major_locator(MultipleLocator(2.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(5.0))
    ax.yaxis.set_minor_locator(MultipleLocator(2.5))
    ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.35)
    legend = ax.legend(frameon=False, loc="upper left", fontsize=6.8)
    if legend is not None:
        for text in legend.get_texts():
            text.set_color("#ECF1F4")
    ax.text(0.985, 0.02, "same FIFO/mux/Hermes-input boundary", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=6.5, color="#C4CDD5")

    return save_all(fig, out_prefix)


def plot_operating_point(
    frames: dict[str, pd.DataFrame],
    out_prefix: Path,
    reference_rate_hz: float,
) -> list[Path]:
    specs = list(SERIES) + [OPERATING_POINT_EXTRA]
    values = [interp_dead(frames[spec.key], reference_rate_hz) for spec in specs]
    labels = [
        "1024",
        "512",
        "ring0",
        "ring50\n(overlap)",
        "coalesced\n(current)",
        "coalesced\n(relaxed)",
    ]

    fig, ax = plt.subplots(figsize=(5.7, 2.85), constrained_layout=True)
    x = np.arange(len(specs))
    bars = ax.bar(x, values, color=[spec.color for spec in specs], width=0.68)
    bars[-1].set_alpha(0.65)
    bars[-1].set_hatch("//")
    bars[-1].set_edgecolor("#ECF1F4")
    bars[-1].set_linewidth(0.6)

    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2.0, value + 0.25, f"{value:.1f}%",
                ha="center", va="bottom", fontsize=7.0)

    ax.set_title("Operating point: what each concept buys and costs")
    ax.set_ylabel("Dead time at 4.6 kHz/ch (%)")
    ax.set_xticks(x, labels)
    ax.set_ylim(0.0, max(values) + 2.3)
    ax.yaxis.set_major_locator(MultipleLocator(2.0))
    ax.yaxis.set_minor_locator(MultipleLocator(1.0))
    ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.35)
    ax.text(0.02, 0.96, "hatched = acceptance-side upper bound, not HDL transport signoff",
            transform=ax.transAxes, ha="left", va="top", fontsize=6.8, color="#C4CDD5")
    ax.text(0.98, 0.96, "coalesced current gate: non-overlap, output-full dominated",
            transform=ax.transAxes, ha="right", va="top", fontsize=6.8, color="#C4CDD5")

    return save_all(fig, out_prefix)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    analysis_dir = (repo_root / args.analysis_dir).resolve()
    plot_dir = (repo_root / args.plot_dir).resolve()
    setup_style()

    all_specs = list(SERIES) + [OPERATING_POINT_EXTRA]
    frames = {spec.key: load(analysis_dir / spec.csv_name) for spec in all_specs}

    outputs = []
    outputs.extend(plot_architecture(frames, plot_dir / "deadtime_arch_fiveway_dunenoir", args.reference_rate_hz))
    outputs.extend(plot_operating_point(frames, plot_dir / "deadtime_operating_point_contracts", args.reference_rate_hz))

    if args.presentation_dir:
        dest = Path(args.presentation_dir).resolve()
        dest.mkdir(parents=True, exist_ok=True)
        for path in outputs:
            shutil.copy2(path, dest / path.name)

    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
