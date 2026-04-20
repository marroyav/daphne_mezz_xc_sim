# Frame-Length Capture And Dead-Time Study

## Scope

This note documents the XC-side study used to answer two questions for the
current DAPHNE self-trigger path:

1. For a given frame length, how often is a pulse cut by the captured waveform
   window?
2. For a given frame length, how often is a pulse missed entirely because the
   channel is dead while another frame is active?

The study is intentionally waveform-oriented. Peak descriptors may be dropped
without counting as a lost pulse if the underlying pulse interval is still fully
contained in the recorded frame.

## RTL-Aligned XC Configuration

`st_xc_sim` now exposes `--rtl-current`, which applies the current firmware-side
trigger and descriptor defaults:

- firmware LPF baseline enabled
- xcorr input negation enabled
- no absolute-value xcorr path
- no post-xcorr sign negation
- CFD enabled with delay `26` and sign `0`
- data delay `265`
- CIEMAT config `0x36CD`
- CIEMAT delay `176`
- CIEMAT descriptor sign left non-inverted
- pretrigger `64`

This matches the current trigger/descriptor chain much more closely than the
older ad hoc replay modes.

## Native Window-Length Method

The capture study is native, not post hoc. The emulator is rerun with several
frame lengths:

- `320`
- `512`
- `1024`
- `2048`
- `4096` as a long-window reference

The CIEMAT descriptor send window now follows:

`frame_len - pretrigger`

instead of a hardcoded `960` samples, so short-window runs are physically
meaningful.

To support long-window references, the CSV now includes:

- `desc_time_start_full`

which is the unwrapped descriptor start sample within the active frame.

## Pulse Definition

Reference pulses are taken from the long-window run (`4096` samples). Each
`desc_valid=1` row defines one pulse interval:

- pulse start:
  `frame_start_sample - pretrigger + desc_time_start_full`
- pulse end:
  `pulse_start + desc_time_over`

Each target frame defines a captured waveform window:

- frame start:
  `frame_start_sample - pretrigger`
- frame end:
  `frame_start + frame_len - 1`

Each reference pulse is classified against the target frame set as:

- `captured`:
  the full pulse interval lies inside some captured frame
- `cut`:
  the pulse overlaps a captured frame, but part of the interval lies outside
  the window
- `deadtime_lost`:
  the pulse does not overlap any captured frame

## Scripts

Relevant scripts:

- `scripts/compare_descriptor_runs.py`
- `scripts/study_frame_capture_loss.py`
- `scripts/plot_frame_capture_loss.py`

## Reproduction Commands

Build:

```sh
cd /Users/marroyav/repo/daphne_mezz_xc_sim
make st_xc_sim
```

Generate native RTL-like runs:

```sh
./st_xc_sim \
  --input data/input/run039344_ch35.bin \
  --input-bin16 \
  --unsigned14 \
  --unsigned14-no-center \
  --rtl-current \
  --threshold 2000 \
  --frame-len 320 \
  --out-prefix data/output/analysis/run039344_ch35_rtl_thr2k_len320

./st_xc_sim \
  --input data/input/run039344_ch35.bin \
  --input-bin16 \
  --unsigned14 \
  --unsigned14-no-center \
  --rtl-current \
  --threshold 2000 \
  --frame-len 512 \
  --out-prefix data/output/analysis/run039344_ch35_rtl_thr2k_len512

./st_xc_sim \
  --input data/input/run039344_ch35.bin \
  --input-bin16 \
  --unsigned14 \
  --unsigned14-no-center \
  --rtl-current \
  --threshold 2000 \
  --frame-len 1024 \
  --out-prefix data/output/analysis/run039344_ch35_rtl_thr2k_len1024

./st_xc_sim \
  --input data/input/run039344_ch35.bin \
  --input-bin16 \
  --unsigned14 \
  --unsigned14-no-center \
  --rtl-current \
  --threshold 2000 \
  --frame-len 2048 \
  --out-prefix data/output/analysis/run039344_ch35_rtl_thr2k_len2048

./st_xc_sim \
  --input data/input/run039344_ch35.bin \
  --input-bin16 \
  --unsigned14 \
  --unsigned14-no-center \
  --rtl-current \
  --threshold 2000 \
  --frame-len 4096 \
  --out-prefix data/output/analysis/run039344_ch35_rtl_thr2k_len4096
```

Run the pulse capture study:

```sh
python3 scripts/study_frame_capture_loss.py \
  --reference-csv data/output/analysis/run039344_ch35_rtl_thr2k_len4096.csv \
  --reference-label 4096 \
  --target 320=data/output/analysis/run039344_ch35_rtl_thr2k_len320.csv \
  --target 512=data/output/analysis/run039344_ch35_rtl_thr2k_len512.csv \
  --target 1024=data/output/analysis/run039344_ch35_rtl_thr2k_len1024.csv \
  --target 2048=data/output/analysis/run039344_ch35_rtl_thr2k_len2048.csv \
  --pretrigger 64 \
  --csv-out data/output/analysis/run039344_ch35_rtl_thr2k_capture_loss_vs_len.csv
```

Render the summary plot:

```sh
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/mpl-daphne-capture-loss \
python3 scripts/plot_frame_capture_loss.py \
  data/output/analysis/run039344_ch35_rtl_thr2k_capture_loss_vs_len.csv \
  --out-prefix data/output/plots/run039344_ch35_rtl_thr2k_capture_loss_vs_len
```

## Current Result: `run039344_ch35.bin`, Threshold `2000`

Reference pulses from the `4096`-sample run:

- `389`

Measured loss summary:

| frame length | captured | cut by frame window | lost to dead time |
| --- | ---: | ---: | ---: |
| `320` | `389 / 389` = `100.00%` | `0 / 389` = `0.00%` | `0 / 389` = `0.00%` |
| `512` | `384 / 389` = `98.71%` | `0 / 389` = `0.00%` | `5 / 389` = `1.29%` |
| `1024` | `388 / 389` = `99.74%` | `0 / 389` = `0.00%` | `1 / 389` = `0.26%` |
| `2048` | `388 / 389` = `99.74%` | `0 / 389` = `0.00%` | `1 / 389` = `0.26%` |

The important interpretation is:

- on this waveform, shortening the frame did not cut any pulse interval
- the loss channel is dead time, not waveform truncation
- `2048` was not a sufficient reference; the `4096` run exposed one additional
  pulse beyond the `2048` window

## Caveat

These numbers are specific to:

- one channel (`run039344_ch35`)
- one threshold (`2000`)
- one waveform class

They should be treated as one operating-point study, not yet as a universal
frame-length law for DAPHNE.
