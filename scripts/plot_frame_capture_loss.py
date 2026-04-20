#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot pulse cut fraction and dead-time loss fraction versus frame length."
    )
    parser.add_argument("summary_csv", type=Path, help="CSV from study_frame_capture_loss.py")
    parser.add_argument("--out-prefix", type=Path, required=True, help="Output prefix for PDF/SVG/PNG")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = []
    with args.summary_csv.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                frame_len = int(row["label"])
            except ValueError:
                continue
            rows.append(
                (
                    frame_len,
                    100.0 * float(row["cut_fraction"]),
                    100.0 * float(row["deadtime_lost_fraction"]),
                    int(row["cut_pulses"]),
                    int(row["deadtime_lost_pulses"]),
                    int(row["reference_pulses"]),
                )
            )
    rows.sort(key=lambda item: item[0])

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
        }
    )

    fig, ax = plt.subplots(figsize=(5.8, 3.8), constrained_layout=True)
    x = [row[0] for row in rows]
    y_cut = [row[1] for row in rows]
    y_dead = [row[2] for row in rows]

    ax.plot(x, y_cut, color="#6a6a6a", marker="s", linewidth=1.5, markersize=4.5, label="Cut by frame window")
    ax.plot(x, y_dead, color="#111111", marker="o", linewidth=1.8, markersize=4.8, label="Lost to dead time")

    for frame_len, cut_pct, dead_pct, cut_count, dead_count, ref_count in rows:
        ax.annotate(
            f"{dead_count}/{ref_count}",
            xy=(frame_len, dead_pct),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#111111",
        )

    ax.set_xlabel("Frame length [samples]")
    ax.set_ylabel("Pulse loss fraction [%]")
    ax.set_ylim(0, max(max(y_cut), max(y_dead), 0.5) * 1.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper right")

    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".pdf", ".svg", ".png"):
        fig.savefig(args.out_prefix.with_suffix(suffix), dpi=300)


if __name__ == "__main__":
    main()
