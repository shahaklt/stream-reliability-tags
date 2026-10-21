import numpy as np
import pandas as pd

from stream_tags.core import tag_streams

NOW = "2026-10-20T12:00:00Z"


def stream_df(name, timestamps, values=None):
    values = values if values is not None else np.zeros(len(timestamps))
    return pd.DataFrame({"stream": name, "timestamp": pd.to_datetime(timestamps, utc=True), "value": values})


def row(result, name):
    return result.set_index("stream").loc[name]


def test_healthy_stream_is_reliable():
    ts = pd.date_range(end=NOW, periods=1440, freq="60s")
    rng = np.random.default_rng(0)
    df = stream_df("hr", ts, rng.normal(60, 1, len(ts)))
    result = tag_streams(df, NOW, expected_interval_s=60, window_hours=24)
    assert row(result, "hr")["tags"] == "reliable"
    assert row(result, "hr")["confidence"] == "high"


def test_old_last_sample_is_stale():
    ts = pd.date_range(end="2026-10-20T06:00:00Z", periods=1440, freq="60s")
    df = stream_df("hr", ts)
    result = tag_streams(df, NOW, expected_interval_s=60, window_hours=24)
    assert "stale" in row(result, "hr")["tags"]


def test_sparse_stream_is_tagged():
    ts = pd.date_range(end=NOW, periods=50, freq="30min")
    df = stream_df("glucose", ts)
    result = tag_streams(df, NOW, expected_interval_s=60, window_hours=24)
    assert "sparse" in row(result, "glucose")["tags"]


def test_spiky_stream_is_noisy():
    ts = pd.date_range(end=NOW, periods=400, freq="60s")
    rng = np.random.default_rng(1)
    values = rng.normal(0, 1, len(ts))
    values[::8] = 500.0  # about 12% spikes
    df = stream_df("spo2", ts, values)
    result = tag_streams(df, NOW, expected_interval_s=60, window_hours=24)
    assert "noisy" in row(result, "spo2")["tags"]


def test_per_stream_interval_override():
    ts = pd.date_range(end=NOW, periods=24, freq="60min")
    df = stream_df("labs", ts)
    default = tag_streams(df, NOW, expected_interval_s=60)
    overridden = tag_streams(df, NOW, expected_interval_s=3600, intervals={"labs": 3600})
    assert "sparse" in row(default, "labs")["tags"]
    assert "sparse" not in row(overridden, "labs")["tags"]


def test_multiple_streams_each_get_a_row():
    a = stream_df("a", pd.date_range(end=NOW, periods=10, freq="60s"))
    b = stream_df("b", pd.date_range(end=NOW, periods=10, freq="60s"))
    result = tag_streams(pd.concat([a, b]), NOW, expected_interval_s=60)
    assert set(result["stream"]) == {"a", "b"}
