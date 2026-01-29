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


def downsample(xs, ys, max_points):
    if max_points <= 0 or len(xs) <= max_points:
        return xs, ys
    stride = max(1, len(xs) // max_points)
    return xs[::stride], ys[::stride]


def load_window(csv_path, start_idx, end_idx, max_samples):
    xs, raw, raw_delayed = [], [], []
    xcorr, trig = [], []
    frame_start, frame_trigger = [], []

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

            if max_samples > 0 and len(xs) >= max_samples:
                break

    return xs, raw, raw_delayed, xcorr, trig, frame_start, frame_trigger


def plot(csv_path, max_points, max_samples, start_idx, end_idx):
    xs, raw, raw_delayed, xcorr, trig, frame_start, frame_trigger = load_window(
        csv_path, start_idx, end_idx, max_samples
    )

    raw_ref = raw_delayed if raw_delayed else raw
    xcorr_scaled = scale_to_range(xcorr, min(raw_ref), max(raw_ref))

    xs_raw, raw_ds = downsample(xs, raw, max_points)
    xs_rd, raw_delayed_ds = downsample(xs, raw_delayed, max_points) if raw_delayed else ([], [])
    xs_xs, xcorr_scaled_ds = downsample(xs, xcorr_scaled, max_points)
    xs_xc, xcorr_ds = downsample(xs, xcorr, max_points)
    xs_tr, trig_ds = downsample(xs, trig, max_points)
    xs_fs, frame_start_ds = downsample(xs, frame_start, max_points) if frame_start else ([], [])
    xs_ft, frame_trigger_ds = downsample(xs, frame_trigger, max_points) if frame_trigger else ([], [])

    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=xs_raw, y=raw_ds, name="raw", line=dict(width=1), visible="legendonly"))
    if raw_delayed_ds:
        fig.add_trace(go.Scattergl(x=xs_rd, y=raw_delayed_ds, name="raw_delayed", line=dict(width=1)))
    else:
        fig.add_trace(go.Scattergl(x=xs_raw, y=raw_ds, name="raw", line=dict(width=1)))
    fig.add_trace(go.Scattergl(x=xs_xs, y=xcorr_scaled_ds, name="xcorr_proc (scaled to raw)", line=dict(width=1)))
    fig.add_trace(go.Scattergl(x=xs_xc, y=xcorr_ds, name="xcorr_proc", line=dict(width=1), visible="legendonly"))
    fig.add_trace(go.Scattergl(x=xs_tr, y=trig_ds, name="trigger", line=dict(width=1), yaxis="y2", visible="legendonly"))
    if frame_start_ds:
        fig.add_trace(go.Scattergl(x=xs_fs, y=frame_start_ds, name="frame_start", line=dict(width=1), yaxis="y2", visible="legendonly"))
    if frame_trigger_ds:
        fig.add_trace(go.Scattergl(x=xs_ft, y=frame_trigger_ds, name="frame_trigger", line=dict(width=1), yaxis="y2", visible="legendonly"))

    fig.update_layout(
        title="Self-trigger matched filter (interactive)",
        xaxis=dict(title="sample index"),
        yaxis=dict(title="raw / xcorr (scaled)", side="left"),
        yaxis2=dict(title="trigger", overlaying="y", side="right", range=[-0.1, 1.1]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
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


def main():
    if len(sys.argv) not in (2, 3, 4, 5, 6):
        print(f"Usage: {sys.argv[0]} <analysis.csv> [max_points] [max_samples] [start_idx] [end_idx]")
        sys.exit(1)

    csv_path = sys.argv[1]
    max_points = int(sys.argv[2]) if len(sys.argv) >= 3 else 200000
    max_samples = int(sys.argv[3]) if len(sys.argv) >= 4 else 0
    start_idx = int(sys.argv[4]) if len(sys.argv) >= 5 else None
    end_idx = int(sys.argv[5]) if len(sys.argv) >= 6 else None

    plot(csv_path, max_points, max_samples, start_idx, end_idx)


if __name__ == "__main__":
    main()
