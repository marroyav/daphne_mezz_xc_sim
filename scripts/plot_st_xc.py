#!/usr/bin/env python3
import csv
import os
import sys

import matplotlib.pyplot as plt


def main(path, scale):
    xs = []
    raw = []
    xcorr = []
    trig = []

    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            xs.append(int(row["index"]))
            raw.append(int(row["raw"]))
            if "xcorr_proc" in row and row["xcorr_proc"] != "":
                xcorr.append(int(row["xcorr_proc"]))
            else:
                xcorr.append(int(row["xcorr"]))
            trig.append(int(row["trigger"]))

    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax1.plot(xs, raw, label="raw", linewidth=1)
    xcorr_scaled = [v / scale for v in xcorr]
    ax1.plot(xs, xcorr_scaled, label=f"xcorr_proc / {scale}", linewidth=1)
    ax1.set_xlabel("sample index")
    ax1.set_ylabel("raw / xcorr")
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.step(xs, trig, where="post", label="trigger", color="tab:red", linewidth=1)
    ax2.set_ylabel("trigger")
    ax2.set_ylim(-0.1, 1.1)
    ax2.legend(loc="upper right")

    plt.tight_layout()
    if "data/output/analysis" in path:
        base = os.path.splitext(os.path.basename(path))[0]
        out_png = os.path.join("data", "output", "plots", base + ".png")
        os.makedirs(os.path.dirname(out_png), exist_ok=True)
    else:
        out_png = path.rsplit(".", 1)[0] + ".png"
    plt.savefig(out_png, dpi=150)
    print(f"wrote {out_png}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print(f"Usage: {sys.argv[0]} <out.csv> [xcorr_scale]")
        sys.exit(1)
    scale = float(sys.argv[2]) if len(sys.argv) == 3 else 100.0
    main(sys.argv[1], scale)
