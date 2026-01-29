#!/usr/bin/env python3
import csv
import sys

import matplotlib.pyplot as plt


def main(path):
    xs = []
    raw = []
    xcorr = []
    trig = []

    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            xs.append(int(row["index"]))
            raw.append(int(row["raw"]))
            xcorr.append(int(row["xcorr"]))
            trig.append(int(row["trigger"]))

    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax1.plot(xs, raw, label="raw", linewidth=1)
    ax1.plot(xs, xcorr, label="xcorr", linewidth=1)
    ax1.set_xlabel("sample index")
    ax1.set_ylabel("raw / xcorr")
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.step(xs, trig, where="post", label="trigger", color="tab:red", linewidth=1)
    ax2.set_ylabel("trigger")
    ax2.set_ylim(-0.1, 1.1)
    ax2.legend(loc="upper right")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <out.csv>")
        sys.exit(1)
    main(sys.argv[1])
