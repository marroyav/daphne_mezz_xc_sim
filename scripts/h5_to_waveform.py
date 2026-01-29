#!/usr/bin/env python3
import argparse
import struct

import h5py
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract a single channel waveform from structured DAPHNE HDF5."
    )
    parser.add_argument("--input", required=True, help="Path to structured .hdf5")
    parser.add_argument("--channel", type=int, required=True, help="Channel ID to extract")
    parser.add_argument("--out-bin", default="data/input/waveform_from_h5.bin", help="Output binary uint16 LE")
    parser.add_argument("--out-txt", default="data/input/waveform_from_h5.txt", help="Output text file")
    parser.add_argument("--max-records", type=int, default=0, help="Limit records (0 = all)")
    return parser.parse_args()


def find_channel_indices(channels, channel_id, max_records):
    idxs = np.where(channels == channel_id)[0]
    if idxs.size == 0:
        raise SystemExit(f"Channel {channel_id} not found")
    if max_records > 0:
        idxs = idxs[: max_records]
    return idxs


def read_channel_waveform(h5_path, channel_id, max_records):
    with h5py.File(h5_path, "r") as f:
        channels = f["channels"][:]
        adcs = f["adcs"]
        idxs = find_channel_indices(channels, channel_id, max_records)
        records = [adcs[i] for i in idxs]
        waveform = np.concatenate(records).astype(np.uint16)
    return idxs.size, waveform


def write_bin_u16(path, data):
    with open(path, "wb") as f:
        for v in data:
            f.write(struct.pack("<H", int(v)))


def write_txt(path, data):
    with open(path, "w") as f:
        for v in data:
            f.write(f"{int(v)}\n")


def main():
    args = parse_args()
    record_count, waveform = read_channel_waveform(
        args.input, args.channel, args.max_records
    )

    write_bin_u16(args.out_bin, waveform)
    write_txt(args.out_txt, waveform)

    print(f"Channel {args.channel}: {record_count} records, {waveform.size} samples")
    print(f"  {args.out_bin}")
    print(f"  {args.out_txt}")


if __name__ == "__main__":
    main()
