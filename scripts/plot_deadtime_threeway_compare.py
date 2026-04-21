#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MultipleLocator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare baseline, ring0, and ring50 HDL dead-time summary CSVs."
    )
    parser.add_argument("--baseline-csv", required=True)
    parser.add_argument("--ring0-csv", required=True)
    parser.add_argument("--ring50-csv", required=True)
    parser.add_argument("--out-prefix", required=True)
    parser.add_argument("--csv-out", default="")
    return parser.parse_args()


def load_summary(path: str, prefix: str) -> pd.DataFrame:
    frame = pd.read_csv(path).sort_values("rate_hz_per_channel").reset_index(drop=True)
    renamed = frame.rename(
        columns={
            "repeats": f"{prefix}_repeats",
            "dead_fraction_mean": f"{prefix}_dead_fraction_mean",
            "dead_fraction_std": f"{prefix}_dead_fraction_std",
            "accepted_total_mean": f"{prefix}_accepted_total_mean",
            "accepted_total_std": f"{prefix}_accepted_total_std",
            "busy_counter_total_mean": f"{prefix}_busy_counter_total_mean",
            "busy_counter_total_std": f"{prefix}_busy_counter_total_std",
            "full_counter_total_mean": f"{prefix}_full_counter_total_mean",
            "full_counter_total_std": f"{prefix}_full_counter_total_std",
            "sent_total_mean": f"{prefix}_sent_total_mean",
            "sent_total_std": f"{prefix}_sent_total_std",
        }
    )
    return renamed


def dead_pct(frame: pd.DataFrame, prefix: str) -> np.ndarray:
    return 100.0 * frame[f"{prefix}_dead_fraction_mean"].to_numpy(dtype=float)


def dead_std_pct(frame: pd.DataFrame, prefix: str) -> np.ndarray:
    return 100.0 * frame[f"{prefix}_dead_fraction_std"].to_numpy(dtype=float)


def setup_rcparams() -> None:
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


def write_outputs(fig: plt.Figure, out_prefix: Path) -> None:
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".png", ".pdf", ".svg"):
        fig.savefig(out_prefix.with_suffix(suffix), dpi=300, bbox_inches="tight")


def main() -> None:
    args = parse_args()
    setup_rcparams()

    baseline = load_summary(args.baseline_csv, "baseline")
    ring0 = load_summary(args.ring0_csv, "ring0")
    ring50 = load_summary(args.ring50_csv, "ring50")

    merged = baseline.merge(ring0, on=["rate_hz_per_channel"], how="inner")
    merged = merged.merge(ring50, on=["rate_hz_per_channel"], how="inner")
    merged["rate_khz_per_channel"] = merged["rate_hz_per_channel"] / 1.0e3

    merged["delta_ring0_vs_baseline_pct"] = dead_pct(merged, "ring0") - dead_pct(merged, "baseline")
    merged["delta_ring50_vs_baseline_pct"] = dead_pct(merged, "ring50") - dead_pct(merged, "baseline")
    merged["delta_ring50_vs_ring0_pct"] = dead_pct(merged, "ring50") - dead_pct(merged, "ring0")

    if args.csv_out:
        Path(args.csv_out).parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(args.csv_out, index=False)

    rate_khz = merged["rate_khz_per_channel"].to_numpy(dtype=float)

    fig, (ax_main, ax_delta) = plt.subplots(2, 1, figsize=(4.8, 5.2), constrained_layout=True)

    styles = [
        ("baseline", "#202020", "o", "baseline"),
        ("ring0", "#4c78a8", "s", "ring, 0% overlap"),
        ("ring50", "#d17c18", "^", "ring, 50% overlap"),
    ]

    for prefix, color, marker, label in styles:
        ax_main.errorbar(
            rate_khz,
            dead_pct(merged, prefix),
            yerr=dead_std_pct(merged, prefix),
            color=color,
            marker=marker,
            linewidth=1.1,
            markersize=3.5,
            capsize=2.2,
            label=label,
        )

    ax_main.set_ylabel("Dead time [%]")
    ax_main.set_xlabel("Rate [kHz/channel]")
    ax_main.xaxis.set_major_locator(MultipleLocator(2))
    ax_main.xaxis.set_minor_locator(MultipleLocator(1))
    ax_main.yaxis.set_minor_locator(MultipleLocator(1))
    ax_main.grid(True, which="major", alpha=0.18, linewidth=0.5)
    ax_main.grid(True, which="minor", alpha=0.08, linewidth=0.4)
    ax_main.legend(frameon=False, loc="upper left")

    ax_delta.axhline(0.0, color="#505050", linewidth=0.8, linestyle="--")
    ax_delta.plot(
        rate_khz,
        merged["delta_ring0_vs_baseline_pct"].to_numpy(dtype=float),
        color="#4c78a8",
        marker="s",
        linewidth=1.0,
        markersize=3.2,
        label="ring0 - baseline",
    )
    ax_delta.plot(
        rate_khz,
        merged["delta_ring50_vs_baseline_pct"].to_numpy(dtype=float),
        color="#d17c18",
        marker="^",
        linewidth=1.0,
        markersize=3.2,
        label="ring50 - baseline",
    )
    ax_delta.plot(
        rate_khz,
        merged["delta_ring50_vs_ring0_pct"].to_numpy(dtype=float),
        color="#1f9d8a",
        marker="D",
        linewidth=1.0,
        markersize=3.0,
        label="ring50 - ring0",
    )
    ax_delta.set_ylabel("Delta [pp]")
    ax_delta.set_xlabel("Rate [kHz/channel]")
    ax_delta.xaxis.set_major_locator(MultipleLocator(2))
    ax_delta.xaxis.set_minor_locator(MultipleLocator(1))
    ax_delta.yaxis.set_minor_locator(MultipleLocator(1))
    ax_delta.grid(True, which="major", alpha=0.18, linewidth=0.5)
    ax_delta.grid(True, which="minor", alpha=0.08, linewidth=0.4)
    ax_delta.legend(frameon=False, loc="lower left")

    write_outputs(fig, Path(args.out_prefix))


if __name__ == "__main__":
    main()
