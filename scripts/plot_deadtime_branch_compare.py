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
class BranchSeries:
    label: str
    rate_hz: np.ndarray
    dead_pct: np.ndarray
    dead_pct_std: np.ndarray
    busy_pct: np.ndarray
    busy_pct_std: np.ndarray
    full_pct: np.ndarray
    full_pct_std: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare baseline and ring HDL dead-time CSVs and generate comparison plots."
    )
    parser.add_argument("--baseline-csv", required=True, help="Baseline summary CSV from run_multichannel_deadtime_tb.py")
    parser.add_argument("--ring-csv", required=True, help="Ring summary CSV from run_multichannel_deadtime_tb.py")
    parser.add_argument("--out-prefix", required=True, help="Output prefix for the main plot")
    parser.add_argument(
        "--baseline-label",
        default="baseline",
        help="Legend label for the baseline branch.",
    )
    parser.add_argument(
        "--ring-label",
        default="ring",
        help="Legend label for the ring branch.",
    )
    parser.add_argument(
        "--style",
        choices=["editorial", "classic"],
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
        "--csv-out",
        default="",
        help="Optional merged comparison CSV output path.",
    )
    parser.add_argument(
        "--no-delta",
        action="store_true",
        help="Skip writing the delta plot.",
    )
    return parser.parse_args()


def _require_column(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame.columns:
        raise KeyError(f"CSV is missing required column: {name}")
    return frame[name]


def load_summary_csv(path: str, label: str) -> BranchSeries:
    frame = pd.read_csv(path)

    if "dead_fraction_mean" not in frame.columns and "dead_fraction" in frame.columns:
        frame["dead_fraction_mean"] = frame["dead_fraction"]
    if "dead_fraction_std" not in frame.columns:
        frame["dead_fraction_std"] = 0.0

    for column in ("busy_counter_total_mean", "busy_counter_total_std", "full_counter_total_mean", "full_counter_total_std", "sent_total_mean"):
        if column not in frame.columns:
            raise KeyError(f"CSV is missing required column: {column}")

    frame = frame.sort_values("rate_hz_per_channel").reset_index(drop=True)

    rate_hz = _require_column(frame, "rate_hz_per_channel").to_numpy(dtype=float)
    sent_total = _require_column(frame, "sent_total_mean").to_numpy(dtype=float)
    sent_total = np.where(sent_total > 0.0, sent_total, np.nan)

    dead_pct = _require_column(frame, "dead_fraction_mean").to_numpy(dtype=float) * 100.0
    dead_pct_std = _require_column(frame, "dead_fraction_std").to_numpy(dtype=float) * 100.0

    busy_mean = _require_column(frame, "busy_counter_total_mean").to_numpy(dtype=float)
    busy_std = _require_column(frame, "busy_counter_total_std").to_numpy(dtype=float)
    full_mean = _require_column(frame, "full_counter_total_mean").to_numpy(dtype=float)
    full_std = _require_column(frame, "full_counter_total_std").to_numpy(dtype=float)

    busy_pct = 100.0 * busy_mean / sent_total
    busy_pct_std = 100.0 * busy_std / sent_total
    full_pct = 100.0 * full_mean / sent_total
    full_pct_std = 100.0 * full_std / sent_total

    return BranchSeries(
        label=label,
        rate_hz=rate_hz,
        dead_pct=dead_pct,
        dead_pct_std=dead_pct_std,
        busy_pct=busy_pct,
        busy_pct_std=busy_pct_std,
        full_pct=full_pct,
        full_pct_std=full_pct_std,
    )


def interp_nan(x_src: np.ndarray, y_src: np.ndarray, x_target: np.ndarray) -> np.ndarray:
    mask = np.isfinite(x_src) & np.isfinite(y_src)
    x_src = x_src[mask]
    y_src = y_src[mask]
    if x_src.size == 0:
        return np.full_like(x_target, np.nan, dtype=float)
    order = np.argsort(x_src)
    x_src = x_src[order]
    y_src = y_src[order]
    unique_x, unique_idx = np.unique(x_src, return_index=True)
    unique_y = y_src[unique_idx]
    out = np.interp(x_target, unique_x, unique_y)
    outside = (x_target < unique_x[0]) | (x_target > unique_x[-1])
    out = out.astype(float, copy=False)
    out[outside] = np.nan
    return out


def union_grid(*series: BranchSeries) -> np.ndarray:
    points = np.unique(np.concatenate([item.rate_hz for item in series]))
    return points.astype(float)


def branch_table(baseline: BranchSeries, ring: BranchSeries) -> pd.DataFrame:
    grid = union_grid(baseline, ring)

    baseline_dead = interp_nan(baseline.rate_hz, baseline.dead_pct, grid)
    baseline_dead_std = interp_nan(baseline.rate_hz, baseline.dead_pct_std, grid)
    baseline_busy = interp_nan(baseline.rate_hz, baseline.busy_pct, grid)
    baseline_busy_std = interp_nan(baseline.rate_hz, baseline.busy_pct_std, grid)
    baseline_full = interp_nan(baseline.rate_hz, baseline.full_pct, grid)
    baseline_full_std = interp_nan(baseline.rate_hz, baseline.full_pct_std, grid)

    ring_dead = interp_nan(ring.rate_hz, ring.dead_pct, grid)
    ring_dead_std = interp_nan(ring.rate_hz, ring.dead_pct_std, grid)
    ring_busy = interp_nan(ring.rate_hz, ring.busy_pct, grid)
    ring_busy_std = interp_nan(ring.rate_hz, ring.busy_pct_std, grid)
    ring_full = interp_nan(ring.rate_hz, ring.full_pct, grid)
    ring_full_std = interp_nan(ring.rate_hz, ring.full_pct_std, grid)

    delta_dead = ring_dead - baseline_dead
    delta_busy = ring_busy - baseline_busy
    delta_full = ring_full - baseline_full
    delta_dead_std = np.sqrt(np.square(ring_dead_std) + np.square(baseline_dead_std))
    delta_busy_std = np.sqrt(np.square(ring_busy_std) + np.square(baseline_busy_std))
    delta_full_std = np.sqrt(np.square(ring_full_std) + np.square(baseline_full_std))

    return pd.DataFrame(
        {
            "rate_hz_per_channel": grid.astype(int),
            "rate_khz_per_channel": grid / 1.0e3,
            "baseline_dead_pct_mean": baseline_dead,
            "baseline_dead_pct_std": baseline_dead_std,
            "ring_dead_pct_mean": ring_dead,
            "ring_dead_pct_std": ring_dead_std,
            "baseline_busy_pct_mean": baseline_busy,
            "baseline_busy_pct_std": baseline_busy_std,
            "ring_busy_pct_mean": ring_busy,
            "ring_busy_pct_std": ring_busy_std,
            "baseline_full_pct_mean": baseline_full,
            "baseline_full_pct_std": baseline_full_std,
            "ring_full_pct_mean": ring_full,
            "ring_full_pct_std": ring_full_std,
            "delta_dead_pct_mean": delta_dead,
            "delta_dead_pct_std": delta_dead_std,
            "delta_busy_pct_mean": delta_busy,
            "delta_busy_pct_std": delta_busy_std,
            "delta_full_pct_mean": delta_full,
            "delta_full_pct_std": delta_full_std,
        }
    )


def setup_rcparams(style: str, font_profile: str) -> None:
    if font_profile == "jetbrains":
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
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
    }
    if style == "classic":
        rc_updates.update(
            {
                "axes.linewidth": 0.8,
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


def plot_main(df: pd.DataFrame, baseline_label: str, ring_label: str, style: str, out_prefix: Path) -> None:
    if style == "classic":
        fig, (ax_total, ax_components) = plt.subplots(2, 1, figsize=(5.1, 5.4), constrained_layout=True)
    else:
        fig, (ax_total, ax_components) = plt.subplots(2, 1, figsize=(4.6, 4.9), constrained_layout=True)

    baseline_color = "#202020" if style == "editorial" else "#111111"
    ring_color = "#4c78a8" if style == "editorial" else "#1f77b4"
    muted = "#6a6a6a"

    rate_khz = df["rate_khz_per_channel"].to_numpy(dtype=float)

    def errorbar(ax, x, y, yerr, label, color, marker, linestyle="-"):
        ax.errorbar(
            x,
            y,
            yerr=yerr,
            linestyle=linestyle,
            marker=marker,
            markersize=4.0 if style == "editorial" else 3.6,
            markerfacecolor="white",
            markeredgecolor=color,
            markeredgewidth=1.0,
            ecolor=color,
            color=color,
            linewidth=1.35 if style == "editorial" else 1.45,
            capsize=1.4 if style == "editorial" else 1.2,
            label=label,
            zorder=3,
        )

    errorbar(
        ax_total,
        rate_khz,
        df["baseline_dead_pct_mean"].to_numpy(dtype=float),
        df["baseline_dead_pct_std"].to_numpy(dtype=float),
        baseline_label,
        baseline_color,
        "o",
    )
    errorbar(
        ax_total,
        rate_khz,
        df["ring_dead_pct_mean"].to_numpy(dtype=float),
        df["ring_dead_pct_std"].to_numpy(dtype=float),
        ring_label,
        ring_color,
        "s",
    )

    ax_total.axhline(0.0, color=muted, linewidth=0.8, zorder=1)
    ax_total.set_ylabel("Total dead time (%)")
    ax_total.set_xlabel("Per-channel trigger rate (kHz)")
    ax_total.xaxis.set_major_locator(MultipleLocator(2.0))
    ax_total.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax_total.yaxis.set_major_locator(MultipleLocator(5.0))
    ax_total.yaxis.set_minor_locator(MultipleLocator(2.5))
    ax_total.set_xlim(0.0, max(15.0, float(np.nanmax(rate_khz)) * 1.05))
    ax_total.set_ylim(bottom=0.0)
    ax_total.legend(frameon=False, loc="upper left", fontsize=7.0)
    ax_total.text(
        0.02,
        0.97,
        "Total dead time",
        transform=ax_total.transAxes,
        ha="left",
        va="top",
        color=muted,
        fontsize=7.0,
    )

    errorbar(
        ax_components,
        rate_khz,
        df["baseline_busy_pct_mean"].to_numpy(dtype=float),
        df["baseline_busy_pct_std"].to_numpy(dtype=float),
        f"{baseline_label} busy",
        baseline_color,
        "o",
    )
    errorbar(
        ax_components,
        rate_khz,
        df["baseline_full_pct_mean"].to_numpy(dtype=float),
        df["baseline_full_pct_std"].to_numpy(dtype=float),
        f"{baseline_label} full",
        baseline_color,
        "o",
        linestyle="--",
    )
    errorbar(
        ax_components,
        rate_khz,
        df["ring_busy_pct_mean"].to_numpy(dtype=float),
        df["ring_busy_pct_std"].to_numpy(dtype=float),
        f"{ring_label} busy",
        ring_color,
        "s",
    )
    errorbar(
        ax_components,
        rate_khz,
        df["ring_full_pct_mean"].to_numpy(dtype=float),
        df["ring_full_pct_std"].to_numpy(dtype=float),
        f"{ring_label} full",
        ring_color,
        "s",
        linestyle="--",
    )

    ax_components.axhline(0.0, color=muted, linewidth=0.8, zorder=1)
    ax_components.set_xlabel("Per-channel trigger rate (kHz)")
    ax_components.set_ylabel("Drop fraction (%)")
    ax_components.xaxis.set_major_locator(MultipleLocator(2.0))
    ax_components.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax_components.yaxis.set_major_locator(MultipleLocator(2.0))
    ax_components.yaxis.set_minor_locator(MultipleLocator(1.0))
    ax_components.set_xlim(0.0, max(15.0, float(np.nanmax(rate_khz)) * 1.05))
    ax_components.set_ylim(bottom=0.0)
    ax_components.legend(frameon=False, loc="upper left", fontsize=6.6, ncol=2)
    ax_components.text(
        0.02,
        0.97,
        "Busy and FIFO-full components",
        transform=ax_components.transAxes,
        ha="left",
        va="top",
        color=muted,
        fontsize=7.0,
    )

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_prefix.with_suffix(".png"), dpi=400)
    fig.savefig(out_prefix.with_suffix(".pdf"))
    fig.savefig(out_prefix.with_suffix(".svg"))


def plot_delta(df: pd.DataFrame, style: str, out_prefix: Path) -> None:
    if style == "classic":
        fig, ax = plt.subplots(figsize=(4.4, 3.1), constrained_layout=True)
    else:
        fig, ax = plt.subplots(figsize=(4.0, 2.9), constrained_layout=True)

    rate_khz = df["rate_khz_per_channel"].to_numpy(dtype=float)
    colors = {
        "delta_dead_pct_mean": "#111111",
        "delta_busy_pct_mean": "#4c78a8",
        "delta_full_pct_mean": "#b07aa1",
    }
    labels = {
        "delta_dead_pct_mean": "total",
        "delta_busy_pct_mean": "busy",
        "delta_full_pct_mean": "full",
    }
    markers = {
        "delta_dead_pct_mean": "o",
        "delta_busy_pct_mean": "s",
        "delta_full_pct_mean": "^",
    }

    for key in ("delta_dead_pct_mean", "delta_busy_pct_mean", "delta_full_pct_mean"):
        ax.errorbar(
            rate_khz,
            df[key].to_numpy(dtype=float),
            yerr=df[key.replace("_mean", "_std")].to_numpy(dtype=float),
            linestyle="-",
            marker=markers[key],
            markersize=3.8,
            markerfacecolor="white",
            markeredgecolor=colors[key],
            markeredgewidth=1.0,
            ecolor=colors[key],
            color=colors[key],
            linewidth=1.25,
            capsize=1.2,
            label=labels[key],
            zorder=3,
        )

    ax.axhline(0.0, color="#6a6a6a", linewidth=0.8, zorder=1)
    ax.set_xlabel("Per-channel trigger rate (kHz)")
    ax.set_ylabel("Ring - baseline (p.p.)")
    ax.xaxis.set_major_locator(MultipleLocator(2.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.yaxis.set_minor_locator(MultipleLocator(0.5))
    ax.set_xlim(0.0, max(15.0, float(np.nanmax(rate_khz)) * 1.05))

    delta_cols = [
        "delta_dead_pct_mean",
        "delta_busy_pct_mean",
        "delta_full_pct_mean",
        "delta_dead_pct_std",
        "delta_busy_pct_std",
        "delta_full_pct_std",
    ]
    max_abs = 0.5
    for col in delta_cols:
        values = np.abs(df[col].to_numpy(dtype=float))
        finite = np.isfinite(values)
        if finite.any():
            max_abs = max(max_abs, float(np.nanmax(values[finite])))
    ax.set_ylim(-1.15 * max_abs, 1.15 * max_abs)
    ax.legend(frameon=False, loc="upper right", fontsize=7.0)
    ax.text(
        0.02,
        0.97,
        "Ring minus baseline",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color="#6a6a6a",
        fontsize=7.0,
    )

    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_prefix.with_suffix(".png"), dpi=400)
    fig.savefig(out_prefix.with_suffix(".pdf"))
    fig.savefig(out_prefix.with_suffix(".svg"))


def main() -> None:
    args = parse_args()
    setup_rcparams(args.style, args.font_profile)

    baseline = load_summary_csv(args.baseline_csv, args.baseline_label)
    ring = load_summary_csv(args.ring_csv, args.ring_label)
    comparison = branch_table(baseline, ring)

    if args.csv_out:
        csv_path = Path(args.csv_out)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        comparison.to_csv(csv_path, index=False)

    out_prefix = Path(args.out_prefix)
    plot_main(comparison, baseline.label, ring.label, args.style, out_prefix)
    if not args.no_delta:
        plot_delta(comparison, args.style, out_prefix.with_name(out_prefix.name + "_delta"))


if __name__ == "__main__":
    main()
