#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Descriptor:
    sample_start: int
    ordinal_in_frame: int


@dataclass(frozen=True)
class StudyRow:
    dataset: str
    frame_length: int
    frame_count: int
    descriptor_count: int
    lost_descriptors: int
    lost_primary_descriptors: int
    lost_additional_descriptors: int
    frames_with_loss: int
    frames_with_additional_loss: int

    @property
    def retained_descriptors(self) -> int:
        return self.descriptor_count - self.lost_descriptors

    @property
    def lost_fraction(self) -> float:
        if self.descriptor_count == 0:
            return 0.0
        return self.lost_descriptors / self.descriptor_count

    @property
    def lost_primary_fraction(self) -> float:
        if self.descriptor_count == 0:
            return 0.0
        return self.lost_primary_descriptors / self.descriptor_count

    @property
    def lost_additional_fraction(self) -> float:
        if self.descriptor_count == 0:
            return 0.0
        return self.lost_additional_descriptors / self.descriptor_count

    @property
    def frames_with_loss_fraction(self) -> float:
        if self.frame_count == 0:
            return 0.0
        return self.frames_with_loss / self.frame_count

    @property
    def frames_with_additional_loss_fraction(self) -> float:
        if self.frame_count == 0:
            return 0.0
        return self.frames_with_additional_loss / self.frame_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Estimate how many peak descriptors would be truncated for shorter "
            "frame lengths using XC replay CSV output."
        )
    )
    parser.add_argument(
        "csv_files",
        nargs="+",
        type=Path,
        help="XC replay CSV files produced by st_xc_sim",
    )
    parser.add_argument(
        "--window-lengths",
        default="320,512,1024",
        help="Comma-separated frame lengths to evaluate",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help="Optional CSV output path for the study summary",
    )
    return parser.parse_args()


def load_descriptors(path: Path) -> tuple[int, list[Descriptor]]:
    frame_to_desc: dict[int, list[int]] = {}

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                if int(row.get("desc_valid") or 0) != 1:
                    continue
                frame_id = int(row.get("frame_id") or 0)
                sample_start = int(row.get("desc_time_start") or 0)
            except ValueError:
                continue
            frame_to_desc.setdefault(frame_id, []).append(sample_start)

    descriptors: list[Descriptor] = []
    for frame_id in sorted(frame_to_desc):
        sample_starts = frame_to_desc[frame_id]
        for ordinal, sample_start in enumerate(sample_starts, start=1):
            descriptors.append(Descriptor(sample_start=sample_start, ordinal_in_frame=ordinal))

    return len(frame_to_desc), descriptors


def study_dataset(dataset: str, frame_count: int, descriptors: Iterable[Descriptor], frame_length: int) -> StudyRow:
    desc_list = list(descriptors)
    lost_descriptors = 0
    lost_primary_descriptors = 0
    lost_additional_descriptors = 0
    frame_loss_flags: dict[int, bool] = {}
    frame_additional_loss_flags: dict[int, bool] = {}

    # descriptors are ordered by frame already, so count frame transitions manually
    current_frame_idx = -1
    descriptor_in_frame = 0
    for descriptor in desc_list:
        if descriptor.ordinal_in_frame == 1:
            current_frame_idx += 1
            descriptor_in_frame = 1
        else:
            descriptor_in_frame += 1

        lost = descriptor.sample_start >= frame_length
        if not lost:
            continue

        lost_descriptors += 1
        frame_loss_flags[current_frame_idx] = True
        if descriptor_in_frame == 1:
            lost_primary_descriptors += 1
        else:
            lost_additional_descriptors += 1
            frame_additional_loss_flags[current_frame_idx] = True

    return StudyRow(
        dataset=dataset,
        frame_length=frame_length,
        frame_count=frame_count,
        descriptor_count=len(desc_list),
        lost_descriptors=lost_descriptors,
        lost_primary_descriptors=lost_primary_descriptors,
        lost_additional_descriptors=lost_additional_descriptors,
        frames_with_loss=len(frame_loss_flags),
        frames_with_additional_loss=len(frame_additional_loss_flags),
    )


def emit_table(rows: list[StudyRow]) -> None:
    current_dataset = None
    for row in rows:
        if row.dataset != current_dataset:
            current_dataset = row.dataset
            print(current_dataset)
            print(
                "  frame_len  lost_desc  lost_%   lost_primary  lost_additional  "
                "frames_hit  frames_hit_%"
            )
        print(
            f"  {row.frame_length:>9}  "
            f"{row.lost_descriptors:>9}  "
            f"{row.lost_fraction:>6.2%}  "
            f"{row.lost_primary_descriptors:>12}  "
            f"{row.lost_additional_descriptors:>15}  "
            f"{row.frames_with_loss:>10}  "
            f"{row.frames_with_loss_fraction:>11.2%}"
        )


def write_csv(path: Path, rows: list[StudyRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset",
        "frame_length",
        "frame_count",
        "descriptor_count",
        "retained_descriptors",
        "lost_descriptors",
        "lost_fraction",
        "lost_primary_descriptors",
        "lost_primary_fraction",
        "lost_additional_descriptors",
        "lost_additional_fraction",
        "frames_with_loss",
        "frames_with_loss_fraction",
        "frames_with_additional_loss",
        "frames_with_additional_loss_fraction",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "dataset": row.dataset,
                    "frame_length": row.frame_length,
                    "frame_count": row.frame_count,
                    "descriptor_count": row.descriptor_count,
                    "retained_descriptors": row.retained_descriptors,
                    "lost_descriptors": row.lost_descriptors,
                    "lost_fraction": f"{row.lost_fraction:.8f}",
                    "lost_primary_descriptors": row.lost_primary_descriptors,
                    "lost_primary_fraction": f"{row.lost_primary_fraction:.8f}",
                    "lost_additional_descriptors": row.lost_additional_descriptors,
                    "lost_additional_fraction": f"{row.lost_additional_fraction:.8f}",
                    "frames_with_loss": row.frames_with_loss,
                    "frames_with_loss_fraction": f"{row.frames_with_loss_fraction:.8f}",
                    "frames_with_additional_loss": row.frames_with_additional_loss,
                    "frames_with_additional_loss_fraction": f"{row.frames_with_additional_loss_fraction:.8f}",
                }
            )


def main() -> None:
    args = parse_args()
    frame_lengths = [int(item.strip()) for item in args.window_lengths.split(",") if item.strip()]

    rows: list[StudyRow] = []
    for csv_file in args.csv_files:
        frame_count, descriptors = load_descriptors(csv_file)
        dataset = csv_file.stem
        for frame_length in frame_lengths:
            rows.append(study_dataset(dataset, frame_count, descriptors, frame_length))

    rows.sort(key=lambda row: (row.dataset, row.frame_length))
    emit_table(rows)
    if args.csv_out is not None:
        write_csv(args.csv_out, rows)


if __name__ == "__main__":
    main()
