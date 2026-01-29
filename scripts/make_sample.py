#!/usr/bin/env python3
import argparse
import struct


def clamp_u14(v: int) -> int:
    if v < 0:
        return 0
    if v > 0x3FFF:
        return 0x3FFF
    return v


def read_noise_u14(path: str, length: int) -> list[int]:
    data = []
    with open(path, "rb") as f:
        for _ in range(length):
            b = f.read(2)
            if len(b) < 2:
                break
            u = struct.unpack('<H', b)[0] & 0x3FFF
            data.append(u)
    return data


def write_bin_u16(path: str, data: list[int]):
    with open(path, "wb") as f:
        for v in data:
            f.write(struct.pack('<H', v & 0xFFFF))


def write_txt(path: str, data: list[int]):
    with open(path, "w") as f:
        for v in data:
            f.write(f"{v}\n")


def sipm_pulse(length: int, peak: int, tau_ticks: float) -> list[int]:
    # simple exponential decay with a 1-tick rise
    y = [0] * length
    y[0] = peak
    for i in range(1, length):
        y[i] = int(round(peak * (2.718281828 ** (-i / tau_ticks))))
    return y


def main():
    ap = argparse.ArgumentParser(description="Generate a positive SiPM-like waveform from noise + pulse.")
    ap.add_argument("--noise", required=True, help="Path to noise .dat (uint16 LE with 14-bit samples).")
    ap.add_argument("--out-bin", default="data/input/sample_waveform.bin", help="Output binary file (uint16 LE).")
    ap.add_argument("--out-txt", default="data/input/sample_waveform.txt", help="Output text file (one sample per line).")
    ap.add_argument("--length", type=int, default=4096, help="Number of samples to emit.")
    ap.add_argument("--baseline", type=int, default=4000, help="Baseline offset (0..16383).")
    ap.add_argument("--pulse-index", type=int, default=2000, help="Sample index where pulse starts.")
    ap.add_argument("--peak", type=int, default=12, help="Pulse peak amplitude over baseline (ADC counts).")
    ap.add_argument("--tau-ticks", type=float, default=55.0, help="Decay time constant in ticks.")
    ap.add_argument("--pulse-length", type=int, default=200, help="Pulse length in ticks.")
    ap.add_argument("--num-pulses", type=int, default=3, help="Number of pulses to inject.")
    ap.add_argument("--pulse-spacing", type=int, default=500, help="Spacing between pulses in ticks.")
    args = ap.parse_args()

    noise = read_noise_u14(args.noise, args.length)
    if not noise:
        raise SystemExit("No samples read from noise file.")

    # recentre noise around baseline
    # compute mean of noise and shift to target baseline
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
    print(f"  ./st_xc_sim --input {args.out_bin} --input-bin16 --unsigned14 --unsigned14-no-center --out-prefix sample --threshold 2000")


if __name__ == "__main__":
    main()
