#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
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
    parser.add_argument(
        "--style",
        choices=["classic", "noir"],
        default="classic",
        help="Visual style profile for the figure.",
    )
    parser.add_argument(
        "--font-profile",
        choices=["default", "jetbrains"],
        default="default",
        help="Font profile for figure text.",
    )
    parser.add_argument(
        "--reference-rate-hz",
        type=float,
        default=0.0,
        help="Optional operating-point marker in Hz/channel.",
    )
    parser.add_argument(
        "--reference-label",
        default="FD-HD reference",
        help="Label used for the optional operating-point marker.",
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

    if args.style == "noir":
        specs = [
            SeriesSpec("1024 waveform", args.wave1024_csv, "#F2682B", "-"),
            SeriesSpec("512 waveform", args.wave512_csv, "#C4CDD5", "-"),
            SeriesSpec("512 + ring0", args.ring0_csv, "#92DDF2", "-"),
            SeriesSpec("512 + ring50", args.ring50_csv, "#96D6AE", "-"),
        ]
        figure_color = "#131B24"
        axes_color = "#1C2834"
        edge_color = "#C4CDD5"
        text_color = "#ECF1F4"
        grid_color = "#556779"
        ref_color = "#C4CDD5"
        note_color = "#C4CDD5"
    else:
        specs = [
            SeriesSpec("1024 waveform", args.wave1024_csv, "#202020", "-"),
            SeriesSpec("512 waveform", args.wave512_csv, "#7f7f7f", "-"),
            SeriesSpec("512 + ring0", args.ring0_csv, "#1f77b4", "-"),
            SeriesSpec("512 + ring50", args.ring50_csv, "#d62728", "-"),
        ]
        figure_color = "white"
        axes_color = "white"
        edge_color = "#202020"
        text_color = "#202020"
        grid_color = "#d8d8d8"
        ref_color = "#666666"
        note_color = "#666666"

    if args.font_profile == "jetbrains":
        font_family = "monospace"
        font_stack = [
            "JetBrainsMono NF",
            "JetBrainsMono NFM",
            "JetBrainsMono NFP",
            "DejaVu Sans Mono",
        ]
    else:
        font_family = "sans-serif"
        font_stack = ["Helvetica", "Arial", "DejaVu Sans"]

    plt.rcParams.update(
        {
            "font.family": font_family,
            "font.sans-serif": font_stack if font_family == "sans-serif" else ["Helvetica", "Arial", "DejaVu Sans"],
            "font.monospace": font_stack if font_family == "monospace" else ["DejaVu Sans Mono"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 8.5,
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
            "savefig.facecolor": figure_color,
            "figure.facecolor": figure_color,
            "axes.facecolor": axes_color,
            "text.color": text_color,
            "axes.labelcolor": text_color,
            "axes.edgecolor": edge_color,
            "xtick.color": edge_color,
            "ytick.color": edge_color,
        }
    )

    if args.style == "noir":
        fig, ax = plt.subplots(figsize=(5.2, 3.2), constrained_layout=True)
    else:
        fig, ax = plt.subplots(figsize=(4.8, 3.2), constrained_layout=True)

    x_max = 0.0
    y_max = 0.0
    for spec in specs:
        frame = load_frame(spec.path)
        x = frame["rate_hz_per_channel"] / 1.0e3
        y = frame["dead_fraction_mean"] * 100.0
        yerr = frame["dead_fraction_std"] * 100.0
        x_max = max(x_max, float(x.max()))
        y_max = max(y_max, float((y + yerr).max()))

        ax.plot(
            x,
            y,
            color=spec.color,
            linestyle=spec.linestyle,
            linewidth=1.45,
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

    ax.set_title(args.title)
    ax.set_xlabel("Per-channel trigger rate (kHz)")
    ax.set_ylabel("Dead time (%)")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=grid_color, linewidth=0.55, alpha=0.35)
    ax.xaxis.set_major_locator(MultipleLocator(2.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(5.0))
    ax.yaxis.set_minor_locator(MultipleLocator(2.5))
    ax.set_xlim(left=0.0, right=max(20.2, x_max * 1.02))
    ax.set_ylim(bottom=0.0, top=max(38.0, y_max * 1.05))

    if args.reference_rate_hz > 0.0:
        ref_x = args.reference_rate_hz / 1.0e3
        ax.axvline(
            ref_x,
            color=ref_color,
            linestyle="--",
            linewidth=0.8,
            dashes=(3, 3),
            zorder=0,
        )
        ax.text(
            ref_x + 0.12,
            ax.get_ylim()[1] * 0.97,
            args.reference_label,
            rotation=90,
            color=ref_color,
            fontsize=6.8,
            ha="left",
            va="top",
        )

    legend = ax.legend(frameon=False, loc="upper left", fontsize=7.0)
    if legend is not None:
        for text in legend.get_texts():
            text.set_color(text_color)

    ax.text(
        0.985,
        0.02,
        "stochastic C++ model",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=6.6,
        color=note_color,
    )

    if args.reference_rate_hz > 0.0:
        refs = []
        for spec in specs:
            frame = load_frame(spec.path)
            y = np.interp(
                args.reference_rate_hz,
                frame["rate_hz_per_channel"].to_numpy(dtype=float),
                frame["dead_fraction_mean"].to_numpy(dtype=float) * 100.0,
            )
            refs.append(f"{spec.label}: {y:.1f}%")
        ax.text(
            0.985,
            0.975,
            "\n".join(refs),
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=6.5,
            color=text_color,
            bbox={
                "boxstyle": "round,pad=0.24",
                "facecolor": axes_color,
                "edgecolor": grid_color,
                "linewidth": 0.6,
                "alpha": 0.96,
            },
        )

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_prefix.with_suffix(".png"), dpi=220)
    fig.savefig(out_prefix.with_suffix(".pdf"))
    fig.savefig(out_prefix.with_suffix(".svg"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
