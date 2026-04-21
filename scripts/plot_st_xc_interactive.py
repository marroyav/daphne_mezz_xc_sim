#!/usr/bin/env python3
import csv
import os
import sys
from statistics import median

try:
    import plotly.graph_objects as go
except ImportError:
    print("plotly is required: pip install plotly")
    sys.exit(1)


def scale_to_range(values, target_min, target_max):
    vmin = min(values)
    vmax = max(values)
    if vmax == vmin:
        return [target_min for _ in values]
    scale = (target_max - target_min) / (vmax - vmin)
    return [target_min + (v - vmin) * scale for v in values]

def scale_binary(values, target_min, target_max):
    return [target_min if v == 0 else target_max for v in values]


def mean_std(values):
    if not values:
        return 0.0, 0.0
    m = sum(values) / len(values)
    if len(values) == 1:
        return m, 0.0
    var = sum((v - m) * (v - m) for v in values) / (len(values) - 1)
    return m, var ** 0.5


def compute_jitter_summary(xs, raw_ref, trig, split_adc=None, sample_period_ns=16.0):
    events = []
    for i, tv in enumerate(trig):
        if tv == 0:
            continue
        b0 = max(0, i - 64)
        b1 = max(b0 + 1, i - 8)
        base = median(raw_ref[b0:b1]) if b1 > b0 else raw_ref[i]

        s0 = max(0, i - 16)
        s1 = min(len(raw_ref), i + 97)
        peak_i = s0
        peak_a = -1
        for j in range(s0, s1):
            a = abs(raw_ref[j] - base)
            if a > peak_a:
                peak_a = a
                peak_i = j

        dt = xs[peak_i] - xs[i]
        events.append((peak_a, dt))

    if not events:
        return None

    amps = [a for a, _ in events]
    split = split_adc if split_adc is not None else median(amps)

    small = [dt for a, dt in events if a <= split]
    large = [dt for a, dt in events if a > split]
    ms, ss = mean_std(small)
    ml, sl = mean_std(large)

    def fmt_group(name, vals, m, s):
        return (
            f"{name}: n={len(vals)}, mean={m:.2f} samp ({m * sample_period_ns:.1f} ns), "
            f"sigma={s:.2f} samp ({s * sample_period_ns:.1f} ns)"
        )

    text = (
        f"Jitter summary (trigger -> |peak(raw_ref-baseline)|, split={split:.1f} ADC): "
        f"{fmt_group('small', small, ms, ss)} | {fmt_group('large', large, ml, sl)}"
    )
    return text


def downsample(xs, ys, max_points):
    if max_points <= 0 or len(xs) <= max_points:
        return xs, ys
    stride = max(1, len(xs) // max_points)
    return xs[::stride], ys[::stride]


def row_int(row, key, default=0):
    value = row.get(key, "")
    if value == "":
        return default
    return int(value)


def load_window(csv_path, start_idx, end_idx, max_samples):
    xs, raw, raw_delayed = [], [], []
    xcorr, trig = [], []
    frame_start, frame_active, frame_end, frame_trigger = [], [], [], []
    desc_peak, desc_charge, desc_charge_simple = [], [], []
    desc_time_over, desc_time_peak = [], []
    desc_time_start, desc_peak_current, desc_slope_current = [], [], []
    desc_detection, desc_sending, desc_info_previous = [], [], []

    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["index"])
            if start_idx is not None and idx < start_idx:
                continue
            if end_idx is not None and idx > end_idx:
                break

            xs.append(idx)
            raw_value = int(row["raw"])
            raw.append(raw_value)
            raw_delayed.append(row_int(row, "raw_delayed", raw_value))

            if "xcorr_proc" in row and row["xcorr_proc"] != "":
                xcorr.append(int(row["xcorr_proc"]))
            else:
                xcorr.append(int(row["xcorr"]))

            trig.append(row_int(row, "trigger", 0))
            frame_start.append(row_int(row, "frame_start", 0))
            if "frame_building" in row:
                frame_active.append(row_int(row, "frame_building", 0))
            else:
                frame_active.append(row_int(row, "frame_active", 0))
            frame_end.append(row_int(row, "frame_end", 0))
            frame_trigger.append(row_int(row, "frame_trigger", 0))

            desc_peak.append(row_int(row, "desc_peak", 0))
            desc_charge.append(row_int(row, "desc_charge", 0))
            desc_charge_simple.append(row_int(row, "desc_charge_simple", 0))
            desc_time_over.append(row_int(row, "desc_time_over", 0))
            desc_time_peak.append(row_int(row, "desc_time_peak", 0))
            desc_time_start.append(row_int(row, "desc_time_start", 0))
            desc_peak_current.append(row_int(row, "desc_peak_current", 0))
            desc_slope_current.append(row_int(row, "desc_slope_current", 0))
            desc_detection.append(row_int(row, "desc_detection", 0))
            desc_sending.append(row_int(row, "desc_sending", 0))
            desc_info_previous.append(row_int(row, "desc_info_previous", 0))

            if max_samples > 0 and len(xs) >= max_samples:
                break

    return (xs, raw, raw_delayed, xcorr, trig, frame_start, frame_active, frame_end, frame_trigger,
            desc_peak, desc_charge, desc_charge_simple, desc_time_over, desc_time_peak, desc_time_start,
            desc_peak_current, desc_slope_current, desc_detection, desc_sending, desc_info_previous)


def plot(csv_path, max_points, max_samples, start_idx, end_idx, png_path=None,
         jitter_footer=False, jitter_split=None):
    (xs, raw, raw_delayed, xcorr, trig, frame_start, frame_active, frame_end, frame_trigger,
     desc_peak, desc_charge, desc_charge_simple, desc_time_over, desc_time_peak, desc_time_start,
     desc_peak_current, desc_slope_current, desc_detection, desc_sending, desc_info_previous) = load_window(
        csv_path, start_idx, end_idx, max_samples
    )

    raw_ref = raw_delayed if any(raw_delayed) else raw
    xcorr_scaled = scale_to_range(xcorr, min(raw_ref), max(raw_ref))
    trig_scaled = scale_binary(trig, min(raw_ref), max(raw_ref))
    frame_start_scaled = scale_binary(frame_start, min(raw_ref), max(raw_ref)) if frame_start else []
    frame_active_scaled = scale_binary(frame_active, min(raw_ref), max(raw_ref)) if frame_active else []
    frame_end_scaled = scale_binary(frame_end, min(raw_ref), max(raw_ref)) if frame_end else []
    frame_trigger_scaled = scale_binary(frame_trigger, min(raw_ref), max(raw_ref)) if frame_trigger else []
    desc_peak_current_scaled = scale_binary(desc_peak_current, min(raw_ref), max(raw_ref)) if desc_peak_current else []
    desc_detection_scaled = scale_binary(desc_detection, min(raw_ref), max(raw_ref)) if desc_detection else []
    desc_sending_scaled = scale_binary(desc_sending, min(raw_ref), max(raw_ref)) if desc_sending else []
    desc_info_previous_scaled = scale_binary(desc_info_previous, min(raw_ref), max(raw_ref)) if desc_info_previous else []

    xs_raw, raw_ds = downsample(xs, raw, max_points)
    xs_rd, raw_delayed_ds = downsample(xs, raw_delayed, max_points) if any(raw_delayed) else ([], [])
    xs_xs, xcorr_scaled_ds = downsample(xs, xcorr_scaled, max_points)
    xs_xc, xcorr_ds = downsample(xs, xcorr, max_points)
    xs_tr, trig_ds = downsample(xs, trig_scaled, max_points)
    xs_fs, frame_start_ds = downsample(xs, frame_start_scaled, max_points) if frame_start_scaled else ([], [])
    xs_fa, frame_active_ds = downsample(xs, frame_active_scaled, max_points) if frame_active_scaled else ([], [])
    xs_fe, frame_end_ds = downsample(xs, frame_end_scaled, max_points) if frame_end_scaled else ([], [])
    xs_ft, frame_trigger_ds = downsample(xs, frame_trigger_scaled, max_points) if frame_trigger_scaled else ([], [])
    xs_dp, desc_peak_ds = downsample(xs, desc_peak, max_points) if desc_peak else ([], [])
    xs_dc, desc_charge_ds = downsample(xs, desc_charge, max_points) if desc_charge else ([], [])
    xs_dcs, desc_charge_simple_ds = downsample(xs, desc_charge_simple, max_points) if desc_charge_simple else ([], [])
    xs_dt, desc_time_over_ds = downsample(xs, desc_time_over, max_points) if desc_time_over else ([], [])
    xs_dtp, desc_time_peak_ds = downsample(xs, desc_time_peak, max_points) if desc_time_peak else ([], [])
    xs_dts, desc_time_start_ds = downsample(xs, desc_time_start, max_points) if desc_time_start else ([], [])
    xs_dpc, desc_peak_current_ds = downsample(xs, desc_peak_current_scaled, max_points) if desc_peak_current_scaled else ([], [])
    xs_dsc, desc_slope_current_ds = downsample(xs, desc_slope_current, max_points) if desc_slope_current else ([], [])
    xs_dd, desc_detection_ds = downsample(xs, desc_detection_scaled, max_points) if desc_detection_scaled else ([], [])
    xs_ds, desc_sending_ds = downsample(xs, desc_sending_scaled, max_points) if desc_sending_scaled else ([], [])
    xs_dip, desc_info_previous_ds = downsample(xs, desc_info_previous_scaled, max_points) if desc_info_previous_scaled else ([], [])

    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=xs_raw, y=raw_ds, name="raw", line=dict(width=1), visible="legendonly", legendgroup="signals", legendgrouptitle_text="Signals"))
    if raw_delayed_ds:
        fig.add_trace(go.Scattergl(x=xs_rd, y=raw_delayed_ds, name="raw_delayed", line=dict(width=1), legendgroup="signals"))
    else:
        fig.add_trace(go.Scattergl(x=xs_raw, y=raw_ds, name="raw", line=dict(width=1), legendgroup="signals"))
    fig.add_trace(go.Scattergl(x=xs_xs, y=xcorr_scaled_ds, name="xcorr_proc (scaled to raw)", line=dict(width=1), legendgroup="xcorr", legendgrouptitle_text="XCorr"))
    fig.add_trace(go.Scattergl(x=xs_xc, y=xcorr_ds, name="xcorr_proc", line=dict(width=1), visible="legendonly", legendgroup="xcorr"))
    fig.add_trace(go.Scattergl(x=xs_tr, y=trig_ds, name="trigger (scaled)", line=dict(width=1), visible="legendonly", legendgroup="triggers", legendgrouptitle_text="Triggers/Frames"))
    if frame_active_ds:
        fig.add_trace(go.Scattergl(x=xs_fa, y=frame_active_ds, name="frame_building (scaled)", line=dict(width=1), visible="legendonly", legendgroup="triggers"))
    if frame_start_ds:
        fig.add_trace(go.Scattergl(x=xs_fs, y=frame_start_ds, name="frame_start (scaled)", line=dict(width=1), legendgroup="triggers"))
    if frame_end_ds:
        fig.add_trace(go.Scattergl(x=xs_fe, y=frame_end_ds, name="frame_end (scaled)", line=dict(width=1), legendgroup="triggers"))
    if frame_trigger_ds:
        fig.add_trace(go.Scattergl(x=xs_ft, y=frame_trigger_ds, name="frame_trigger (scaled)", line=dict(width=1), visible="legendonly", legendgroup="triggers"))
    if desc_peak_ds:
        fig.add_trace(go.Scattergl(x=xs_dp, y=desc_peak_ds, name="peak_desc_peak", line=dict(width=1), visible="legendonly", legendgroup="desc_vhdl", legendgrouptitle_text="Peak descriptors (VHDL)"))
    if desc_charge_ds:
        fig.add_trace(go.Scattergl(x=xs_dc, y=desc_charge_ds, name="peak_desc_charge", line=dict(width=1), yaxis="y2", visible="legendonly", legendgroup="desc_vhdl"))
    if desc_charge_simple_ds:
        fig.add_trace(go.Scattergl(x=xs_dcs, y=desc_charge_simple_ds, name="peak_desc_charge_simple", line=dict(width=1), yaxis="y2", visible="legendonly", legendgroup="desc_simple", legendgrouptitle_text="Peak descriptors (simple)"))
    if desc_time_over_ds:
        fig.add_trace(go.Scattergl(x=xs_dt, y=desc_time_over_ds, name="peak_desc_time_over", line=dict(width=1), yaxis="y2", visible="legendonly", legendgroup="desc_vhdl"))
    if desc_time_peak_ds:
        fig.add_trace(go.Scattergl(x=xs_dtp, y=desc_time_peak_ds, name="peak_desc_time_peak", line=dict(width=1), yaxis="y2", visible="legendonly", legendgroup="desc_vhdl"))
    if desc_time_start_ds:
        fig.add_trace(go.Scattergl(x=xs_dts, y=desc_time_start_ds, name="peak_desc_time_start", line=dict(width=1), yaxis="y2", visible="legendonly", legendgroup="desc_vhdl"))
    if desc_peak_current_ds:
        fig.add_trace(go.Scattergl(x=xs_dpc, y=desc_peak_current_ds, name="peak_desc_peak_current (scaled)", line=dict(width=1), visible="legendonly", legendgroup="desc_vhdl"))
    if desc_slope_current_ds:
        fig.add_trace(go.Scattergl(x=xs_dsc, y=desc_slope_current_ds, name="peak_desc_slope_current", line=dict(width=1), yaxis="y2", visible="legendonly", legendgroup="desc_vhdl"))
    if desc_detection_ds:
        fig.add_trace(go.Scattergl(x=xs_dd, y=desc_detection_ds, name="peak_desc_detection (scaled)", line=dict(width=1), visible="legendonly", legendgroup="desc_vhdl"))
    if desc_sending_ds:
        fig.add_trace(go.Scattergl(x=xs_ds, y=desc_sending_ds, name="peak_desc_sending (scaled)", line=dict(width=1), visible="legendonly", legendgroup="desc_vhdl"))
    if desc_info_previous_ds:
        fig.add_trace(go.Scattergl(x=xs_dip, y=desc_info_previous_ds, name="peak_desc_info_previous (scaled)", line=dict(width=1), visible="legendonly", legendgroup="desc_vhdl"))

    fig.update_layout(
        title=None,
        xaxis=dict(title="sample index"),
        yaxis=dict(title="raw / xcorr (scaled)", side="left"),
        yaxis2=dict(title="trigger/metrics", overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, groupclick="toggleitem"),
        height=600,
    )

    if jitter_footer:
        jitter_text = compute_jitter_summary(xs, raw_ref, trig, jitter_split)
        if jitter_text:
            fig.add_annotation(
                text=jitter_text,
                xref="paper", yref="paper",
                x=0, y=-0.20,
                xanchor="left", yanchor="top",
                showarrow=False,
                align="left",
                font=dict(size=11),
            )
            fig.update_layout(margin=dict(b=145))
            print(jitter_text)
        else:
            print("Jitter summary: no trigger events in selected window.")

    base = os.path.splitext(os.path.basename(csv_path))[0]
    if "data/output/analysis" in csv_path:
        out_html = os.path.join("data", "output", "plots", base + ".html")
        os.makedirs(os.path.dirname(out_html), exist_ok=True)
    else:
        out_html = base + ".html"

    fig.write_html(out_html, include_plotlyjs="cdn")
    print(f"wrote {out_html}")
    if png_path:
        fig.write_image(png_path, scale=2)
        print(f"wrote {png_path}")


def main():
    png_path = None
    jitter_footer = False
    jitter_split = None
    if "--png" in sys.argv:
        png_idx = sys.argv.index("--png")
        if png_idx + 1 >= len(sys.argv):
            print("Error: --png requires a path")
            sys.exit(1)
        png_path = sys.argv[png_idx + 1]
        del sys.argv[png_idx:png_idx + 2]

    if "--jitter-footer" in sys.argv:
        jitter_footer = True
        sys.argv.remove("--jitter-footer")

    if "--jitter-split" in sys.argv:
        split_idx = sys.argv.index("--jitter-split")
        if split_idx + 1 >= len(sys.argv):
            print("Error: --jitter-split requires an ADC value")
            sys.exit(1)
        jitter_split = float(sys.argv[split_idx + 1])
        del sys.argv[split_idx:split_idx + 2]

    if len(sys.argv) not in (2, 3, 4, 5, 6):
        print(
            f"Usage: {sys.argv[0]} <analysis.csv> [max_points] [max_samples] [start_idx] [end_idx] "
            "[--jitter-footer] [--jitter-split <adc>] [--png <path>]"
        )
        sys.exit(1)

    csv_path = sys.argv[1]
    max_points = int(sys.argv[2]) if len(sys.argv) >= 3 else 200000
    max_samples = int(sys.argv[3]) if len(sys.argv) >= 4 else 0
    start_idx = int(sys.argv[4]) if len(sys.argv) >= 5 else None
    end_idx = int(sys.argv[5]) if len(sys.argv) >= 6 else None

    plot(csv_path, max_points, max_samples, start_idx, end_idx, png_path, jitter_footer, jitter_split)


if __name__ == "__main__":
    main()
