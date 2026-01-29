#!/usr/bin/env python3
import argparse
import struct

import h5py
import numpy as np


def main():
    ap = argparse.ArgumentParser(description="Extract a channel waveform from structured DAPHNE HDF5.")
    ap.add_argument("--input", required=True, help="Path to structured .hdf5")
    ap.add_argument("--channel", type=int, required=True, help="Channel ID to extract")
    ap.add_argument("--out-bin", default="data/input/waveform_from_h5.bin", help="Output binary uint16 LE")
    ap.add_argument("--out-txt", default="data/input/waveform_from_h5.txt", help="Output text file")
    ap.add_argument("--max-records", type=int, default=0, help="Limit records (0 = all)")
    args = ap.parse_args()

    with h5py.File(args.input, "r") as f:
        chans = f["channels"][:]
        adcs = f["adcs"]
        idxs = np.where(chans == args.channel)[0]
        if idxs.size == 0:
            raise SystemExit(f"Channel {args.channel} not found")
        if args.max_records > 0:
            idxs = idxs[: args.max_records]

        # concatenate all selected records
        wave = []
        for i in idxs:
            wave.append(adcs[i])
        data = np.concatenate(wave).astype(np.uint16)

    # write binary
    with open(args.out_bin, "wb") as fb:
        for v in data:
            fb.write(struct.pack('<H', int(v)))

    # write text
    with open(args.out_txt, "w") as ft:
        for v in data:
            ft.write(f"{int(v)}\n")

    print(f"Channel {args.channel}: {len(idxs)} records, {data.size} samples")
    print(f"  {args.out_bin}")
    print(f"  {args.out_txt}")


if __name__ == "__main__":
    main()
