"""Tag each data stream as reliable, stale, sparse, or noisy so downstream text can state its confidence."""

import numpy as np
import pandas as pd


def load_streams(path):
    """CSV with columns: stream, timestamp (ISO 8601), value."""
    df = pd.read_csv(path)
    missing = [c for c in ["stream", "timestamp", "value"] if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="raise")
    return df


def tag_streams(df, now, expected_interval_s=60.0, window_hours=24.0, intervals=None,
                stale_factor=2.0, min_coverage=0.5, outlier_k=5.0, max_outlier_frac=0.05,
                outlier_method="mad", rolling_window=11, rolling_bpm=30.0):
    """One row per stream. `intervals` maps stream name to its expected spacing in seconds.

    outlier_method:
      "mad"     - value differs from the window median by more than outlier_k robust sigmas.
      "rolling" - value differs from its centered rolling median (rolling_window samples) by
                  more than rolling_bpm. Tolerates sustained physiological shifts; still catches
                  isolated spikes.
    """
    now = pd.Timestamp(now, tz="UTC") if pd.Timestamp(now).tzinfo is None else pd.Timestamp(now)
    window_start = now - pd.Timedelta(hours=window_hours)
    intervals = intervals or {}
    rows = []
    for stream, sub in df.groupby("stream"):
        sub = sub.sort_values("timestamp")
        interval = float(intervals.get(stream, expected_interval_s))
        last = sub["timestamp"].max()
        age_s = (now - last).total_seconds()

        win = sub[(sub["timestamp"] >= window_start) & (sub["timestamp"] <= now)]
        n = len(win)
        expected = window_hours * 3600.0 / interval
        coverage = min(1.0, n / expected)
        gaps = win["timestamp"].diff().dt.total_seconds().dropna()
        max_gap = float(gaps.max()) if len(gaps) else np.nan

        outlier_frac = np.nan
        if n >= 3:
            vals = win["value"].to_numpy(dtype=float)
            if outlier_method == "rolling":
                local = win["value"].rolling(rolling_window, center=True, min_periods=1).median().to_numpy()
                outlier_frac = float(np.mean(np.abs(vals - local) > rolling_bpm))
            elif outlier_method == "mad":
                med = np.median(vals)
                mad = 1.4826 * np.median(np.abs(vals - med))
                outlier_frac = float(np.mean(np.abs(vals - med) > outlier_k * mad)) if mad > 0 else 0.0
            else:
                raise ValueError(f"unknown outlier_method: {outlier_method!r}")

        tags = []
        if age_s > stale_factor * interval:
            tags.append("stale")
        if n == 0 or coverage < min_coverage:
            tags.append("sparse")
        if not np.isnan(outlier_frac) and outlier_frac > max_outlier_frac:
            tags.append("noisy")

        rows.append({
            "stream": stream,
            "n_in_window": int(n),
            "coverage": round(coverage, 4),
            "age_hours": round(age_s / 3600.0, 3),
            "max_gap_s": max_gap,
            "outlier_fraction": outlier_frac,
            "tags": ";".join(tags) if tags else "reliable",
            "confidence": "low" if tags else "high",
        })
    return pd.DataFrame(rows)
