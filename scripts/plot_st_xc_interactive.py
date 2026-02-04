#!/usr/bin/env python3
import csv
import os
import sys

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


def downsample(xs, ys, max_points):
    if max_points <= 0 or len(xs) <= max_points:
        return xs, ys
    stride = max(1, len(xs) // max_points)
    return xs[::stride], ys[::stride]


def load_window(csv_path, start_idx, end_idx, max_samples):
    xs, raw, raw_delayed = [], [], []
    xcorr, trig = [], []
    frame_start, frame_trigger = [], []
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
            raw.append(int(row["raw"]))
            if "raw_delayed" in row and row["raw_delayed"] != "":
                raw_delayed.append(int(row["raw_delayed"]))

            if "xcorr_proc" in row and row["xcorr_proc"] != "":
                xcorr.append(int(row["xcorr_proc"]))
            else:
                xcorr.append(int(row["xcorr"]))

            trig.append(int(row["trigger"]))
            if "frame_start" in row and row["frame_start"] != "":
                frame_start.append(int(row["frame_start"]))
            if "frame_trigger" in row and row["frame_trigger"] != "":
                frame_trigger.append(int(row["frame_trigger"]))

            if "desc_peak" in row and row["desc_peak"] != "":
                desc_peak.append(int(row["desc_peak"]))
            if "desc_charge" in row and row["desc_charge"] != "":
                desc_charge.append(int(row["desc_charge"]))
            if "desc_charge_simple" in row and row["desc_charge_simple"] != "":
                desc_charge_simple.append(int(row["desc_charge_simple"]))
            if "desc_time_over" in row and row["desc_time_over"] != "":
                desc_time_over.append(int(row["desc_time_over"]))
            if "desc_time_peak" in row and row["desc_time_peak"] != "":
                desc_time_peak.append(int(row["desc_time_peak"]))
            if "desc_time_start" in row and row["desc_time_start"] != "":
                desc_time_start.append(int(row["desc_time_start"]))
            if "desc_peak_current" in row and row["desc_peak_current"] != "":
                desc_peak_current.append(int(row["desc_peak_current"]))
            if "desc_slope_current" in row and row["desc_slope_current"] != "":
                desc_slope_current.append(int(row["desc_slope_current"]))
            if "desc_detection" in row and row["desc_detection"] != "":
                desc_detection.append(int(row["desc_detection"]))
            if "desc_sending" in row and row["desc_sending"] != "":
                desc_sending.append(int(row["desc_sending"]))
            if "desc_info_previous" in row and row["desc_info_previous"] != "":
                desc_info_previous.append(int(row["desc_info_previous"]))

            if max_samples > 0 and len(xs) >= max_samples:
                break

    return (xs, raw, raw_delayed, xcorr, trig, frame_start, frame_trigger,
            desc_peak, desc_charge, desc_charge_simple, desc_time_over, desc_time_peak, desc_time_start,
            desc_peak_current, desc_slope_current, desc_detection, desc_sending, desc_info_previous)


def plot(csv_path, max_points, max_samples, start_idx, end_idx, png_path=None):
    (xs, raw, raw_delayed, xcorr, trig, frame_start, frame_trigger,
     desc_peak, desc_charge, desc_charge_simple, desc_time_over, desc_time_peak, desc_time_start,
     desc_peak_current, desc_slope_current, desc_detection, desc_sending, desc_info_previous) = load_window(
        csv_path, start_idx, end_idx, max_samples
    )

    raw_ref = raw_delayed if raw_delayed else raw
    xcorr_scaled = scale_to_range(xcorr, min(raw_ref), max(raw_ref))
    trig_scaled = scale_binary(trig, min(raw_ref), max(raw_ref))
    frame_start_scaled = scale_binary(frame_start, min(raw_ref), max(raw_ref)) if frame_start else []
    frame_trigger_scaled = scale_binary(frame_trigger, min(raw_ref), max(raw_ref)) if frame_trigger else []
    desc_peak_current_scaled = scale_binary(desc_peak_current, min(raw_ref), max(raw_ref)) if desc_peak_current else []
    desc_detection_scaled = scale_binary(desc_detection, min(raw_ref), max(raw_ref)) if desc_detection else []
    desc_sending_scaled = scale_binary(desc_sending, min(raw_ref), max(raw_ref)) if desc_sending else []
    desc_info_previous_scaled = scale_binary(desc_info_previous, min(raw_ref), max(raw_ref)) if desc_info_previous else []

    xs_raw, raw_ds = downsample(xs, raw, max_points)
    xs_rd, raw_delayed_ds = downsample(xs, raw_delayed, max_points) if raw_delayed else ([], [])
    xs_xs, xcorr_scaled_ds = downsample(xs, xcorr_scaled, max_points)
    xs_xc, xcorr_ds = downsample(xs, xcorr, max_points)
    xs_tr, trig_ds = downsample(xs, trig_scaled, max_points)
    xs_fs, frame_start_ds = downsample(xs, frame_start_scaled, max_points) if frame_start_scaled else ([], [])
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
    if frame_start_ds:
        fig.add_trace(go.Scattergl(x=xs_fs, y=frame_start_ds, name="frame_start (scaled)", line=dict(width=1), visible="legendonly", legendgroup="triggers"))
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
    if "--png" in sys.argv:
        png_idx = sys.argv.index("--png")
        if png_idx + 1 >= len(sys.argv):
            print("Error: --png requires a path")
            sys.exit(1)
        png_path = sys.argv[png_idx + 1]
        del sys.argv[png_idx:png_idx + 2]

    if len(sys.argv) not in (2, 3, 4, 5, 6):
        print(f"Usage: {sys.argv[0]} <analysis.csv> [max_points] [max_samples] [start_idx] [end_idx] [--png <path>]")
        sys.exit(1)

    csv_path = sys.argv[1]
    max_points = int(sys.argv[2]) if len(sys.argv) >= 3 else 200000
    max_samples = int(sys.argv[3]) if len(sys.argv) >= 4 else 0
    start_idx = int(sys.argv[4]) if len(sys.argv) >= 5 else None
    end_idx = int(sys.argv[5]) if len(sys.argv) >= 6 else None

    plot(csv_path, max_points, max_samples, start_idx, end_idx, png_path)


if __name__ == "__main__":
    main()
