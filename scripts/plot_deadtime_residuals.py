#!/usr/bin/env python3
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot HDL minus nominal dead-time residuals versus trigger rate."
    )
    parser.add_argument("--nominal-csv", required=True, help="CSV from sim_nominal_deadtime.py")
    parser.add_argument("--hdl-csv", required=True, help="CSV from run_multichannel_deadtime_tb.py")
    parser.add_argument("--out-prefix", required=True, help="Output path prefix without extension")
    parser.add_argument("--csv-out", default="", help="Optional residual CSV output path")
    parser.add_argument(
        "--lane-ceiling-hz",
        type=float,
        default=13412.017,
        help="Nominal fair-share lane ceiling in Hz/channel.",
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
        default="jetbrains",
        help="Font profile for figure text.",
    )
    return parser.parse_args()


def load_frame(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "dead_fraction" not in frame.columns and "dead_ppm" in frame.columns:
        frame["dead_fraction"] = frame["dead_ppm"] / 1_000_000.0
    if "dead_fraction_mean" not in frame.columns and "dead_fraction" in frame.columns:
        frame["dead_fraction_mean"] = frame["dead_fraction"]
    if "dead_fraction_std" not in frame.columns:
        frame["dead_fraction_std"] = 0.0
    return frame.sort_values("rate_hz_per_channel").reset_index(drop=True)


def main():
    args = parse_args()
    nominal = load_frame(args.nominal_csv)
    hdl = load_frame(args.hdl_csv)

    if args.font_profile == "jetbrains":
        font_family = "monospace"
        font_stack = ["JetBrainsMono NF", "JetBrainsMono NFM", "JetBrainsMono NFP", "DejaVu Sans Mono"]
    else:
        font_family = "sans-serif"
        font_stack = ["Helvetica", "Arial", "DejaVu Sans"]

    if args.style == "noir":
        marker_color = "#F2682B"
        line_color = "#C4CDD5"
        text_color = "#ECF1F4"
        figure_color = "#131B24"
        axes_color = "#1C2834"
        grid_color = "#556779"
        marker_face = "#1C2834"
    else:
        marker_color = "#111111"
        line_color = "#111111"
        text_color = "#111111"
        figure_color = "white"
        axes_color = "white"
        grid_color = "#d8d8d8"
        marker_face = "white"

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
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "xtick.minor.width": 0.55,
            "ytick.minor.width": 0.55,
            "xtick.major.size": 3.6,
            "ytick.major.size": 3.6,
            "xtick.minor.size": 2.1,
            "ytick.minor.size": 2.1,
            "savefig.facecolor": figure_color,
            "figure.facecolor": figure_color,
            "axes.facecolor": axes_color,
            "text.color": text_color,
            "axes.labelcolor": text_color,
            "axes.edgecolor": line_color,
            "xtick.color": line_color,
            "ytick.color": line_color,
        }
    )

    nominal_rates = nominal["rate_hz_per_channel"].to_numpy(dtype=float)
    nominal_dead_pct = nominal["dead_fraction"].to_numpy(dtype=float) * 100.0
    hdl_rates = hdl["rate_hz_per_channel"].to_numpy(dtype=float)
    hdl_dead_pct = hdl["dead_fraction_mean"].to_numpy(dtype=float) * 100.0
    hdl_dead_std_pct = hdl["dead_fraction_std"].to_numpy(dtype=float) * 100.0

    nominal_interp_pct = np.interp(hdl_rates, nominal_rates, nominal_dead_pct)
    residual_pct = hdl_dead_pct - nominal_interp_pct

    residual_df = pd.DataFrame(
        {
            "rate_hz_per_channel": hdl_rates.astype(int),
            "rate_khz_per_channel": hdl_rates / 1.0e3,
            "hdl_dead_fraction_mean": hdl["dead_fraction_mean"].to_numpy(dtype=float),
            "hdl_dead_fraction_std": hdl["dead_fraction_std"].to_numpy(dtype=float),
            "hdl_dead_pct_mean": hdl_dead_pct,
            "hdl_dead_pct_std": hdl_dead_std_pct,
            "nominal_dead_pct_interp": nominal_interp_pct,
            "residual_pct_points": residual_pct,
        }
    )

    if args.style == "noir":
        fig, ax = plt.subplots(figsize=(4.6, 2.65), constrained_layout=True)
    else:
        fig, ax = plt.subplots(figsize=(4.15, 2.45), constrained_layout=True)

    ax.axhline(0.0, color=line_color, linewidth=1.0, zorder=1)
    ax.errorbar(
        residual_df["rate_khz_per_channel"],
        residual_df["residual_pct_points"],
        yerr=residual_df["hdl_dead_pct_std"],
        linestyle="none",
        marker="s",
        markersize=3.8,
        markerfacecolor=marker_face,
        markeredgecolor=marker_color,
        markeredgewidth=1.0,
        ecolor=marker_color,
        elinewidth=0.6,
        capsize=1.2,
        zorder=3,
    )

    lane_x = args.lane_ceiling_hz / 1.0e3
    ax.axvline(
        lane_x,
        color=line_color,
        linestyle="--",
        linewidth=0.75,
        dashes=(3, 3),
        zorder=1,
    )

    ax.set_xlabel("Per-channel trigger rate (kHz)")
    ax.set_ylabel("HDL - nominal (p.p.)")
    ax.grid(axis="y", color=grid_color, linewidth=0.55, alpha=0.35)
    ax.xaxis.set_major_locator(MultipleLocator(2.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.yaxis.set_minor_locator(MultipleLocator(0.5))
    ax.set_xlim(0.0, max(14.6, float(residual_df["rate_khz_per_channel"].max()) * 1.03))

    y_abs = max(
        0.5,
        float(np.max(np.abs(residual_df["residual_pct_points"]) + residual_df["hdl_dead_pct_std"])) * 1.15,
    )
    ax.set_ylim(-y_abs, y_abs)

    ax.text(
        0.02,
        0.97,
        "Residuals after interpolation to HDL rates",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color=line_color,
        fontsize=7.0,
    )
    ax.text(
        lane_x + 0.06,
        ax.get_ylim()[1] * 0.96,
        "Hermes-input ceiling",
        rotation=90,
        color=line_color,
        fontsize=6.8,
        ha="left",
        va="top",
    )

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_prefix.with_suffix(".png"), dpi=400)
    fig.savefig(out_prefix.with_suffix(".pdf"))
    fig.savefig(out_prefix.with_suffix(".svg"))

    if args.csv_out:
        residual_path = Path(args.csv_out)
        residual_path.parent.mkdir(parents=True, exist_ok=True)
        residual_df.to_csv(residual_path, index=False)


if __name__ == "__main__":
    main()
