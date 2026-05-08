#!/usr/bin/env python3
import argparse
import csv
import math
import re
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory


RESULT_RE = re.compile(r"(\w+)=([0-9]+)")


def parse_args():
    repo_root = Path(__file__).resolve().parents[1]
    default_fw = repo_root.parent / "daphne-firmware"
    parser = argparse.ArgumentParser(
        description="Run the HDL multichannel dead-time bench over a trigger-rate sweep."
    )
    parser.add_argument("--rate-list", default="", help="Comma-separated rates in Hz/channel.")
    parser.add_argument("--rate-start", type=int, default=1000)
    parser.add_argument("--rate-stop", type=int, default=20000)
    parser.add_argument("--points", type=int, default=8)
    parser.add_argument("--warmup-cycles", type=int, default=20000)
    parser.add_argument("--measure-cycles", type=int, default=200000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--jobs", type=int, default=1, help="Parallel HDL jobs after the single shared build step.")
    parser.add_argument("--seed-start", type=int, default=101)
    parser.add_argument("--seed-step", type=int, default=1000)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse rows already present in the raw CSV and run only missing tasks.",
    )
    parser.add_argument("--csv-out", default="")
    parser.add_argument("--raw-csv-out", default="")
    parser.add_argument(
        "--firmware-root",
        default=str(default_fw),
        help="Path to the daphne-firmware tree to compile against.",
    )
    parser.add_argument(
        "--builder-variant",
        choices=["auto", "baseline", "ring", "lane"],
        default="auto",
        help="Select the dead-time bench wrapper to match the builder RTL interface.",
    )
    parser.add_argument(
        "--signal-delay-steps",
        type=int,
        default=0,
        help="Ring-builder overlap control in 16-sample steps. Ignored for baseline.",
    )
    parser.add_argument(
        "--frame-extend-hold-cycles",
        type=int,
        default=0,
        help="Hold frame_extend_i high for this many cycles after each trigger in the ring wrapper bench.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse an already elaborated multichannel_deadtime_tb executable.",
    )
    parser.add_argument("--channel-count", type=int, default=40)
    parser.add_argument("--producer-count", type=int, default=5)
    parser.add_argument("--channels-per-producer", type=int, default=8)
    return parser.parse_args()


def sweep_rates(args):
    if args.rate_list.strip():
        return [int(item) for item in args.rate_list.split(",") if item.strip()]
    if args.points <= 1:
        return [args.rate_start]
    step = (args.rate_stop - args.rate_start) / float(args.points - 1)
    return [int(round(args.rate_start + idx * step)) for idx in range(args.points)]


def detect_builder_variant(repo_root: Path, firmware_root: str, requested_variant: str):
    if requested_variant != "auto":
        return requested_variant

    root = Path(firmware_root) if firmware_root else (repo_root / ".." / "daphne-firmware")
    lane_wired_path = (root / "rtl/isolated/subsystems/trigger/afe_selftrigger_island.vhd").resolve()
    if lane_wired_path.exists():
        lane_text = lane_wired_path.read_text(encoding="utf-8")
        if "afe_stc3_stream_serializer" in lane_text and "stc3_frame_source" in lane_text:
            return "lane"

    lane_serializer_path = (root / "rtl/isolated/subsystems/trigger/afe_stc3_stream_serializer.vhd").resolve()
    if lane_serializer_path.exists() and not (root / "rtl/isolated/subsystems/trigger/stc3_record_builder.vhd").exists():
        return "lane"
    builder_path = (root / "rtl/isolated/subsystems/trigger/stc3_record_builder.vhd").resolve()
    text = builder_path.read_text(encoding="utf-8")
    return "ring" if "timestamp_i" in text else "baseline"


def ensure_built(repo_root: Path, firmware_root: str, builder_variant: str):
    cmd = ["make", "deadtime_tb"]
    if firmware_root:
        cmd.append(f"DAPHNE_FIRMWARE_ROOT={firmware_root}")
    if builder_variant == "ring":
        cmd.append("DEADTIME_TB_SRC=hdl/multichannel_deadtime_tb_ring.vhd")
    elif builder_variant == "lane":
        cmd.append("DEADTIME_TB_SRC=hdl/multichannel_deadtime_tb_lane.vhd")
    subprocess.run(cmd, cwd=repo_root, check=True)


def bench_executable(repo_root: Path) -> Path:
    bench = repo_root / "multichannel_deadtime_tb"
    if not bench.exists():
        raise FileNotFoundError(f"expected elaborated bench executable at {bench}")
    return bench


def run_one(
    repo_root: Path,
    rate: int,
    warmup_cycles: int,
    measure_cycles: int,
    seed_base: int,
    signal_delay_steps: int,
    frame_extend_hold_cycles: int,
    builder_variant: str,
    channel_count: int,
    producer_count: int,
    channels_per_producer: int,
):
    bench = bench_executable(repo_root)
    cmd = [
        str(bench),
        f"-gTRIGGER_RATE_HZ_G={rate}",
        f"-gWARMUP_CYCLES_G={warmup_cycles}",
        f"-gMEASURE_CYCLES_G={measure_cycles}",
        f"-gSEED_BASE_G={seed_base}",
    ]
    if signal_delay_steps:
        cmd.append(f"-gSIGNAL_DELAY_STEPS_G={signal_delay_steps}")
    if frame_extend_hold_cycles:
        cmd.append(f"-gFRAME_EXTEND_HOLD_CYCLES_G={frame_extend_hold_cycles}")
    if builder_variant == "lane":
        cmd.extend(
            [
                f"-gCHANNEL_COUNT_G={channel_count}",
                f"-gPRODUCER_COUNT_G={producer_count}",
                f"-gCHANNELS_PER_PRODUCER_G={channels_per_producer}",
            ]
        )
    with TemporaryDirectory(prefix="daphne-deadtime-tb-") as run_dir:
        proc = subprocess.run(cmd, cwd=run_dir, check=True, capture_output=True, text=True)
    result_line = None
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            result_line = line
            break
    if result_line is None:
        raise RuntimeError(f"bench output did not contain a RESULT line for rate {rate}")
    row = {key: int(value) for key, value in RESULT_RE.findall(result_line)}
    row["dead_fraction"] = row["dead_ppm"] / 1_000_000.0
    return row


def mean(values):
    return sum(values) / float(len(values))


def stddev(values):
    if len(values) <= 1:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((value - mu) ** 2 for value in values) / float(len(values) - 1))


def summarise(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["rate_hz_per_channel"]].append(row)

    summary_rows = []
    for rate in sorted(grouped):
        samples = grouped[rate]
        dead_values = [sample["dead_fraction"] for sample in samples]
        accepted_values = [sample["accepted_total"] for sample in samples]
        sent_values = [sample["sent_total"] for sample in samples]
        busy_values = [sample["busy_counter_total"] for sample in samples]
        full_values = [sample["full_counter_total"] for sample in samples]
        spacing_values = [sample["spacing_counter_total"] for sample in samples] if "spacing_counter_total" in samples[0] else []
        queue_values = [sample["queue_counter_total"] for sample in samples] if "queue_counter_total" in samples[0] else []
        ring_values = [sample["ring_counter_total"] for sample in samples] if "ring_counter_total" in samples[0] else []
        output_values = [sample["output_counter_total"] for sample in samples] if "output_counter_total" in samples[0] else []

        row = {
            "rate_hz_per_channel": rate,
            "channels": samples[0].get("channels", 0),
            "producers": samples[0].get("producers", 0),
            "channels_per_producer": samples[0].get("channels_per_producer", 0),
            "repeats": len(samples),
            "dead_fraction_mean": mean(dead_values),
            "dead_fraction_std": stddev(dead_values),
            "accepted_total_mean": mean(accepted_values),
            "accepted_total_std": stddev(accepted_values),
            "sent_total_mean": mean(sent_values),
            "sent_total_std": stddev(sent_values),
            "busy_counter_total_mean": mean(busy_values),
            "busy_counter_total_std": stddev(busy_values),
            "full_counter_total_mean": mean(full_values),
            "full_counter_total_std": stddev(full_values),
        }
        if spacing_values:
            row["spacing_counter_total_mean"] = mean(spacing_values)
            row["spacing_counter_total_std"] = stddev(spacing_values)
            row["queue_counter_total_mean"] = mean(queue_values)
            row["queue_counter_total_std"] = stddev(queue_values)
            row["ring_counter_total_mean"] = mean(ring_values)
            row["ring_counter_total_std"] = stddev(ring_values)
            row["output_counter_total_mean"] = mean(output_values)
            row["output_counter_total_std"] = stddev(output_values)

        summary_rows.append(row)
    return summary_rows


def load_existing_raw_rows(path: Path):
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)
        rows = []
        for row in reader:
            parsed = {}
            for key, value in row.items():
                if value is None or value == "":
                    continue
                if key == "dead_fraction":
                    parsed[key] = float(value)
                else:
                    parsed[key] = int(float(value))
            rows.append(parsed)
        return rows


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    builder_variant = detect_builder_variant(repo_root, args.firmware_root, args.builder_variant)
    if args.signal_delay_steps < 0 or args.signal_delay_steps > 31:
        raise ValueError("--signal-delay-steps must be in [0, 31]")
    if args.frame_extend_hold_cycles < 0:
        raise ValueError("--frame-extend-hold-cycles must be non-negative")
    if args.channel_count <= 0:
        raise ValueError("--channel-count must be positive")
    if args.producer_count <= 0:
        raise ValueError("--producer-count must be positive")
    if args.channels_per_producer <= 0:
        raise ValueError("--channels-per-producer must be positive")
    if builder_variant == "baseline" and args.signal_delay_steps != 0:
        raise ValueError("--signal-delay-steps only applies to the ring builder variant")
    if builder_variant == "baseline" and args.frame_extend_hold_cycles != 0:
        raise ValueError("--frame-extend-hold-cycles only applies to the ring builder variant")
    if builder_variant == "lane" and args.frame_extend_hold_cycles != 0:
        raise ValueError("--frame-extend-hold-cycles does not apply to the lane-serializer variant")
    if builder_variant == "lane" and args.channel_count != args.producer_count * args.channels_per_producer:
        raise ValueError("--channel-count must equal --producer-count * --channels-per-producer for the lane-serializer variant")
    if builder_variant != "lane" and (
        args.channel_count != 40 or args.producer_count != 5 or args.channels_per_producer != 8
    ):
        raise ValueError("grouped producer arguments only apply to the lane-serializer variant")
    if not args.skip_build:
        ensure_built(repo_root, args.firmware_root, builder_variant)
    print(
        "USING "
        f"builder_variant={builder_variant} "
        f"signal_delay_steps={args.signal_delay_steps} "
        f"frame_extend_hold_cycles={args.frame_extend_hold_cycles} "
        f"channel_count={args.channel_count} "
        f"producer_count={args.producer_count} "
        f"channels_per_producer={args.channels_per_producer}"
    )

    raw_rows = []
    if args.resume and args.raw_csv_out:
        raw_rows = load_existing_raw_rows(Path(args.raw_csv_out))

    existing_keys = {
        (row["rate_hz_per_channel"], row["repeat_index"])
        for row in raw_rows
        if "rate_hz_per_channel" in row and "repeat_index" in row
    }

    tasks = []
    for rate in sweep_rates(args):
        for repeat_idx in range(args.repeats):
            if (rate, repeat_idx) in existing_keys:
                continue
            seed_base = args.seed_start + repeat_idx * args.seed_step + rate
            tasks.append((rate, repeat_idx, seed_base))

    if raw_rows:
        print(f"REUSED {len(raw_rows)} existing raw rows from {args.raw_csv_out}")

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {
            pool.submit(
                run_one,
                repo_root,
                rate,
                args.warmup_cycles,
                args.measure_cycles,
                seed_base,
                args.signal_delay_steps,
                args.frame_extend_hold_cycles,
                builder_variant,
                args.channel_count,
                args.producer_count,
                args.channels_per_producer,
            ): (rate, repeat_idx, seed_base)
            for rate, repeat_idx, seed_base in tasks
        }
        completed = 0
        total = len(futures)
        for future in as_completed(futures):
            rate, repeat_idx, seed_base = futures[future]
            row = future.result()
            row["repeat_index"] = repeat_idx
            row["seed_base"] = seed_base
            raw_rows.append(row)
            completed += 1
            print(
                "DONE "
                f"{completed}/{total} "
                f"rate_hz_per_channel={rate} "
                f"repeat_index={repeat_idx} "
                f"dead_fraction={row['dead_fraction']:.6f} "
                f"accepted_total={row['accepted_total']} "
                f"sent_total={row['sent_total']}"
            )

    raw_rows.sort(key=lambda row: (row["rate_hz_per_channel"], row["repeat_index"]))

    rows = summarise(raw_rows)

    print("rate_hz/ch dead_frac_mean dead_frac_std accepted_mean sent_mean")
    for row in rows:
        print(
            f"{row['rate_hz_per_channel']:10d} "
            f"{row['dead_fraction_mean']:14.6f} "
            f"{row['dead_fraction_std']:13.6f} "
            f"{row['accepted_total_mean']:13.3f} "
            f"{row['sent_total_mean']:10.3f}"
        )

    if args.csv_out:
        with open(args.csv_out, "w", newline="", encoding="utf-8") as fout:
            writer = csv.DictWriter(fout, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    if args.raw_csv_out:
        with open(args.raw_csv_out, "w", newline="", encoding="utf-8") as fout:
            writer = csv.DictWriter(fout, fieldnames=list(raw_rows[0].keys()))
            writer.writeheader()
            writer.writerows(raw_rows)


if __name__ == "__main__":
    main()
