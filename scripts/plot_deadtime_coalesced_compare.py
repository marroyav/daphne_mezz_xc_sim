#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import MultipleLocator


@dataclass(frozen=True)
class SimCase:
    key: str
    label: str
    color: str
    args: tuple[str, ...]


CASES = (
    SimCase("ring0", "512 + ring0", "#92DDF2", ("--architecture", "ring", "--signal-delay-steps", "0")),
    SimCase("ring50", "512 + ring50", "#96D6AE", ("--architecture", "ring", "--signal-delay-steps", "16")),
    SimCase(
        "coalesced",
        "coalesced, inherited FIFO gate",
        "#F2682B",
        ("--architecture", "coalesced"),
    ),
    SimCase(
        "coalesced_open",
        "coalesced, output gate relaxed",
        "#D8B365",
        ("--architecture", "coalesced", "--prog-full-thresh", "1000000"),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run and plot the ring/coalesced dead-time comparison."
    )
    parser.add_argument("--rate-start", type=int, default=200)
    parser.add_argument("--rate-stop", type=int, default=20000)
    parser.add_argument("--points", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--warmup-cycles", type=int, default=20000)
    parser.add_argument("--measure-cycles", type=int, default=200000)
    parser.add_argument("--reference-rate-hz", type=float, default=4600.0)
    parser.add_argument("--analysis-dir", default="data/output/analysis")
    parser.add_argument("--plot-dir", default="data/output/plots")
    parser.add_argument(
        "--presentation-dir",
        default="",
        help="Optional directory where rendered plot/diagram files are copied.",
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Use existing CSVs instead of rerunning the simulator.",
    )
    return parser.parse_args()


def run(cmd: list[str], cwd: Path) -> None:
    print("RUN", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        raise subprocess.CalledProcessError(result.returncode, cmd)


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "font.size": 8,
            "axes.labelsize": 8,
            "axes.titlesize": 9,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.7,
            "figure.facecolor": "#131B24",
            "axes.facecolor": "#1C2834",
            "savefig.facecolor": "#131B24",
            "text.color": "#ECF1F4",
            "axes.labelcolor": "#ECF1F4",
            "axes.edgecolor": "#C4CDD5",
            "xtick.color": "#C4CDD5",
            "ytick.color": "#C4CDD5",
        }
    )


def load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path).sort_values("rate_hz_per_channel").reset_index(drop=True)
    if "dead_fraction_std" not in frame.columns:
        frame["dead_fraction_std"] = 0.0
    return frame


def write_outputs(fig: plt.Figure, prefix: Path) -> list[Path]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    outputs = [
        prefix.with_suffix(".png"),
        prefix.with_suffix(".pdf"),
        prefix.with_suffix(".svg"),
    ]
    fig.savefig(outputs[0], dpi=220)
    fig.savefig(outputs[1])
    fig.savefig(outputs[2])
    return outputs


def box(ax, xy, width, height, label, face="#223344", edge="#92DDF2", text="#ECF1F4", fontsize=8):
    patch = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.035",
        linewidth=1.0,
        edgecolor=edge,
        facecolor=face,
    )
    ax.add_patch(patch)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        label,
        ha="center",
        va="center",
        color=text,
        fontsize=fontsize,
        linespacing=1.15,
    )


def arrow(ax, start, end, color="#C4CDD5", lw=1.1):
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        arrowprops={"arrowstyle": "->", "color": color, "linewidth": lw, "shrinkA": 3, "shrinkB": 3},
    )


def plot_compare(csvs: dict[str, Path], out_prefix: Path, reference_rate_hz: float) -> list[Path]:
    fig, (ax, cause_ax) = plt.subplots(
        2,
        1,
        figsize=(6.3, 5.15),
        gridspec_kw={"height_ratios": [2.2, 1.0]},
        constrained_layout=True,
    )

    y_max = 0.0
    for case in CASES:
        frame = load(csvs[case.key])
        x = frame["rate_hz_per_channel"].to_numpy(dtype=float) / 1.0e3
        y = frame["dead_fraction_mean"].to_numpy(dtype=float) * 100.0
        yerr = frame["dead_fraction_std"].to_numpy(dtype=float) * 100.0
        y_max = max(y_max, float(np.max(y + yerr)))
        ax.plot(x, y, label=case.label, color=case.color, linewidth=1.5)
        ax.fill_between(x, y - yerr, y + yerr, color=case.color, alpha=0.10, linewidth=0.0)

    ax.axvline(reference_rate_hz / 1.0e3, color="#C4CDD5", linewidth=0.8, linestyle="--", dashes=(3, 3))
    ax.set_title("Ring versus coalesced non-overlap model")
    ax.set_xlabel("Per-channel trigger rate (kHz)")
    ax.set_ylabel("Dead time (%)")
    ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.38)
    ax.xaxis.set_major_locator(MultipleLocator(2.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(10.0))
    ax.yaxis.set_minor_locator(MultipleLocator(5.0))
    ax.set_xlim(0.0, 20.2)
    ax.set_ylim(0.0, max(52.0, y_max * 1.08))
    legend = ax.legend(frameon=False, loc="upper left", fontsize=7.0)
    for text in legend.get_texts():
        text.set_color("#ECF1F4")

    coalesced = load(csvs["coalesced"])
    x = coalesced["rate_hz_per_channel"].to_numpy(dtype=float) / 1.0e3
    generated = coalesced["generated_total_mean"].to_numpy(dtype=float)
    denom = np.maximum(generated, 1.0)
    full = coalesced["full_counter_total_mean"].to_numpy(dtype=float) / denom * 100.0
    ring = coalesced["ring_counter_total_mean"].to_numpy(dtype=float) / denom * 100.0
    queue = coalesced["queue_counter_total_mean"].to_numpy(dtype=float) / denom * 100.0
    spacing = coalesced["spacing_counter_total_mean"].to_numpy(dtype=float) / denom * 100.0

    cause_ax.stackplot(
        x,
        full,
        ring,
        queue,
        spacing,
        colors=["#F2682B", "#92DDF2", "#D8B365", "#96D6AE"],
        labels=["output-full", "ring retention", "queue", "spacing"],
        alpha=0.88,
    )
    cause_ax.set_title("Coalesced model reject causes with inherited FIFO gate")
    cause_ax.set_xlabel("Per-channel trigger rate (kHz)")
    cause_ax.set_ylabel("Rejects / generated (%)")
    cause_ax.grid(axis="y", color="#556779", linewidth=0.55, alpha=0.38)
    cause_ax.xaxis.set_major_locator(MultipleLocator(2.0))
    cause_ax.set_xlim(0.0, 20.2)
    cause_ax.set_ylim(bottom=0.0)
    cause_legend = cause_ax.legend(frameon=False, loc="upper left", ncol=4, fontsize=6.8)
    for text in cause_legend.get_texts():
        text.set_color("#ECF1F4")

    ax.text(
        0.985,
        0.03,
        "coalesced/open-gate is an acceptance-side upper bound, not a transport signoff",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=6.6,
        color="#C4CDD5",
    )

    return write_outputs(fig, out_prefix)


def plot_timeline(out_prefix: Path) -> list[Path]:
    fig, ax = plt.subplots(figsize=(6.3, 2.7), constrained_layout=True)
    ax.set_axis_off()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)

    ax.text(0.1, 3.75, "Same two triggers, two output policies", fontsize=10, weight="bold")
    ax.text(1.35, 3.35, "T1", color="#ECF1F4", ha="center")
    ax.text(3.55, 3.35, "T2", color="#ECF1F4", ha="center")
    ax.plot([0.8, 8.8], [3.1, 3.1], color="#C4CDD5", linewidth=1.0)
    ax.plot([1.35, 1.35], [2.95, 3.25], color="#ECF1F4", linewidth=1.1)
    ax.plot([3.55, 3.55], [2.95, 3.25], color="#ECF1F4", linewidth=1.1)

    ax.text(0.35, 2.45, "ring50", ha="left", va="center", fontsize=8)
    ax.add_patch(Rectangle((1.0, 2.15), 4.2, 0.42, color="#96D6AE", alpha=0.88))
    ax.add_patch(Rectangle((3.2, 1.72), 4.2, 0.42, color="#92DDF2", alpha=0.88))
    ax.text(3.1, 2.36, "frame 1", ha="center", va="center", fontsize=7, color="#131B24")
    ax.text(5.3, 1.93, "frame 2", ha="center", va="center", fontsize=7, color="#131B24")
    ax.text(4.2, 1.42, "overlap samples emitted twice", ha="center", va="center", fontsize=7, color="#F2682B")

    ax.text(0.35, 0.95, "coalesced", ha="left", va="center", fontsize=8)
    ax.add_patch(Rectangle((1.0, 0.72), 6.4, 0.5, color="#D8B365", alpha=0.92))
    ax.text(4.2, 0.97, "one non-overlapping interval", ha="center", va="center", fontsize=7, color="#131B24")
    ax.text(4.2, 0.42, "metadata: T1, T2", ha="center", va="center", fontsize=7, color="#ECF1F4")

    return write_outputs(fig, out_prefix)


def plot_pipeline(out_prefix: Path) -> list[Path]:
    fig, ax = plt.subplots(figsize=(6.3, 3.2), constrained_layout=True)
    ax.set_axis_off()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)

    ax.text(0.1, 4.65, "Coalesced path: where the pressure moves", fontsize=10, weight="bold")

    box(ax, (0.25, 3.25), 1.35, 0.75, "samples")
    box(ax, (2.05, 3.25), 1.55, 0.75, "2k ring\nper channel", face="#263847")
    box(ax, (4.05, 3.25), 1.7, 0.75, "metadata\nqueue", face="#263847")
    box(ax, (6.25, 3.25), 1.55, 0.75, "coalescer", face="#352E23", edge="#D8B365")
    box(ax, (8.25, 3.25), 1.35, 0.75, "packer", face="#263847")

    box(ax, (0.25, 1.35), 1.35, 0.75, "trigger")
    box(ax, (2.05, 1.35), 1.55, 0.75, "accept\nmetadata", face="#263847")
    box(ax, (4.05, 1.35), 1.7, 0.75, "output FIFO", face="#3B2730", edge="#F2682B")
    box(ax, (6.25, 1.35), 1.55, 0.75, "2-lane mux", face="#263847")
    box(ax, (8.25, 1.35), 1.35, 0.75, "Hermes\ninput", face="#263847")

    for start, end in [
        ((1.6, 3.62), (2.05, 3.62)),
        ((3.6, 3.62), (4.05, 3.62)),
        ((5.75, 3.62), (6.25, 3.62)),
        ((7.8, 3.62), (8.25, 3.62)),
        ((1.6, 1.72), (2.05, 1.72)),
        ((3.6, 1.72), (4.05, 1.72)),
        ((5.75, 1.72), (6.25, 1.72)),
        ((7.8, 1.72), (8.25, 1.72)),
        ((8.95, 3.25), (4.9, 2.1)),
    ]:
        arrow(ax, start, end)

    ax.text(4.8, 0.65, "default coalesced run: spacing rejects vanish; output-full becomes dominant", ha="center", fontsize=7.4)

    return write_outputs(fig, out_prefix)


def copy_for_presentation(paths: list[Path], presentation_dir: Path) -> None:
    presentation_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, presentation_dir / path.name)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    analysis_dir = (repo_root / args.analysis_dir).resolve()
    plot_dir = (repo_root / args.plot_dir).resolve()
    analysis_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_run:
        run(["make", "ring_deadtime_sim"], repo_root)

    csvs: dict[str, Path] = {}
    common = [
        "--rate-start",
        str(args.rate_start),
        "--rate-stop",
        str(args.rate_stop),
        "--points",
        str(args.points),
        "--repeats",
        str(args.repeats),
        "--warmup-cycles",
        str(args.warmup_cycles),
        "--measure-cycles",
        str(args.measure_cycles),
    ]

    for case in CASES:
        csv_path = analysis_dir / f"deadtime_{case.key}_coalesced_compare.csv"
        raw_path = analysis_dir / f"deadtime_{case.key}_coalesced_compare_raw.csv"
        csvs[case.key] = csv_path
        if not args.skip_run:
            run(
                [
                    "./ring_deadtime_sim",
                    *case.args,
                    "--csv-out",
                    str(csv_path),
                    "--raw-csv-out",
                    str(raw_path),
                    *common,
                ],
                repo_root,
            )

    setup_style()
    outputs: list[Path] = []
    outputs.extend(plot_compare(csvs, plot_dir / "deadtime_coalesced_compare", args.reference_rate_hz))
    outputs.extend(plot_timeline(plot_dir / "deadtime_coalescing_timeline"))
    outputs.extend(plot_pipeline(plot_dir / "deadtime_coalesced_pipeline"))

    if args.presentation_dir:
        copy_for_presentation(outputs, Path(args.presentation_dir).expanduser().resolve())

    print("WROTE")
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
