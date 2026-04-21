#!/usr/bin/env python3
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create a publication-style dead-time vs trigger-rate comparison plot."
    )
    parser.add_argument("--nominal-csv", required=True, help="CSV from sim_nominal_deadtime.py")
    parser.add_argument("--hdl-csv", required=True, help="CSV from run_multichannel_deadtime_tb.py")
    parser.add_argument("--out-prefix", required=True, help="Output path prefix without extension")
    parser.add_argument(
        "--lane-ceiling-hz",
        type=float,
        default=13412.017,
        help="Nominal fair-share lane ceiling in Hz/channel",
    )
    parser.add_argument(
        "--style",
        choices=["editorial", "classic", "noir"],
        default="editorial",
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
        help="Label used for the operating-point marker.",
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

    if args.style == "classic":
        accent_color = "#111111"
        model_color = "#111111"
        mid_color = "#111111"
        text_color = "#111111"
        figure_color = "white"
        axes_color = "white"
        grid_color = "#d8d8d8"
        reference_color = "#4c78a8"
        marker_face = "white"
    elif args.style == "noir":
        accent_color = "#F2682B"
        model_color = "#92DDF2"
        mid_color = "#C4CDD5"
        text_color = "#ECF1F4"
        figure_color = "#131B24"
        axes_color = "#1C2834"
        grid_color = "#556779"
        reference_color = "#96D6AE"
        marker_face = "#1C2834"
    else:
        accent_color = "#4c78a8"
        model_color = "#202020"
        mid_color = "#6a6a6a"
        text_color = "#202020"
        figure_color = "white"
        axes_color = "white"
        grid_color = "#d8d8d8"
        reference_color = "#B279A2"
        marker_face = "white"

    if args.font_profile == "jetbrains":
        font_family = "monospace"
        font_stack = ["JetBrainsMono NF", "JetBrainsMono NFM", "JetBrainsMono NFP", "DejaVu Sans Mono"]
    else:
        font_family = "sans-serif"
        font_stack = ["Helvetica", "Arial", "DejaVu Sans"]

    rc_updates = {
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
        "savefig.facecolor": figure_color,
        "figure.facecolor": figure_color,
        "axes.facecolor": axes_color,
        "text.color": text_color,
        "axes.labelcolor": text_color,
        "axes.edgecolor": mid_color,
        "xtick.color": mid_color,
        "ytick.color": mid_color,
    }
    if args.style == "classic":
        rc_updates.update(
            {
                "axes.spines.top": False,
                "axes.spines.right": False,
                "axes.linewidth": 0.8,
                "xtick.direction": "out",
                "ytick.direction": "out",
                "xtick.top": False,
                "ytick.right": False,
                "xtick.major.width": 0.8,
                "ytick.major.width": 0.8,
                "xtick.minor.width": 0.55,
                "ytick.minor.width": 0.55,
                "xtick.major.size": 3.6,
                "ytick.major.size": 3.6,
                "xtick.minor.size": 2.1,
                "ytick.minor.size": 2.1,
            }
        )
    plt.rcParams.update(rc_updates)

    if args.style == "classic":
        fig, ax = plt.subplots(figsize=(4.15, 3.0), constrained_layout=True)
    elif args.style == "noir":
        fig, ax = plt.subplots(figsize=(4.7, 3.0), constrained_layout=True)
    else:
        # Nature single-column width is ~89 mm; keep the panel close to that scale.
        fig, ax = plt.subplots(figsize=(3.5, 2.5), constrained_layout=True)

    nominal_x = nominal["rate_hz_per_channel"] / 1.0e3
    nominal_y = nominal["dead_fraction"] * 100.0
    hdl_x = hdl["rate_hz_per_channel"] / 1.0e3
    hdl_y = hdl["dead_fraction_mean"] * 100.0
    hdl_yerr = hdl["dead_fraction_std"] * 100.0

    ax.plot(
        nominal_x,
        nominal_y,
        color=model_color,
        linewidth=1.55 if args.style == "classic" else 1.45,
        solid_capstyle="round",
        zorder=2,
    )

    ax.errorbar(
        hdl_x,
        hdl_y,
        yerr=hdl_yerr,
        linestyle="none",
        marker="o" if args.style == "editorial" else "s",
        markersize=4.2 if args.style == "editorial" else 3.8,
        markerfacecolor=marker_face,
        markeredgecolor=accent_color,
        markeredgewidth=1.0,
        ecolor=accent_color,
        elinewidth=0.65 if args.style == "editorial" else 0.6,
        capsize=1.4 if args.style == "editorial" else 1.2,
        zorder=4,
    )

    lane_x = args.lane_ceiling_hz / 1.0e3
    ax.axvline(
        lane_x,
        color=mid_color,
        linestyle="--",
        linewidth=0.75,
        dashes=(3, 3),
        zorder=1,
    )

    ax.set_xlabel("Per-channel trigger rate (kHz)")
    ax.set_ylabel("Dead time (%)")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=grid_color, linewidth=0.55, alpha=0.35)
    ax.xaxis.set_major_locator(MultipleLocator(2.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(5.0))
    ax.yaxis.set_minor_locator(MultipleLocator(2.5))

    ax.text(
        0.02,
        0.98,
        "40 channels, 2 lanes, 62.5 MHz",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color=mid_color,
        fontsize=6.8,
    )

    x_max = max(float(nominal_x.max()), float(hdl_x.max()))
    y_max = max(float(nominal_y.max()), float(hdl_y.max() + hdl_yerr.max()))
    if args.style == "classic":
        ax.set_xlim(left=0.0, right=max(14.6, x_max * 1.03))
        ax.set_ylim(bottom=0.0, top=max(28.0, y_max * 1.03))
    else:
        ax.set_xlim(left=0.0, right=max(15.0, x_max * 1.08))
        ax.set_ylim(bottom=0.0, top=max(30.0, y_max * 1.06))

    if args.style == "classic":
        key_x0 = 0.05
        key_x1 = 0.13
        key_tx = 0.15
        key_y_model = 0.90
        key_y_hdl = 0.82

        ax.plot(
            [key_x0, key_x1],
            [key_y_model, key_y_model],
            transform=ax.transAxes,
            color=model_color,
            linewidth=1.55,
            solid_capstyle="round",
            clip_on=False,
        )
        ax.text(
            key_tx,
            key_y_model,
            "stochastic model",
            transform=ax.transAxes,
            color=text_color,
            fontsize=7.2,
            ha="left",
            va="center",
        )

        ax.plot(
            [0.09],
            [key_y_hdl],
            transform=ax.transAxes,
            linestyle="none",
            marker="s",
            markersize=4.0,
            markerfacecolor=marker_face,
            markeredgecolor=accent_color,
            markeredgewidth=1.0,
            clip_on=False,
        )
        ax.text(
            key_tx,
            key_y_hdl,
            "HDL bench",
            transform=ax.transAxes,
            color=text_color,
            fontsize=7.2,
            ha="left",
            va="center",
        )
    else:
        key_x0 = 0.05
        key_x1 = 0.13
        key_tx = 0.15
        key_y_model = 0.86
        key_y_hdl = 0.78

        ax.plot(
            [key_x0, key_x1],
            [key_y_model, key_y_model],
            transform=ax.transAxes,
            color=model_color,
            linewidth=1.45,
            solid_capstyle="round",
            clip_on=False,
        )
        ax.text(
            key_tx,
            key_y_model,
            "Stochastic model",
            transform=ax.transAxes,
            color=text_color,
            fontsize=7.0,
            ha="left",
            va="center",
        )

        ax.plot(
            [0.09],
            [key_y_hdl],
            transform=ax.transAxes,
            linestyle="none",
            marker="o",
            markersize=4.2,
            markerfacecolor=marker_face,
            markeredgecolor=accent_color,
            markeredgewidth=1.0,
            clip_on=False,
        )
        ax.text(
            key_tx,
            key_y_hdl,
            "HDL bench",
            transform=ax.transAxes,
            color=text_color,
            fontsize=7.0,
            ha="left",
            va="center",
        )

    ax.text(
        lane_x + 0.06,
        ax.get_ylim()[1] * 0.97,
        "Hermes-input ceiling",
        rotation=90,
        color=mid_color,
        fontsize=6.8,
        ha="left",
        va="top",
    )

    if args.reference_rate_hz > 0.0:
        ref_x = args.reference_rate_hz / 1.0e3
        ref_y = float(np.interp(args.reference_rate_hz, nominal["rate_hz_per_channel"], nominal_y))
        ax.axvline(
            ref_x,
            color=reference_color,
            linestyle=":",
            linewidth=1.0,
            dashes=(1.5, 2.5),
            zorder=1,
        )
        ax.scatter(
            [ref_x],
            [ref_y],
            s=28,
            facecolors=reference_color,
            edgecolors=figure_color if args.style == "noir" else "white",
            linewidths=0.8,
            zorder=5,
        )
        if args.style == "noir":
            bbox_face = "#2A3948"
        else:
            bbox_face = "white"
        ax.annotate(
            f"{args.reference_label}\n{ref_x:.1f} kHz/ch\n{ref_y:.1f}% dead time",
            xy=(ref_x, ref_y),
            xytext=(ref_x + 1.05, ref_y + 5.2),
            ha="left",
            va="bottom",
            fontsize=6.8,
            color=text_color,
            bbox={
                "boxstyle": "round,pad=0.28",
                "facecolor": bbox_face,
                "edgecolor": reference_color,
                "linewidth": 0.8,
            },
            arrowprops={
                "arrowstyle": "-",
                "color": reference_color,
                "linewidth": 0.9,
            },
            zorder=6,
        )

    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_prefix.with_suffix(".png"), dpi=400)
    fig.savefig(out_prefix.with_suffix(".pdf"))
    fig.savefig(out_prefix.with_suffix(".svg"))


if __name__ == "__main__":
    main()
