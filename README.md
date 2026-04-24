# daphne_mezz_xc_sim

C++ emulation of the self-trigger matched filter in
`rtl/selftrig/eia_selftrig/st_xc.vhd` from the DAPHNE mezzanine project.

This model follows the transposed FIR structure and the pipeline registers used
in the RTL, including the two-cycle tap pipeline and the xcorr output pipeline.
It writes raw samples, xcorr output, trigger, frame markers, and peak descriptor
signals to CSV and
separate text files.

## Build

```sh
make
```

The build uses `src/st_xc_sim.cpp`.

## Run (text input)

Input file: one integer per line (signed 14-bit by default). Lines starting with `#`
are ignored.

```sh
./st_xc_sim --input waveform.txt --out-prefix data/output/analysis/run1 --threshold 2000
```

If your input is unsigned 14-bit ADC counts (0..16383):

```sh
./st_xc_sim --input waveform.txt --out-prefix data/output/analysis/run1 --threshold 2000 --unsigned14 --unsigned14-no-center
```

## Run (binary 16-bit LE)

```sh
./st_xc_sim --input waveform.bin --input-bin16 --out-prefix data/output/analysis/run1 --threshold 2000
```

If binary is unsigned 14-bit ADC counts in 16-bit words:

```sh
./st_xc_sim --input waveform.bin --input-bin16 --out-prefix data/output/analysis/run1 --threshold 2000 --unsigned14 --unsigned14-no-center \
  --auto-baseline --xcorr-negate --holdoff 1024
```

`--auto-baseline` is a convenience mode that subtracts one constant mean value
computed over the whole input file. It is not the firmware baseline algorithm.

To emulate the firmware `k_low_pass_filter` baseline tracker, use the dedicated
LPF mode instead. With unsigned raw ADC words, keep the waveform uncentered so
the emulator matches the RTL baseline initialization at mid-scale (`8192`):

```sh
./st_xc_sim --input waveform.bin --input-bin16 --unsigned14 --unsigned14-no-center \
  --fw-baseline-lpf --xcorr-input-negate --threshold 5000 \
  --out-prefix data/output/analysis/run1_lpf
```

To approximate the full firmware trigger path (`trig_xc` + `Configurable_CFD`),
enable the CFD gate and (optionally) input-sign inversion used around
`hpf_out_xcorr`:

```sh
./st_xc_sim --input waveform.bin --input-bin16 --unsigned14 --unsigned14-no-center \
  --fw-baseline-lpf \
  --threshold 5000 --fw-cfd --fw-cfd-delay 26 --fw-cfd-sign 0 \
  --xcorr-input-negate \
  --out-prefix data/output/analysis/run1_fw
```

If your firmware uses `invert_enable='1'`, drop `--xcorr-input-negate`.

To force absolute-value correlation for positive-only triggering:

```sh
./st_xc_sim --input waveform.bin --input-bin16 --out-prefix data/output/analysis/run1 --threshold 2000 --xcorr-abs
```

To emulate the CIEMAT peak-descriptor path with positive pulses, invert the
signal before the descriptor logic:

```sh
./st_xc_sim --input waveform.bin --input-bin16 --unsigned14 --unsigned14-no-center \
  --fw-baseline-lpf \
  --xcorr-abs --threshold 2000 --data-delay 265 --ciemat-invert \
  --out-prefix data/output/analysis/run1
```

## Outputs

Given `--out-prefix data/output/analysis/run1`:

- `run1.csv` columns:
  `index,raw,raw_delayed,baseline_lpf,xcorr_input,xcorr,xcorr_proc,trigger,frame_start,frame_active,frame_building,frame_end,frame_index,frame_id,frame_trigger,`
  `desc_valid,desc_time_peak,desc_time_over,desc_peak,desc_charge,desc_charge_simple,desc_peak_count,`
  `desc_time_start,desc_peak_current,desc_slope_current,desc_detection,desc_sending,desc_info_previous`
- `run1_raw.txt`
- `run1_xcorr.txt`
- `run1_trigger.txt`

## Interactive Plot

```sh
python3 scripts/plot_st_xc_interactive.py data/output/analysis/run1.csv 200000 100000
```

This generates an HTML plot in `data/output/plots/` with:
- raw
- xcorr_proc scaled to raw range
Other traces (xcorr_proc, trigger, frame_start, frame_trigger, peak descriptor values including time-of-peak and charge variants) are available in the legend.
When present, the plot uses `raw_delayed` (data alignment delay, default 256 samples) as the
reference for scaling `xcorr_proc` and displays it by default.

To export a PNG alongside the HTML:

```sh
python3 scripts/plot_st_xc_interactive.py data/output/analysis/run1.csv 200000 100000 --png data/output/plots/run1.png
```

## Generate a SiPM-like sample waveform

This uses a noise file (uint16 LE with 14-bit samples) and injects a positive
SiPM-like pulse (peak 10-12 counts, decay 50-60 ticks) on top of a configurable
baseline (default 4000).

```sh
python3 scripts/make_sample.py \
  --noise /Users/marroyav/proto_fix/daphne-server/runs/run_2026-01-28/channel_16.dat \
  --out-bin data/input/sample_waveform.bin \
  --out-txt data/input/sample_waveform.txt \
  --baseline 4000 \
  --peak 12 \
  --tau-ticks 55 \
  --num-pulses 3 \
  --pulse-spacing 500
```

Then run the sim:

```sh
./st_xc_sim --input data/input/sample_waveform.bin --input-bin16 --unsigned14 --unsigned14-no-center \
  --out-prefix data/output/analysis/sample --threshold 2000
```

## Notes on RTL matching / emulation

- Uses the 32-tap template coefficients from `st_xc.vhd` unless overridden.
- Models the transposed FIR with a 2-cycle pipeline per tap, matching the
  zero-coefficient path and the DSP48E2 default pipeline latency.
- The trigger condition matches the RTL: `xcorr > threshold` for two cycles
  with the previous cycle at or below the threshold (default mode).
- Optional firmware baseline LPF mode is available with `--fw-baseline-lpf`.
  It implements the RTL `k_low_pass_filter` recurrence rather than a fixed
  whole-file mean subtraction.
- Optional firmware-like CFD stage is available with `--fw-cfd` (default
  delay 26, sign mode 0) to emulate `Configurable_CFD` gating in `trig_xc`.
- The data path can be aligned with `--data-delay`. The VHDL delay is
  `256 + 9 = 265` samples (see `stc3.vhd`), so use `--data-delay 265` to match
  the default gateware alignment.
- The delay knobs are exact sample counts in the emulator, so `--data-delay 265`
  means a 265-sample output delay and `--ciemat-delay N` means an `N`-sample
  descriptor-input delay.
- CIEMAT descriptor emulation uses `--ciemat-config` (default `0x36CD`) and
  `--ciemat-delay` (default `176`) to match the VHDL pipeline staging.
- The descriptor path now consumes the same filtered sample domain exported in
  `xcorr_input`, rather than the raw ADC sample, so descriptor behavior tracks
  the trigger/filter preprocessing more closely.

## Simulation vs VHDL (mapping)

**1) Matched filter / cross-correlation**
- **VHDL:** `rtl/selftrig/eia_selftrig/st_xc.vhd`
- **C++:** `src/st_xc_sim.cpp` (`XCorrSim::UpdateFIR()` + `UpdateXCorrPipeline()`)
- **Notes:** 32-tap template, transposed FIR, 2-cycle tap pipeline mirrored.

**2) Trigger condition**
- **VHDL:** `st_xc.vhd` trigger logic
- **C++:** `XCorrSim::ShouldTrigger()`
- **Logic:** fires when `xcorr > threshold` for two cycles and the previous cycle is `<= threshold`.

**3) Frame assembly**
- **VHDL:** `stc3.vhd` frame FSM
- **C++:** `XCorrSim::UpdateFrame()`
- **Behavior:** frame starts only on trigger, length 1024 samples, trigger at `frame_index = 64`, no overlapping frames.

**4) Data delay alignment**
- **VHDL:** `stc3.vhd` delay chain
- **C++:** `raw_delayed` using `--data-delay` (default 256)
- **Purpose:** aligns data with trigger/pretrigger latency.

**5) Peak descriptors (CIEMAT)**
- **VHDL:** `rtl/selftrig/ciemat_selftrig/PeakDetector_SelfTrigger_CIEMAT.vhd`,
  `rtl/selftrig/ciemat_selftrig/LocalPrimitives_CIEMAT.vhd`,
  `rtl/selftrig/ciemat_selftrig/Self_Trigger_Primitive_Calculation.vhd`
- **C++:** `CiematPeakDetector`, `CiematLocalPrimitives`, `CiematSim` in
  `src/st_xc_sim.cpp` + `desc_*` columns
- **Notes:** `desc_charge` follows the VHDL integration. `desc_charge_simple`
  is the previous positive-amplitude sum for comparison.

**Not modeled**
- Ethernet packetization, FIFO depth, dense-packing format, multi-channel arbitration.

## Nominal dead-time scan versus trigger rate

The waveform emulator above does not model the shared multi-channel drain path.
For a nominal rate scan derived from the current RTL builder + round-robin
readout rules, use:

```sh
python3 scripts/sim_nominal_deadtime.py \
  --rate-start 1000 \
  --rate-stop 20000 \
  --points 12
```

This script uses the current gateware constants:

- builder busy time from `stc3_record_builder.vhd`
- record size from the same builder FSM
- round-robin service from `two_lane_readout_mux.vhd`
- homogeneous trigger arrivals across the 20 channels sharing one output lane

The output table reports:

- accepted trigger rate per channel
- total dead-time fraction
- split between builder-busy drops and FIFO-full drops

It is still a stochastic queueing model, not a waveform-accurate HDL testbench,
but it is the right level for a nominal dead-time-versus-rate study.

## C++ stochastic ring model

For the current ring-buffer builder, there is now a separate stochastic C++
model that mirrors the HDL-side acceptance gates:

- spacing reject
- queue-full reject
- ring-safe reject
- output-full reject

Build it with:

```sh
make ring_deadtime_sim
```

Run a sweep aligned with the HDL bench defaults:

```sh
./ring_deadtime_sim \
  --rate-start 1000 \
  --rate-stop 14000 \
  --points 20 \
  --repeats 3 \
  --warmup-cycles 20000 \
  --measure-cycles 200000 \
  --signal-delay-steps 0 \
  --csv-out data/output/analysis/deadtime_ring_cpp_summary.csv \
  --raw-csv-out data/output/analysis/deadtime_ring_cpp_raw.csv
```

For `50%` overlap on the current `512`-sample frame:

```sh
./ring_deadtime_sim \
  --rate-start 1000 \
  --rate-stop 14000 \
  --points 20 \
  --repeats 3 \
  --warmup-cycles 20000 \
  --measure-cycles 200000 \
  --signal-delay-steps 16 \
  --csv-out data/output/analysis/deadtime_ring_cpp50_summary.csv \
  --raw-csv-out data/output/analysis/deadtime_ring_cpp50_raw.csv
```

The summary CSV is intentionally shaped like the HDL summary CSV from
`scripts/run_multichannel_deadtime_tb.py`, including:

- `dead_fraction_mean/std`
- `accepted_total_mean/std`
- `sent_total_mean/std`
- `busy_counter_total_mean/std`
- `full_counter_total_mean/std`
- `spacing_counter_total_mean/std`
- `queue_counter_total_mean/std`
- `ring_counter_total_mean/std`
- `output_counter_total_mean/std`

So you can compare the stochastic model directly against HDL outputs with the
existing comparison scripts.

Example, compare the C++ ring model against an HDL ring sweep:

```sh
python3 scripts/plot_deadtime_branch_compare.py \
  --baseline-csv data/output/analysis/deadtime_ring_cpp_summary.csv \
  --ring-csv data/output/analysis/deadtime_hdl_ring_summary.csv \
  --baseline-label "cpp model" \
  --ring-label "hdl bench" \
  --out-prefix data/output/plots/deadtime_cpp_vs_hdl_ring
```

## Four-way architecture comparison

To compare:

- `1024` waveform
- `512` waveform
- `512 + ring0`
- `512 + ring50`

across the full rate spectrum with one command:

```sh
python3 scripts/run_deadtime_fourway_compare.py
```

By default this generates a dense sweep from `200 Hz/ch` to `20 kHz/ch` and
writes:

- `data/output/analysis/deadtime_arch_1024_cpp.csv`
- `data/output/analysis/deadtime_arch_512_cpp.csv`
- `data/output/analysis/deadtime_arch_512_ring0_cpp.csv`
- `data/output/analysis/deadtime_arch_512_ring50_cpp.csv`
- `data/output/plots/deadtime_arch_fourway_cpp.png`
- `data/output/plots/deadtime_arch_fourway_cpp.pdf`

The deep study note for that comparison is:

- [`docs/fourway-deadtime-study.md`](docs/fourway-deadtime-study.md)

You can override the scan density and window with:

```sh
python3 scripts/run_deadtime_fourway_compare.py \
  --rate-start 200 \
  --rate-stop 20000 \
  --points 120 \
  --repeats 4
```

Important limitation:

- this C++ model is event-driven and intentionally coarser than the HDL bench
- it models serializer completion at record granularity, not per-word FIFO write
  timing inside the serializer
- use it to sweep quickly and identify dominant reject causes, not as a
  replacement for the HDL bench

## Dead-time optimization study

For the current non-overlap optimization argument, the repo now includes:

- a coalesced non-overlap architecture probe
- a transport-scaling comparison (`2 x 20` channels vs `4 x 10`)
- operating-point figures for the downstream-contract discussion

Run the full stochastic study bundle with:

```sh
python3 scripts/run_deadtime_optimization_study.py
```

This renders:

- the four-way architecture plot
- the ring versus coalesced comparison
- the throughput/saturation view
- the transport-scaling plot
- compact presentation figures

Useful standalone entry points:

```sh
python3 scripts/plot_deadtime_coalesced_compare.py
python3 scripts/plot_deadtime_throughput_compare.py
python3 scripts/plot_deadtime_transport_compare.py
python3 scripts/plot_deadtime_argument_figures.py
```

The deep report note for the current optimization direction is:

- [`docs/deadtime-optimization-study.md`](docs/deadtime-optimization-study.md)

### Bursty arrival studies from empirical event spacings

The default nominal scan assumes Poisson arrivals. That is useful as a baseline,
 but it is not the right model for shower-like or track-clustered activity.

The same script can instead drive each channel with an empirical renewal
process built from inter-arrival spacings, for example from CORSIKA-derived
event spacings:

```sh
python3 scripts/sim_nominal_deadtime.py \
  --arrival-mode empirical \
  --interarrival-file data/corsika_interarrival_us.txt \
  --interarrival-unit us \
  --rate-start 1000 \
  --rate-stop 14000 \
  --points 20 \
  --csv-out data/output/analysis/deadtime_empirical.csv
```

Notes:

- the empirical spacing file may contain either:
  - one inter-arrival sample per line, or
  - CSV data with a selected column via `--interarrival-column`
- if you already have absolute event timestamps instead of spacings, use:
  - `--interarrival-format timestamp`
- the script rescales the empirical spacing distribution to the target nominal
  rate for each scan point, preserving burst structure while changing the mean
  rate

Current limitation:

- this empirical mode keeps channels statistically identical and independent
  except for sharing the same spacing distribution
- it does **not** yet model cross-channel correlation from a single shower
  lighting up many channels at the same time

So this mode answers:

- "what happens if each channel has the same nominal rate, but arrivals are
  bursty instead of Poisson?"

It does not yet answer:

- "what happens if one physical shower produces correlated trigger bursts across
  many channels at once?"

## Dependencies

- C++17 compiler
- Python 3 + plotly (for interactive plots)
- `ghdl` for the HDL multichannel dead-time bench

## HDL multichannel dead-time bench

The C++ emulator models the trigger/filter path, but it still does not model
the shared lane drain in RTL. For a real HDL bench around the current
`stc3_record_builder` plus `two_lane_readout_mux`, build:

```sh
make deadtime_tb
```

Run one rate point:

```sh
ghdl -r --std=08 multichannel_deadtime_tb -gTRIGGER_RATE_HZ_G=5000
```

Run a sweep:

```sh
python3 scripts/run_multichannel_deadtime_tb.py \
  --rate-start 1000 \
  --rate-stop 20000 \
  --points 8 \
  --repeats 3 \
  --jobs 4 \
  --csv-out data/output/analysis/deadtime_hdl_summary.csv \
  --raw-csv-out data/output/analysis/deadtime_hdl_raw.csv
```

The runner builds the bench once, then fans out the rate points in parallel
with isolated temporary run directories. Use `--jobs` to control concurrency.
For publication-style comparisons, keep `--repeats` above `1` so the summary
CSV contains a mean dead-time point and a run-to-run spread.

The defaults are chosen for a more stable comparison than a smoke test:

- `--warmup-cycles 20000`
- `--measure-cycles 200000`
- `--repeats 3`

For a denser scan, increase the rate points and keep the HDL bench parallelized
through `--jobs`.

The bench uses:

- the real `stc3_record_builder.vhd`
- the real `two_lane_readout_mux.vhd`
- a bench-local `sync_fifo_fwft` simulation model so GHDL can run the design
  without XPM libraries

To compare alternate firmware trees against the same bench, point the runner at
another checkout:

```sh
python3 scripts/run_multichannel_deadtime_tb.py \
  --firmware-root ../daphne-firmware-bram \
  --rate-list 1000,3000,5000,7000,9000,11000,13000 \
  --repeats 3 \
  --jobs 4 \
  --csv-out data/output/analysis/deadtime_hdl_ring_summary.csv \
  --raw-csv-out data/output/analysis/deadtime_hdl_ring_raw.csv
```

The runner auto-detects whether the builder RTL uses the baseline or ring
interface and selects the matching testbench wrapper. For apples-to-apples
dead-time comparison against the previous study, keep the ring branch at zero
overlap unless you explicitly want to study the overlap policy itself.

To study overlap on the ring builder, pass `--signal-delay-steps`. The current
RTL interprets this as `16` samples per step, so `--signal-delay-steps 16`
corresponds to `256` samples of overlap, i.e. `50%` overlap for a `512`-sample
frame.

It prints a `RESULT ...` line containing:

- total generated triggers
- total accepted records
- total sent records
- total busy/full diagnostic counters
- dead fraction in ppm

## Compare two HDL branches

When you have two HDL summary CSVs from `scripts/run_multichannel_deadtime_tb.py`,
you can compare them directly with:

```sh
python3 scripts/plot_deadtime_branch_compare.py \
  --baseline-csv data/output/analysis/deadtime_hdl_baseline_40pt.csv \
  --ring-csv data/output/analysis/deadtime_hdl_ring_40pt.csv \
  --out-prefix data/output/plots/deadtime_branch_compare_40pt \
  --csv-out data/output/analysis/deadtime_branch_compare_40pt.csv
```

The script produces:

- a main comparison figure with total dead time and busy/full components
- a delta figure with `ring - baseline` differences in percentage points

If the two sweeps do not use the same rate grid, the script aligns them on the
union of both grids and interpolates each branch within its covered range.

## Three-way comparison: baseline, ring0, ring50

For the ring-builder study, the most useful combined view is baseline versus
ring with zero overlap versus ring with `50%` overlap. Generate it with:

```sh
python3 scripts/plot_deadtime_threeway_compare.py \
  --baseline-csv data/output/analysis/deadtime_hdl_fixed_20pt.csv \
  --ring0-csv data/output/analysis/deadtime_hdl_ring_20pt.csv \
  --ring50-csv data/output/analysis/deadtime_hdl_ring50_20pt.csv \
  --out-prefix data/output/plots/deadtime_threeway_compare_20pt \
  --csv-out data/output/analysis/deadtime_threeway_compare_20pt.csv
```

This produces:

- `data/output/plots/deadtime_threeway_compare_20pt.png`
- `data/output/plots/deadtime_threeway_compare_20pt.pdf`
- `data/output/analysis/deadtime_threeway_compare_20pt.csv`

The full study note is in:

- [`docs/ring-deadtime-study.md`](docs/ring-deadtime-study.md)

## Publication plot: stochastic model versus HDL bench

Generate the dense nominal-model curve:

```sh
python3 scripts/sim_nominal_deadtime.py \
  --rate-start 1000 \
  --rate-stop 14000 \
  --points 100 \
  --csv-out data/output/analysis/deadtime_nominal.csv
```

Generate the HDL comparison points:

```sh
python3 scripts/run_multichannel_deadtime_tb.py \
  --rate-list 1000,3000,5000,7000,9000,11000,13000 \
  --repeats 3 \
  --jobs 4 \
  --csv-out data/output/analysis/deadtime_hdl_summary.csv \
  --raw-csv-out data/output/analysis/deadtime_hdl_raw.csv
```

Render the comparison figure:

```sh
python3 scripts/plot_deadtime_vs_rate.py \
  --nominal-csv data/output/analysis/deadtime_nominal.csv \
  --hdl-csv data/output/analysis/deadtime_hdl_summary.csv \
  --out-prefix data/output/plots/deadtime_vs_rate_daphne
```

This produces:

- `data/output/plots/deadtime_vs_rate_daphne.png`
- `data/output/plots/deadtime_vs_rate_daphne.pdf`

The figure overlays:

- a dense stochastic queueing-model curve
- HDL multichannel bench points with mean ± `1σ`
- the nominal fair-share lane ceiling marker
