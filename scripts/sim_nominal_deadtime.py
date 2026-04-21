#!/usr/bin/env python3
"""
Nominal self-trigger dead-time scan derived from the current DAPHNE RTL.

This is not a waveform-accurate HDL simulation. It is a stochastic queueing
model built from the constants and control rules in:

- daphne-firmware/rtl/isolated/subsystems/trigger/stc3_record_builder.vhd
- daphne-firmware/rtl/isolated/subsystems/readout/two_lane_readout_mux.vhd

Assumptions:

- homogeneous per-channel trigger arrivals
- one lane modeled explicitly; all 20 channels on that lane are statistically
  identical, so the per-channel numbers are the ones that matter
- arrival process is either:
  - Poisson per channel, or
  - an empirical renewal process built from inter-arrival spacings
- fixed per-accepted-trigger builder busy time
- fixed 232-word record size
- round-robin record drain with one-word-per-clock dump, one-cycle pause between
  records, and one-cycle-per-empty-channel scan approximation

The model separates:

- busy drops: trigger arrives while the channel builder is still assembling the
  previous frame
- full drops: trigger arrives when the per-channel FIFO has not drained enough
  to clear the RTL prog_full gate
"""

from __future__ import annotations

import argparse
import csv
import heapq
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


ARRIVAL = 2
RECORD_READY = 1
SERVICE_END = 0


@dataclass
class Service:
    channel: int
    start: float
    end: float


@dataclass
class LaneStats:
    arrivals: int = 0
    accepted: int = 0
    busy_drops: int = 0
    full_drops: int = 0
    sent: int = 0


@dataclass
class ArrivalConfig:
    mode: str
    interarrival_cycles: Optional[List[float]] = None
    scale_factor: float = 1.0
    source_mean_us: float = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Simulate nominal per-channel dead time from the DAPHNE self-trigger "
            "builder + round-robin drain model."
        )
    )
    parser.add_argument(
        "--rate-list",
        default="",
        help="Comma-separated per-channel trigger rates in Hz. Overrides start/stop/points.",
    )
    parser.add_argument(
        "--rate-start",
        type=float,
        default=1.0e3,
        help="Sweep start rate in Hz/channel (default: 1e3).",
    )
    parser.add_argument(
        "--rate-stop",
        type=float,
        default=2.0e4,
        help="Sweep stop rate in Hz/channel (default: 2e4).",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=12,
        help="Number of sweep points for a linear scan (default: 12).",
    )
    parser.add_argument(
        "--channels-per-lane",
        type=int,
        default=20,
        help="Channels sharing one round-robin lane (default: 20).",
    )
    parser.add_argument(
        "--clock-hz",
        type=float,
        default=62.5e6,
        help="Self-trigger clock frequency in Hz (default: 62.5e6).",
    )
    parser.add_argument(
        "--builder-busy-cycles",
        type=int,
        default=1037,
        help="Accepted-trigger builder busy length in cycles (default: 1037).",
    )
    parser.add_argument(
        "--record-words",
        type=int,
        default=232,
        help="Words emitted per accepted frame (default: 232).",
    )
    parser.add_argument(
        "--prog-full-thresh",
        type=int,
        default=200,
        help="RTL prog_full threshold in words (default: 200).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=1.0,
        help="Measurement time in seconds after warmup (default: 1.0).",
    )
    parser.add_argument(
        "--warmup",
        type=float,
        default=0.2,
        help="Warmup time in seconds before counting statistics (default: 0.2).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1,
        help="Base RNG seed (default: 1).",
    )
    parser.add_argument(
        "--arrival-mode",
        choices=["poisson", "empirical"],
        default="poisson",
        help="Per-channel arrival model (default: poisson).",
    )
    parser.add_argument(
        "--interarrival-file",
        default="",
        help="Path to empirical inter-arrival samples or timestamps.",
    )
    parser.add_argument(
        "--interarrival-column",
        default="",
        help="Optional CSV column name for inter-arrival samples or timestamps.",
    )
    parser.add_argument(
        "--interarrival-format",
        choices=["interarrival", "timestamp"],
        default="interarrival",
        help="Interpret empirical file as inter-arrival spacings or absolute timestamps.",
    )
    parser.add_argument(
        "--interarrival-unit",
        choices=["s", "ms", "us", "ns"],
        default="us",
        help="Unit of the empirical file values (default: us).",
    )
    parser.add_argument(
        "--csv-out",
        default="",
        help="Optional output CSV path.",
    )
    return parser.parse_args()


def sweep_rates(args: argparse.Namespace) -> List[float]:
    if args.rate_list.strip():
        return [float(item) for item in args.rate_list.split(",") if item.strip()]
    if args.points <= 1:
        return [args.rate_start]
    step = (args.rate_stop - args.rate_start) / float(args.points - 1)
    return [args.rate_start + idx * step for idx in range(args.points)]


def builder_only_accept_rate(rate_hz: float, busy_s: float) -> float:
    # Non-paralyzable dead-time approximation for the per-channel builder only.
    return rate_hz / (1.0 + rate_hz * busy_s)


def unit_scale(unit: str) -> float:
    return {
        "s": 1.0,
        "ms": 1.0e-3,
        "us": 1.0e-6,
        "ns": 1.0e-9,
    }[unit]


def load_numeric_series(path: str, column: str) -> List[float]:
    values: List[float] = []
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"inter-arrival file does not exist: {path}")

    with source.open("r", encoding="utf-8", newline="") as fin:
        if column:
            reader = csv.DictReader(fin)
            if reader.fieldnames is None or column not in reader.fieldnames:
                raise KeyError(f"column '{column}' not found in {path}")
            for row in reader:
                cell = row.get(column, "").strip()
                if not cell:
                    continue
                values.append(float(cell))
            return values

    with source.open("r", encoding="utf-8") as fin:
        for raw_line in fin:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            for token in line.replace(",", " ").split():
                try:
                    values.append(float(token))
                except ValueError:
                    continue
    return values


def build_arrival_config(args: argparse.Namespace, rate_hz_per_channel: float) -> ArrivalConfig:
    if args.arrival_mode == "poisson":
        return ArrivalConfig(mode="poisson")

    if not args.interarrival_file:
        raise ValueError("--interarrival-file is required when --arrival-mode empirical")

    values = load_numeric_series(args.interarrival_file, args.interarrival_column)
    if not values:
        raise ValueError("empirical inter-arrival source produced no numeric samples")

    values_s = [value * unit_scale(args.interarrival_unit) for value in values]
    if args.interarrival_format == "timestamp":
        if len(values_s) < 2:
            raise ValueError("timestamp mode requires at least two timestamp samples")
        values_s = [
            curr - prev
            for prev, curr in zip(values_s[:-1], values_s[1:])
            if curr > prev
        ]
        if not values_s:
            raise ValueError("timestamp mode produced no positive inter-arrival spacings")

    values_s = [value for value in values_s if value > 0.0]
    if not values_s:
        raise ValueError("empirical inter-arrival spacings must be strictly positive")

    source_mean_s = sum(values_s) / float(len(values_s))
    if rate_hz_per_channel <= 0.0:
        scaled_cycles: List[float] = []
        scale_factor = 1.0
    else:
        target_mean_s = 1.0 / rate_hz_per_channel
        scale_factor = target_mean_s / source_mean_s
        scaled_cycles = [value * scale_factor * args.clock_hz for value in values_s]

    return ArrivalConfig(
        mode="empirical",
        interarrival_cycles=scaled_cycles,
        scale_factor=scale_factor,
        source_mean_us=source_mean_s * 1.0e6,
    )


def simulate_lane(
    rate_hz_per_channel: float,
    *,
    channels_per_lane: int,
    clock_hz: float,
    builder_busy_cycles: int,
    record_words: int,
    prog_full_thresh: int,
    duration_s: float,
    warmup_s: float,
    seed: int,
    arrival_cfg: ArrivalConfig,
) -> Tuple[LaneStats, float]:
    total_cycles = (duration_s + warmup_s) * clock_hz
    warmup_cycles = warmup_s * clock_hz
    busy_cycles_f = float(builder_busy_cycles)
    full_release_cycles = max(0, record_words - (prog_full_thresh - 1))

    rng = random.Random(seed)
    stats = LaneStats()

    busy_until = [0.0 for _ in range(channels_per_lane)]
    complete_records = [0 for _ in range(channels_per_lane)]

    event_q: List[Tuple[float, int, int, int]] = []
    seq = 0

    def push_event(time_cyc: float, kind: int, channel: int) -> None:
        nonlocal seq
        heapq.heappush(event_q, (time_cyc, kind, seq, channel))
        seq += 1

    rate_per_cycle = rate_hz_per_channel / clock_hz if rate_hz_per_channel > 0.0 else 0.0

    def next_arrival_delta() -> Optional[float]:
        if arrival_cfg.mode == "poisson":
            if rate_per_cycle <= 0.0:
                return None
            return rng.expovariate(rate_per_cycle)
        if not arrival_cfg.interarrival_cycles:
            return None
        return rng.choice(arrival_cfg.interarrival_cycles)

    arrivals_enabled = (
        (arrival_cfg.mode == "poisson" and rate_per_cycle > 0.0)
        or (arrival_cfg.mode == "empirical" and bool(arrival_cfg.interarrival_cycles))
    )
    if arrivals_enabled:
        for ch in range(channels_per_lane):
            dt = next_arrival_delta()
            if dt is not None:
                push_event(dt, ARRIVAL, ch)

    rr_sel = 0
    current_service: Optional[Service] = None

    def prog_full(channel: int, now: float) -> bool:
        q = complete_records[channel]
        if q == 0:
            return False
        if q >= 2:
            return True
        if current_service is None:
            return True
        if current_service.channel != channel:
            return True
        if now < current_service.start + full_release_cycles:
            return True
        return False

    def maybe_schedule_service(now: float) -> None:
        nonlocal current_service, rr_sel
        if current_service is not None:
            return
        chosen: Optional[int] = None
        empty_steps = 0
        for offs in range(channels_per_lane):
            ch = (rr_sel + offs) % channels_per_lane
            if complete_records[ch] > 0:
                chosen = ch
                empty_steps = offs
                break
        if chosen is None:
            return
        start = now + empty_steps + 1.0
        end = start + float(record_words)
        current_service = Service(channel=chosen, start=start, end=end)
        push_event(end, SERVICE_END, chosen)

    maybe_schedule_service(0.0)

    while event_q:
        time_cyc, kind, _, channel = heapq.heappop(event_q)
        if time_cyc > total_cycles:
            break

        if kind == SERVICE_END:
            if current_service is None or current_service.channel != channel:
                continue
            complete_records[channel] -= 1
            if time_cyc >= warmup_cycles:
                stats.sent += 1
            current_service = None
            rr_sel = (channel + 1) % channels_per_lane
            maybe_schedule_service(time_cyc + 1.0)
            continue

        if kind == RECORD_READY:
            complete_records[channel] += 1
            maybe_schedule_service(time_cyc)
            continue

        if kind != ARRIVAL:
            continue

        next_dt = next_arrival_delta()
        if next_dt is not None:
            next_time = time_cyc + next_dt
            if next_time <= total_cycles:
                push_event(next_time, ARRIVAL, channel)

        if time_cyc >= warmup_cycles:
            stats.arrivals += 1

        if time_cyc < busy_until[channel]:
            if time_cyc >= warmup_cycles:
                stats.busy_drops += 1
            continue

        if prog_full(channel, time_cyc):
            if time_cyc >= warmup_cycles:
                stats.full_drops += 1
            continue

        busy_until[channel] = time_cyc + busy_cycles_f
        push_event(busy_until[channel], RECORD_READY, channel)
        if time_cyc >= warmup_cycles:
            stats.accepted += 1

    return stats, full_release_cycles / clock_hz


def main() -> int:
    args = parse_args()
    rates = sweep_rates(args)

    busy_s = args.builder_busy_cycles / args.clock_hz
    mux_capacity_per_lane_hz = args.clock_hz / float(args.record_words + 1)
    mux_capacity_per_channel_hz = mux_capacity_per_lane_hz / float(args.channels_per_lane)

    rows = []
    for idx, rate in enumerate(rates):
        arrival_cfg = build_arrival_config(args, rate)
        stats, full_release_s = simulate_lane(
            rate,
            channels_per_lane=args.channels_per_lane,
            clock_hz=args.clock_hz,
            builder_busy_cycles=args.builder_busy_cycles,
            record_words=args.record_words,
            prog_full_thresh=args.prog_full_thresh,
            duration_s=args.duration,
            warmup_s=args.warmup,
            seed=args.seed + idx,
            arrival_cfg=arrival_cfg,
        )

        arrivals = max(stats.arrivals, 1)
        accepted_frac = stats.accepted / arrivals
        busy_frac = stats.busy_drops / arrivals
        full_frac = stats.full_drops / arrivals
        dead_frac = 1.0 - accepted_frac
        accepted_rate = rate * accepted_frac

        rows.append(
            {
                "rate_hz_per_channel": rate,
                "accepted_hz_per_channel": accepted_rate,
                "dead_fraction": dead_frac,
                "busy_drop_fraction": busy_frac,
                "full_drop_fraction": full_frac,
                "builder_only_accept_hz": builder_only_accept_rate(rate, busy_s),
                "builder_busy_us": busy_s * 1.0e6,
                "full_release_us": full_release_s * 1.0e6,
                "mux_capacity_hz_per_channel": mux_capacity_per_channel_hz,
                "arrival_model": args.arrival_mode,
                "arrival_scale_factor": arrival_cfg.scale_factor,
                "arrival_source_mean_us": arrival_cfg.source_mean_us,
            }
        )

    header = (
        "rate_hz/ch accepted_hz/ch dead_frac busy_frac full_frac "
        "builder_only_hz/ch builder_busy_us mux_cap_hz/ch"
    )
    print(header)
    for row in rows:
        print(
            f"{row['rate_hz_per_channel']:12.3f} "
            f"{row['accepted_hz_per_channel']:14.3f} "
            f"{row['dead_fraction']:9.5f} "
            f"{row['busy_drop_fraction']:9.5f} "
            f"{row['full_drop_fraction']:9.5f} "
            f"{row['builder_only_accept_hz']:18.3f} "
            f"{row['builder_busy_us']:15.6f} "
            f"{row['mux_capacity_hz_per_channel']:15.3f}"
        )

    if args.csv_out:
        with open(args.csv_out, "w", newline="", encoding="utf-8") as fout:
            writer = csv.DictWriter(
                fout,
                fieldnames=list(rows[0].keys()) if rows else [],
            )
            writer.writeheader()
            writer.writerows(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
