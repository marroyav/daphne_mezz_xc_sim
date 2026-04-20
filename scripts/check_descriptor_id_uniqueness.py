#!/usr/bin/env python3

import argparse
import sys

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check per-channel descriptor ID uniqueness in a single-channel XC CSV. "
            "The reconstructed ID is frame_start_index + desc_time_start."
        )
    )
    parser.add_argument("csv", help="Path to the XC analysis CSV")
    parser.add_argument(
        "--show",
        type=int,
        default=10,
        help="Maximum number of duplicate ID groups to print (default: 10)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    df = pd.read_csv(args.csv)

    starts = (
        df[df["frame_start"] == 1][["frame_id", "index"]]
        .drop_duplicates("frame_id")
        .rename(columns={"index": "frame_start_index"})
    )

    peaks = df[df["desc_valid"] == 1][
        [
            "index",
            "frame_id",
            "frame_index",
            "desc_time_start",
            "desc_peak",
            "desc_charge",
            "desc_peak_count",
            "desc_info_previous",
        ]
    ].copy()

    peaks = peaks.merge(starts, on="frame_id", how="left")
    if peaks["frame_start_index"].isna().any():
        missing = int(peaks["frame_start_index"].isna().sum())
        print(f"ERROR: {missing} peak rows are missing a frame_start index", file=sys.stderr)
        return 2

    peaks["abs_id"] = (peaks["frame_start_index"] + peaks["desc_time_start"]).astype(int)

    dup_counts = peaks.groupby("abs_id").size().reset_index(name="n")
    dup_counts = dup_counts[dup_counts["n"] > 1].sort_values(["n", "abs_id"], ascending=[False, True])

    print(f"csv={args.csv}")
    print(f"peaks={len(peaks)} duplicate_abs_ids={len(dup_counts)}")

    if dup_counts.empty:
        return 0

    for abs_id in dup_counts["abs_id"].head(args.show):
        print()
        print(f"abs_id={abs_id}")
        print(
            peaks[peaks["abs_id"] == abs_id][
                [
                    "index",
                    "frame_id",
                    "frame_index",
                    "frame_start_index",
                    "desc_time_start",
                    "desc_peak",
                    "desc_charge",
                    "desc_peak_count",
                    "desc_info_previous",
                ]
            ].to_string(index=False)
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
