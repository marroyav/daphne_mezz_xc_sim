#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunSummary:
    label: str
    path: Path
    frame_count: int
    frames_with_descriptors: int
    total_descriptors: int
    primary_descriptors: int
    additional_descriptors: int
    multi_descriptor_frames: int
    max_desc_time_start_full: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare native XC replay runs produced with different frame lengths."
    )
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="LABEL=CSV",
        help="Run label and CSV path, for example 512=data/output/analysis/run_512.csv",
    )
    parser.add_argument(
        "--reference",
        required=True,
        help="Label to use as the comparison reference, for example 2048",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help="Optional CSV output path",
    )
    return parser.parse_args()


def parse_run_arg(item: str) -> tuple[str, Path]:
    if "=" not in item:
        raise ValueError(f"Invalid --run value: {item!r}")
    label, raw_path = item.split("=", 1)
    return label, Path(raw_path)


def summarize_run(label: str, path: Path) -> RunSummary:
    frame_to_count: dict[int, int] = {}
    max_desc_time_start_full = 0

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                frame_id = int(row.get("frame_id") or 0)
                if int(row.get("frame_start") or 0) == 1:
                    frame_to_count.setdefault(frame_id, 0)
                if int(row.get("desc_valid") or 0) != 1:
                    continue
                frame_to_count[frame_id] = frame_to_count.get(frame_id, 0) + 1
                max_desc_time_start_full = max(max_desc_time_start_full, int(row.get("desc_time_start_full") or 0))
            except ValueError:
                continue

    frame_count = len(frame_to_count)
    frames_with_descriptors = sum(count > 0 for count in frame_to_count.values())
    total_descriptors = sum(frame_to_count.values())
    additional_descriptors = sum(max(0, count - 1) for count in frame_to_count.values())
    primary_descriptors = total_descriptors - additional_descriptors
    multi_descriptor_frames = sum(count > 1 for count in frame_to_count.values())

    return RunSummary(
        label=label,
        path=path,
        frame_count=frame_count,
        frames_with_descriptors=frames_with_descriptors,
        total_descriptors=total_descriptors,
        primary_descriptors=primary_descriptors,
        additional_descriptors=additional_descriptors,
        multi_descriptor_frames=multi_descriptor_frames,
        max_desc_time_start_full=max_desc_time_start_full,
    )


def emit_table(summaries: list[RunSummary], reference: RunSummary) -> None:
    print(
        "label  frames  frames_w_desc  total_desc  primary  additional  "
        "multi_frames  loss_vs_ref  add_loss_vs_ref  max_desc_time_start_full"
    )
    for summary in summaries:
        loss_vs_ref = reference.total_descriptors - summary.total_descriptors
        add_loss_vs_ref = reference.additional_descriptors - summary.additional_descriptors
        print(
            f"{summary.label:>5}  "
            f"{summary.frame_count:>6}  "
            f"{summary.frames_with_descriptors:>13}  "
            f"{summary.total_descriptors:>10}  "
            f"{summary.primary_descriptors:>7}  "
            f"{summary.additional_descriptors:>10}  "
            f"{summary.multi_descriptor_frames:>12}  "
            f"{loss_vs_ref:>11}  "
            f"{add_loss_vs_ref:>15}  "
            f"{summary.max_desc_time_start_full:>24}"
        )


def write_csv(path: Path, summaries: list[RunSummary], reference: RunSummary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "label",
                "path",
                "frame_count",
                "frames_with_descriptors",
                "total_descriptors",
                "primary_descriptors",
                "additional_descriptors",
                "multi_descriptor_frames",
                "loss_vs_ref",
                "additional_loss_vs_ref",
                "max_desc_time_start_full",
            ],
        )
        writer.writeheader()
        for summary in summaries:
            writer.writerow(
                {
                    "label": summary.label,
                    "path": str(summary.path),
                    "frame_count": summary.frame_count,
                    "frames_with_descriptors": summary.frames_with_descriptors,
                    "total_descriptors": summary.total_descriptors,
                    "primary_descriptors": summary.primary_descriptors,
                    "additional_descriptors": summary.additional_descriptors,
                    "multi_descriptor_frames": summary.multi_descriptor_frames,
                    "loss_vs_ref": reference.total_descriptors - summary.total_descriptors,
                    "additional_loss_vs_ref": reference.additional_descriptors - summary.additional_descriptors,
                    "max_desc_time_start_full": summary.max_desc_time_start_full,
                }
            )


def main() -> None:
    args = parse_args()
    summaries = [summarize_run(*parse_run_arg(item)) for item in args.run]
    summaries.sort(key=lambda item: int(item.label) if item.label.isdigit() else item.label)

    ref_matches = [summary for summary in summaries if summary.label == args.reference]
    if not ref_matches:
        raise SystemExit(f"Reference label {args.reference!r} not found in --run inputs")
    reference = ref_matches[0]

    emit_table(summaries, reference)
    if args.csv_out is not None:
        write_csv(args.csv_out, summaries, reference)


if __name__ == "__main__":
    main()
