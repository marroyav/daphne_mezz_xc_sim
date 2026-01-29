# daphne_mezz_xc_sim

C++ simulation of the self-trigger matched filter in
`rtl/selftrig/eia_selftrig/st_xc.vhd` from the DAPHNE mezzanine project.

This model follows the transposed FIR structure and the pipeline registers used
in the RTL, including the two-cycle tap pipeline and the xcorr output pipeline.
It writes raw samples, xcorr output, and the trigger signal to both CSV and
separate text files.

## Build

```sh
make
```

Or:

```sh
g++ -O2 -std=c++17 -o st_xc_sim st_xc_sim.cpp
```

## Run (text input)

Input file: one integer per line (signed 14-bit by default). Lines starting with `#`
are ignored.

```sh
./st_xc_sim --input waveform.txt --out-prefix run1 --threshold 2000
```

If your input is unsigned 14-bit ADC counts (0..16383):

```sh
./st_xc_sim --input waveform.txt --out-prefix run1 --threshold 2000 --unsigned14 --unsigned14-no-center
```

## Run (binary 16-bit LE)

```sh
./st_xc_sim --input waveform.bin --input-bin16 --out-prefix run1 --threshold 2000
```

If binary is unsigned 14-bit ADC counts in 16-bit words:

```sh
./st_xc_sim --input waveform.bin --input-bin16 --out-prefix run1 --threshold 2000 --unsigned14 --unsigned14-no-center
```

## Outputs

Given `--out-prefix run1`:

- `run1.csv` (columns: `index,raw,xcorr,trigger`)
- `run1_raw.txt`
- `run1_xcorr.txt`
- `run1_trigger.txt`

## Plot

```sh
python3 plot_st_xc.py run1.csv
```

## Generate a SiPM-like sample waveform

This uses a noise file (uint16 LE with 14-bit samples) and injects a positive
SiPM-like pulse (peak 10-12 counts, decay 50-60 ticks) on top of a configurable
baseline (default 4000).

```sh
python3 make_sample.py \
  --noise /Users/marroyav/proto_fix/daphne-server/runs/run_2026-01-28/channel_16.dat \
  --out-bin sample_waveform.bin \
  --out-txt sample_waveform.txt \
  --baseline 4000 \
  --peak 12 \
  --tau-ticks 55
```

Then run the sim:

```sh
./st_xc_sim --input sample_waveform.bin --input-bin16 --unsigned14 --unsigned14-no-center \
  --out-prefix sample --threshold 2000
```

## Notes on RTL matching

- Uses the 32-tap template coefficients from `st_xc.vhd` unless overridden.
- Models the transposed FIR with a 2-cycle pipeline per tap, matching the
  zero-coefficient path and the DSP48E2 default pipeline latency.
- The trigger condition matches the RTL: `xcorr > threshold` for two cycles
  with the previous cycle at or below the threshold.

## Dependencies

- C++17 compiler (e.g., g++)
- Python 3 + matplotlib (for plotting only)
