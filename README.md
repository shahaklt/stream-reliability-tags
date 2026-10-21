# stream-reliability-tags

Tags each timestamped data stream (wearable signal, lab feed, sensor) with one or more reliability flags, so any text built on top of it can say how much to trust it. The motivating case is a consumer health companion that texts insights from several streams. The failure mode it targets is a confident message built on a stale or noisy stream.

## Tags

| Tag | Meaning |
|---|---|
| `stale` | last sample is older than `stale_factor` × expected interval (default 2×) |
| `sparse` | coverage in the window is below 50% of the expected sample count, or there are no samples |
| `noisy` | more than 5% of values are outliers (|x − median| > 5 × robust sigma, from MAD) |
| `reliable` | none of the above. `confidence` is `high`; any tag gives `low` |

Each row also reports `coverage`, `age_hours`, `max_gap_s`, and `outlier_fraction`.

## Usage

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m stream_tags.cli streams.csv --interval-s 60 --window-hours 24 --now 2026-10-20T12:00:00Z --out tags.csv
```

Input: CSV with `stream,timestamp,value`. Use `--now` for reproducible output. Per-stream intervals need the Python API (`tag_streams(..., intervals={...})`).

## Limits

- Reliability is about data quality, not clinical meaning. Nothing here is a diagnosis or a medical-device check, and it should never be presented as one.
- The thresholds are defaults you should set per stream.
- Outlier detection is a robust screen. Real artifacts (motion, sensor drift) need their own handling.
- Built and tested on synthetic streams only.
