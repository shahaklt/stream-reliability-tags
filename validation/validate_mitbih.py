"""Validate stream-reliability-tags on real recordings with injected, known faults.

Data: MIT-BIH Arrhythmia Database (PhysioNet, ODC Attribution License v1.0).
Each record's beat annotations are turned into a 1-minute heart-rate stream
(median instantaneous HR per minute). Faults are injected with known labels:

  clean  -> expected tag: reliable (none of the fault tags)
  stale  -> the reference time is moved 2 hours past the last sample
  sparse -> 70% of minutes are dropped at random
  noisy  -> 10% of minutes get a +artifact_bpm artifact (default +100 bpm)

Metric: detection rate (fault injected, expected tag present) and false-positive
rate (clean data, tag present).

Usage:
    python validation/validate_mitbih.py --data-dir DIR --records 100 101 103
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import wfdb

from stream_tags.core import tag_streams

BEAT_SYMBOLS = set("NLRBAaJSVrFejnE/fQ?")
START = pd.Timestamp("2026-10-20T00:00:00Z")
WINDOW_HOURS = 0.5
INTERVAL_S = 60.0


def heart_rate_per_minute(data_dir, record):
    ann = wfdb.rdann(os.path.join(data_dir, record), "atr")
    keep = [i for i, s in enumerate(ann.symbol) if s in BEAT_SYMBOLS]
    samples = ann.sample[keep].astype(float)
    fs = float(ann.fs)
    if len(samples) < 3:
        return pd.DataFrame(columns=["stream", "timestamp", "value"])
    rr = np.diff(samples) / fs
    hr = 60.0 / rr
    t_sec = samples[1:] / fs
    minute = np.floor(t_sec / 60.0).astype(int)
    df = pd.DataFrame({"minute": minute, "hr": hr}).groupby("minute")["hr"].median().reset_index()
    df["timestamp"] = START + pd.to_timedelta(df["minute"] * 60 + 60, unit="s")
    df["stream"] = record
    df["value"] = df["hr"]
    return df[["stream", "timestamp", "value"]].reset_index(drop=True)


def inject(df, kind, rng, artifact_bpm=100.0):
    out = df.copy()
    n = len(out)
    if kind == "sparse":
        drop = rng.choice(n, size=int(round(0.7 * n)), replace=False)
        out = out.drop(out.index[drop]).reset_index(drop=True)
    elif kind == "noisy":
        hit = rng.choice(n, size=max(1, int(round(0.10 * n))), replace=False)
        out.loc[hit, "value"] = out.loc[hit, "value"] + artifact_bpm
    return out


def run_case(df, kind, **tag_kwargs):
    now = df["timestamp"].max()
    if kind == "stale":
        now = now + pd.Timedelta(hours=2)
    result = tag_streams(df, now, expected_interval_s=INTERVAL_S, window_hours=WINDOW_HOURS, **tag_kwargs)
    return set(result["tags"].iloc[0].split(";")) - {"reliable"} if len(result) else set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--records", nargs="+", required=True)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--artifact-bpm", type=float, default=100.0)
    parser.add_argument("--outlier-method", choices=["mad", "rolling"], default="mad")
    parser.add_argument("--rolling-bpm", type=float, default=30.0)
    parser.add_argument("--split", choices=["all", "dev", "test"], default="all",
                        help="dev = every other record (sorted), test = the rest.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    records = sorted(args.records, key=int)
    if args.split == "dev":
        records = records[::2]
    elif args.split == "test":
        records = records[1::2]
    tag_kwargs = {"outlier_method": args.outlier_method, "rolling_bpm": args.rolling_bpm}

    faults = ["stale", "sparse", "noisy"]
    expected = {"stale": "stale", "sparse": "sparse", "noisy": "noisy"}
    rng = np.random.default_rng(0)
    rows = []
    fp = {f: [] for f in faults}
    detect = {f: [] for f in faults}

    for rec in records:
        base = heart_rate_per_minute(args.data_dir, rec)
        if len(base) < 10:
            continue
        clean_tags = run_case(base, "clean", **tag_kwargs)
        for f in faults:
            fp[f].append(expected[f] in clean_tags)
        for f in faults:
            for _ in range(args.trials):
                df = inject(base, f, rng, args.artifact_bpm) if f != "stale" else base
                tags = run_case(df, f, **tag_kwargs)
                detect[f].append(expected[f] in tags)
        rows.append({"record": rec, "minutes": len(base),
                     "clean_tags": ";".join(sorted(clean_tags)) or "reliable"})

    summary = {
        "records_used": [r["record"] for r in rows],
        "trials_per_fault": args.trials * len(rows),
        "artifact_bpm": args.artifact_bpm,
        "outlier_method": args.outlier_method,
        "rolling_bpm": args.rolling_bpm,
        "split": args.split,
        "detection_rate": {f: round(float(np.mean(detect[f])), 3) for f in faults},
        "false_positive_rate_on_clean": {f: round(float(np.mean(fp[f])), 3) for f in faults},
        "per_record": rows,
    }
    text = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
