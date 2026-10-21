# Validation on real recordings

Data: **MIT-BIH Arrhythmia Database** (PhysioNet; Moody & Mark, 2001; Goldberger et al., 2000). ECG recordings from 47 subjects with expert beat annotations. Licensed under the Open Data Commons Attribution License v1.0. Downloaded annotation files for 29 of the 48 records (100–124, 200–210).

## Method

Each record's beat annotations become a heart-rate stream: median instantaneous HR per minute, about 30 minutes per record. The tagger then runs on that stream with a 30-minute window and a 60-second expected interval.

Faults are injected with known labels:

| Condition | Injection | Expected tag |
|---|---|---|
| clean | none | none (should be `reliable`) |
| stale | reference time moved 2 h past the last sample | `stale` |
| sparse | 70% of minutes dropped at random | `sparse` |
| noisy | 10% of minutes get a +artifact bpm offset | `noisy` |

20 random trials per record per fault, so 580 trials per fault type.

Run:

```bash
PYTHONPATH=src python3 validation/validate_mitbih.py --data-dir <dir with .hea/.atr files> --records <ids> --trials 20 --artifact-bpm 100
```

## Results

| Fault | Detection rate, +100 bpm artifact | Detection rate, +15 bpm artifact | False-positive rate on clean data |
|---|---|---|---|
| stale | 1.00 | 1.00 | 0.00 |
| sparse | 1.00 | 1.00 | 0.00 |
| noisy | 1.00 | 0.63 | 0.24 (7 of 29 records) |

Clean records tagged `noisy`: 101, 108, 121, 201, 202, 207, 209. Several of these are arrhythmia-heavy records in MIT-BIH.

Raw output: `results_artifact100.json`, `results_artifact15.json`.

## What this shows and doesn't

- **Stale and sparse detection work**, but these checks are close to true by construction. Dropping 70% of minutes or moving the clock will trip them. This confirms the code path, not the thresholds.
- **Noisy detection is the real test, and it is mixed.** Large artifacts (+100 bpm) are always caught. Subtle ones (+15 bpm) are caught 63% of the time.
- **The noisy tag false-positives on real physiology.** Ectopic beats and arrhythmia produce true heart-rate jumps. The robust MAD rule can't tell those from sensor noise. For a wellness product this matters: a real irregular rhythm would be labeled "low confidence," which is conservative but may be wrong about the sensor.
- **Not validated:** actual wearable sensor noise (motion artifacts, dropouts), clinical utility, or any threshold tuning. Thresholds were the defaults and were not tuned on this data.

## Suggested next step

Separate sensor artifacts from physiology before trusting the `noisy` tag. For example, flag only values that are physiologically impossible or that jump without a matching change in the other channels.

## Tuning attempt: rolling-median rule (dev/test split)

Goal: cut the noisy-tag false positives on real records without losing artifact detection.

Method: records sorted by ID, alternating into dev (14) and test (15) sets. On dev only, I searched a grid of rolling-median rules (window 5, 11, 21 samples; threshold 10–40 bpm) and picked the rule with the highest +15 bpm detection subject to dev clean false positives ≤ 10%. Then I scored the choice once on test. Script: `validation/tune_noisy.py`. Full output: `tuning_results.json`.

Selected on dev: rolling window 5, threshold 15 bpm.

| Rule | Test: detection, +100 bpm | Test: detection, +15 bpm | Test: false positives on clean |
|---|---|---|---|
| MAD (current default) | 1.00 | 0.68 | 0.29 |
| rolling, window 5, 15 bpm (selected on dev) | 0.99 | 0.46 | 0.29 |

**Result: no improvement.** The dev-selected rule matched the baseline false-positive rate on test and detected fewer subtle artifacts. The rolling rule trades one failure for another: thresholds that suppress arrhythmia false positives also miss small spikes, and the dev set is too small (14 records, so each record moves the rate by about 7 points) to pick a threshold that holds on new records. The default stays MAD. The `noisy` tag should be treated as unvalidated on real physiology.
