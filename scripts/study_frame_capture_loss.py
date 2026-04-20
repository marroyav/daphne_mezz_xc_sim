#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Pulse:
    start: int
    end: int


@dataclass(frozen=True)
class FrameWindow:
    start: int
    end: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure pulse capture, cut pulses, and dead-time loss as a function "
            "of frame length using a long-frame reference XC replay."
        )
    )
    parser.add_argument("--reference-csv", required=True, type=Path, help="Reference CSV from a long frame-length run")
    parser.add_argument("--reference-label", required=True, help="Reference run label, for example 4096")
    parser.add_argument(
        "--target",
        action="append",
        required=True,
        metavar="LABEL=CSV",
        help="Target frame-length run, for example 512=data/output/analysis/run_512.csv",
    )
    parser.add_argument("--pretrigger", type=int, default=64, help="Frame pretrigger in samples")
    parser.add_argument("--csv-out", type=Path, default=None, help="Optional summary CSV output")
    return parser.parse_args()


def parse_target_arg(item: str) -> tuple[str, Path]:
    if "=" not in item:
        raise ValueError(f"Invalid --target value: {item!r}")
    label, raw_path = item.split("=", 1)
    return label, Path(raw_path)


def load_pulses(path: Path, pretrigger: int) -> list[Pulse]:
    frame_start_index: dict[int, int] = {}
    pulses: list[Pulse] = []

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                sample_index = int(row["index"])
                frame_id = int(row["frame_id"])
            except (KeyError, ValueError):
                continue

            try:
                if int(row.get("frame_start") or 0) == 1:
                    frame_start_index[frame_id] = sample_index - pretrigger
            except ValueError:
                pass

            try:
                if int(row.get("desc_valid") or 0) != 1:
                    continue
                sample0 = frame_start_index[frame_id]
                start = sample0 + int(row.get("desc_time_start_full") or row.get("desc_time_start") or 0)
                width = int(row.get("desc_time_over") or 0)
                end = start + width
                pulses.append(Pulse(start=start, end=end))
            except (KeyError, ValueError):
                continue

    pulses.sort(key=lambda pulse: (pulse.start, pulse.end))
    return pulses


def load_frames(path: Path, pretrigger: int) -> list[FrameWindow]:
    frame_len = None
    frame_start_indices: list[int] = []

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        frame_active_rows = 0
        for row in reader:
            try:
                sample_index = int(row["index"])
            except (KeyError, ValueError):
                continue

            if frame_len is None:
                try:
                    if int(row.get("frame_active") or 0) == 1:
                        frame_active_rows += 1
                    elif frame_active_rows > 0:
                        frame_len = frame_active_rows
                        frame_active_rows = 0
                except ValueError:
                    pass

            try:
                if int(row.get("frame_start") or 0) == 1:
                    frame_start_indices.append(sample_index)
            except ValueError:
                pass

    if frame_len is None:
        raise RuntimeError(f"Could not infer frame length from {path}")
    return [
        FrameWindow(start=sample_index - pretrigger, end=(sample_index - pretrigger) + frame_len - 1)
        for sample_index in frame_start_indices
    ]


def classify_pulse(pulse: Pulse, windows: list[FrameWindow]) -> str:
    overlapped = False
    for window in windows:
        if pulse.end < window.start:
            break
        if pulse.start > window.end:
            continue
        overlapped = True
        if pulse.start >= window.start and pulse.end <= window.end:
            return "captured"
    return "cut" if overlapped else "deadtime_lost"


def main() -> None:
    args = parse_args()

    reference_pulses = load_pulses(args.reference_csv, args.pretrigger)
    target_specs = [parse_target_arg(item) for item in args.target]
    target_specs.sort(key=lambda item: int(item[0]) if item[0].isdigit() else item[0])

    rows = []
    for label, path in target_specs:
        windows = load_frames(path, args.pretrigger)
        captured = 0
        cut = 0
        deadtime_lost = 0
        for pulse in reference_pulses:
            state = classify_pulse(pulse, windows)
            if state == "captured":
                captured += 1
            elif state == "cut":
                cut += 1
            else:
                deadtime_lost += 1
        rows.append(
            {
                "label": label,
                "reference_label": args.reference_label,
                "reference_pulses": len(reference_pulses),
                "captured_pulses": captured,
                "captured_fraction": captured / len(reference_pulses) if reference_pulses else 0.0,
                "cut_pulses": cut,
                "cut_fraction": cut / len(reference_pulses) if reference_pulses else 0.0,
                "deadtime_lost_pulses": deadtime_lost,
                "deadtime_lost_fraction": deadtime_lost / len(reference_pulses) if reference_pulses else 0.0,
            }
        )

    print("label  ref_pulses  captured  captured_%  cut  cut_%  deadtime_lost  deadtime_lost_%")
    for row in rows:
        print(
            f"{row['label']:>5}  "
            f"{row['reference_pulses']:>10}  "
            f"{row['captured_pulses']:>8}  "
            f"{row['captured_fraction']:>10.2%}  "
            f"{row['cut_pulses']:>3}  "
            f"{row['cut_fraction']:>5.2%}  "
            f"{row['deadtime_lost_pulses']:>13}  "
            f"{row['deadtime_lost_fraction']:>16.2%}"
        )

    if args.csv_out is not None:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "label",
                    "reference_label",
                    "reference_pulses",
                    "captured_pulses",
                    "captured_fraction",
                    "cut_pulses",
                    "cut_fraction",
                    "deadtime_lost_pulses",
                    "deadtime_lost_fraction",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
