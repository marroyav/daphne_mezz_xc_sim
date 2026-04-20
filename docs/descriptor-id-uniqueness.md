# Descriptor ID Uniqueness Replay

## Scope

This note documents the same-channel peak-descriptor ID collision that can
occur when the descriptor key is reconstructed as:

`frame_start_index + desc_time_start`

The intended downstream key is channel-scoped, for example:

`(geo_id, channel_id, frame_timestamp + sample_start)`

Cross-channel timestamp sharing is therefore not the issue. The bug is reuse of
`sample_start` inside one channel/frame.

## Root Cause

The CIEMAT descriptor path keeps two time-start registers:

- `time_start_reg_`: pending start sample for the next descriptor
- `time_start_reg2_`: committed start sample emitted with the current
  descriptor

The broken mirror logic was:

```cpp
if (ext_match) {
    time_start_reg_ = time_start_aux;
} else if (data_available) {
    time_start_reg2_ = time_start_reg_;
}
```

When a new trigger starts in the same cycle that the current descriptor becomes
available, the current descriptor loses priority and keeps the previous
`time_start_reg2_`.

The fixed logic matches the RTL correction:

```cpp
if (data_available) {
    time_start_reg2_ = time_start_reg_;
}
if (ext_match) {
    time_start_reg_ = time_start_aux;
}
```

## Replay Command

The `calib10_clean` replay used to validate the fix is:

```sh
cd /Users/marroyav/repo/daphne_mezz_xc_sim
make st_xc_sim
./st_xc_sim \
  --input data/input/calib10_clean.bin \
  --input-bin16 \
  --baseline-sub 4002 \
  --threshold 1 \
  --xcorr-negate \
  --out-prefix data/output/analysis/calib10_clean_neg_fixed
```

## Uniqueness Check

Run:

```sh
python3 scripts/check_descriptor_id_uniqueness.py \
  data/output/analysis/calib10_clean_neg_fixed.csv
```

Expected result after the fix:

- `duplicate_abs_ids=0`

The historical pre-fix replay file:

- `data/output/analysis/calib10_clean_neg.csv`

shows the original failure:

- `peaks=1646`
- `duplicate_abs_ids=19`

while the fixed replay:

- `data/output/analysis/calib10_clean_neg_fixed.csv`

gives:

- `peaks=1652`
- `duplicate_abs_ids=0`
