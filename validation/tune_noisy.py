"""Pick the noisy-tag rule on DEV records, then report TEST records once.

Dev/test split: records sorted numerically; dev = every other record, test = the rest.
Selection rule (fixed before looking at test): among configs whose dev false-positive
rate on clean data is <= 0.10, pick the one with the highest dev detection rate at a
+15 bpm artifact. Ties go to the earlier config in the grid.

Usage (from repo root):
    PYTHONPATH=src:validation python3 validation/tune_noisy.py --data-dir DIR --records ...
"""

import argparse
import json

import numpy as np

from validate_mitbih import heart_rate_per_minute, inject, run_case

FP_LIMIT = 0.10
GRID = [("mad", {"outlier_method": "mad"})] + [
    (f"rolling_w{w}_bpm{b}", {"outlier_method": "rolling", "rolling_bpm": float(b), "rolling_window": w})
    for w in [5, 11, 21]
    for b in [10, 15, 20, 25, 30, 40]
]


def evaluate(bases, kwargs, artifact_bpm, trials, seed=0):
    rng = np.random.default_rng(seed)
    fp, det = [], []
    for base in bases:
        fp.append("noisy" in run_case(base, "clean", **kwargs))
        for _ in range(trials):
            det.append("noisy" in run_case(inject(base, "noisy", rng, artifact_bpm), "noisy", **kwargs))
    return float(np.mean(fp)), float(np.mean(det))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--records", nargs="+", required=True)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--out", default="validation/tuning_results.json")
    args = parser.parse_args()

    records = sorted(args.records, key=int)
    dev_ids, test_ids = records[::2], records[1::2]
    bases = {r: heart_rate_per_minute(args.data_dir, r) for r in records}
    bases = {r: b for r, b in bases.items() if len(b) >= 10}
    dev = [bases[r] for r in dev_ids if r in bases]
    test = [bases[r] for r in test_ids if r in bases]

    dev_table = {}
    for name, kwargs in GRID:
        fp15, det15 = evaluate(dev, kwargs, 15.0, args.trials)
        dev_table[name] = {"dev_fp_clean": round(fp15, 3), "dev_detect_15bpm": round(det15, 3)}

    eligible = [(name, v) for name, v in dev_table.items() if v["dev_fp_clean"] <= FP_LIMIT]
    chosen = max(eligible, key=lambda kv: kv[1]["dev_detect_15bpm"])[0] if eligible else "mad"
    chosen_kwargs = dict(GRID)[chosen]
    baseline_kwargs = dict(GRID)["mad"]

    test_report = {}
    for label, kwargs in [("mad (baseline)", baseline_kwargs), (chosen, chosen_kwargs)]:
        row = {}
        for artifact in [100.0, 15.0]:
            fp, det = evaluate(test, kwargs, artifact, args.trials)
            row[f"detect_noisy_{int(artifact)}bpm"] = round(det, 3)
            row["fp_clean"] = round(fp, 3)
        test_report[label] = row

    out = {
        "dev_records": dev_ids, "test_records": test_ids,
        "fp_limit": FP_LIMIT, "selection": "max dev detection at +15 bpm subject to dev clean FP <= limit",
        "chosen": chosen, "chosen_kwargs": chosen_kwargs,
        "dev_grid": dev_table, "test_results": test_report,
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
