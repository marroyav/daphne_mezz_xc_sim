# daphne_mezz_xc_sim

C++ simulation of the self-trigger matched filter in
`rtl/selftrig/eia_selftrig/st_xc.vhd` from the DAPHNE mezzanine project.

This model follows the transposed FIR structure and the pipeline registers used
in the RTL, including the two-cycle tap pipeline and the xcorr output pipeline.
It writes raw samples, xcorr output, trigger, and frame markers to CSV and
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

## Outputs

Given `--out-prefix data/output/analysis/run1`:

- `run1.csv` columns:
  `index,raw,raw_delayed,xcorr,xcorr_proc,trigger,frame_start,frame_active,frame_index,frame_id,frame_trigger`
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
Other traces (xcorr_proc, trigger, frame_start, frame_trigger) are available in the legend.
When present, the plot uses `raw_delayed` (data alignment delay, default 256 samples) as the
reference for scaling `xcorr_proc` and displays it by default.

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

## Notes on RTL matching

- Uses the 32-tap template coefficients from `st_xc.vhd` unless overridden.
- Models the transposed FIR with a 2-cycle pipeline per tap, matching the
  zero-coefficient path and the DSP48E2 default pipeline latency.
- The trigger condition matches the RTL: `xcorr > threshold` for two cycles
  with the previous cycle at or below the threshold.
- The data path can be aligned with `--data-delay` (default 256 samples) to
  match the `stc3.vhd` delay chain.

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

**Not modeled**
- Ethernet packetization, FIFO depth, dense-packing format, multi-channel arbitration.

## Dependencies

- C++17 compiler
- Python 3 + plotly (for interactive plots)
