#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot descriptor loss fraction as a function of frame length."
    )
    parser.add_argument("summary_csv", type=Path, help="Summary CSV from study_descriptor_window_loss.py")
    parser.add_argument(
        "--out-prefix",
        type=Path,
        required=True,
        help="Output prefix for PDF/SVG/PNG files",
    )
    return parser.parse_args()


def load_rows(path: Path) -> dict[str, list[tuple[int, float, float]]]:
    grouped: dict[str, list[tuple[int, float, float]]] = {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            dataset = row["dataset"]
            frame_length = int(row["frame_length"])
            lost_fraction = float(row["lost_fraction"])
            lost_additional_fraction = float(row["lost_additional_fraction"])
            grouped.setdefault(dataset, []).append((frame_length, lost_fraction, lost_additional_fraction))
    for rows in grouped.values():
        rows.sort(key=lambda item: item[0])
    return grouped


def main() -> None:
    args = parse_args()
    grouped = load_rows(args.summary_csv)

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
        }
    )

    fig, ax = plt.subplots(figsize=(6.0, 3.8), constrained_layout=True)

    colors = ["#111111", "#5c5c5c", "#9a9a9a"]
    markers = ["o", "s", "^"]
    for (dataset, rows), color, marker in zip(sorted(grouped.items()), colors, markers):
        frame_lengths = [row[0] for row in rows]
        lost_fraction = [100.0 * row[1] for row in rows]
        lost_additional_fraction = [100.0 * row[2] for row in rows]
        ax.plot(
            frame_lengths,
            lost_fraction,
            color=color,
            marker=marker,
            linewidth=1.8,
            markersize=4.5,
            label=f"{dataset} total",
        )
        ax.plot(
            frame_lengths,
            lost_additional_fraction,
            color=color,
            linestyle="--",
            linewidth=1.2,
            alpha=0.9,
            label=f"{dataset} additional",
        )

    ax.set_xlabel("Frame length [samples]")
    ax.set_ylabel("Descriptors truncated [%]")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper right")

    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".pdf", ".svg", ".png"):
        fig.savefig(args.out_prefix.with_suffix(suffix), dpi=300)


if __name__ == "__main__":
    main()
