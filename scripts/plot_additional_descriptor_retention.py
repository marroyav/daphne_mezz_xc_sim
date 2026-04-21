#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot additional-descriptor retention versus frame length from compare_descriptor_runs output."
    )
    parser.add_argument("compare_csv", type=Path, help="CSV produced by compare_descriptor_runs.py")
    parser.add_argument("--reference", required=True, help="Reference label, for example 2048")
    parser.add_argument("--out-prefix", type=Path, required=True, help="Output prefix for PDF/SVG/PNG")
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    args = parse_args()
    rows = load_rows(args.compare_csv)
    ref_rows = [row for row in rows if row["label"] == args.reference]
    if not ref_rows:
        raise SystemExit(f"Reference label {args.reference!r} not found in {args.compare_csv}")
    ref_additional = int(ref_rows[0]["additional_descriptors"])
    if ref_additional <= 0:
        raise SystemExit("Reference run has no additional descriptors; retention is undefined")

    data = []
    for row in rows:
        try:
            frame_len = int(row["label"])
            additional = int(row["additional_descriptors"])
        except ValueError:
            continue
        retention = 100.0 * additional / ref_additional
        data.append((frame_len, additional, retention))

    data.sort(key=lambda item: item[0])

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
        }
    )

    fig, ax = plt.subplots(figsize=(5.6, 3.6), constrained_layout=True)

    frame_lengths = [item[0] for item in data]
    retention = [item[2] for item in data]
    additional = [item[1] for item in data]

    ax.plot(
        frame_lengths,
        retention,
        color="#111111",
        marker="o",
        linewidth=1.8,
        markersize=4.8,
    )
    ax.axhline(100.0, color="#6a6a6a", linewidth=0.9, linestyle="--")

    for x, add_count, y in zip(frame_lengths, additional, retention):
        ax.annotate(
            f"{add_count}/{ref_additional}",
            xy=(x, y),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#222222",
        )

    ax.set_xlabel("Frame length [samples]")
    ax.set_ylabel("Additional descriptor retention [%]")
    ax.set_xlim(min(frame_lengths) - 50, max(frame_lengths) + 80)
    ax.set_ylim(0, 110)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    args.out_prefix.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".pdf", ".svg", ".png"):
        fig.savefig(args.out_prefix.with_suffix(suffix), dpi=300)


if __name__ == "__main__":
    main()
