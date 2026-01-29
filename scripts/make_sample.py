#!/usr/bin/env python3
import argparse
import math
import struct


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a positive SiPM-like waveform from noise + pulse."
    )
    parser.add_argument("--noise", required=True, help="Noise .dat (uint16 LE with 14-bit samples)")
    parser.add_argument("--out-bin", default="data/input/sample_waveform.bin", help="Output binary (uint16 LE)")
    parser.add_argument("--out-txt", default="data/input/sample_waveform.txt", help="Output text (one sample per line)")
    parser.add_argument("--length", type=int, default=4096, help="Number of samples")
    parser.add_argument("--baseline", type=int, default=4000, help="Baseline offset (0..16383)")
    parser.add_argument("--pulse-index", type=int, default=2000, help="Sample index where pulse starts")
    parser.add_argument("--peak", type=int, default=12, help="Pulse peak amplitude over baseline (ADC counts)")
    parser.add_argument("--tau-ticks", type=float, default=55.0, help="Decay time constant in ticks")
    parser.add_argument("--pulse-length", type=int, default=200, help="Pulse length in ticks")
    parser.add_argument("--num-pulses", type=int, default=3, help="Number of pulses to inject")
    parser.add_argument("--pulse-spacing", type=int, default=500, help="Spacing between pulses in ticks")
    return parser.parse_args()


def clamp_u14(v):
    return 0 if v < 0 else 0x3FFF if v > 0x3FFF else v


def read_noise_u14(path, length):
    out = []
    with open(path, "rb") as f:
        for _ in range(length):
            b = f.read(2)
            if len(b) < 2:
                break
            u = struct.unpack("<H", b)[0] & 0x3FFF
            out.append(u)
    return out


def write_bin_u16(path, data):
    with open(path, "wb") as f:
        for v in data:
            f.write(struct.pack("<H", v & 0xFFFF))


def write_txt(path, data):
    with open(path, "w") as f:
        for v in data:
            f.write(f"{v}\n")


def sipm_pulse(length, peak, tau_ticks):
    # Simple exponential decay with a 1-tick rise
    return [int(round(peak * math.exp(-i / tau_ticks))) for i in range(length)]


def main():
    args = parse_args()

    noise = read_noise_u14(args.noise, args.length)
    if not noise:
        raise SystemExit("No samples read from noise file.")

    mean = sum(noise) / len(noise)
    shift = int(round(args.baseline - mean))
    wave = [clamp_u14(v + shift) for v in noise[: args.length]]

    pulse = sipm_pulse(args.pulse_length, args.peak, args.tau_ticks)
    for p in range(args.num_pulses):
        base = args.pulse_index + p * args.pulse_spacing
        for i, amp in enumerate(pulse):
            idx = base + i
            if 0 <= idx < len(wave):
                wave[idx] = clamp_u14(wave[idx] + amp)

    write_bin_u16(args.out_bin, wave)
    write_txt(args.out_txt, wave)

    print(f"Wrote {len(wave)} samples")
    print(f"  {args.out_bin}")
    print(f"  {args.out_txt}")
    print("Suggested sim usage:")
    print(
        "  ./st_xc_sim --input {bin} --input-bin16 --unsigned14 --unsigned14-no-center "
        "--out-prefix data/output/analysis/sample --threshold 2000".format(bin=args.out_bin)
    )


if __name__ == "__main__":
    main()
