from datetime import datetime, timezone

import click

from .core import load_streams, tag_streams


@click.command()
@click.argument("data", type=click.Path(exists=True, dir_okay=False))
@click.option("--interval-s", default=60.0, show_default=True, help="Default expected spacing in seconds.")
@click.option("--window-hours", default=24.0, show_default=True)
@click.option("--now", default=None, help="Reference time, ISO 8601 UTC. Default: current time.")
@click.option("--out", type=click.Path(dir_okay=False), default=None)
def main(data, interval_s, window_hours, now, out):
    """Tag each stream in a long-format CSV (stream, timestamp, value)."""
    df = load_streams(data)
    reference = now or datetime.now(timezone.utc).isoformat()
    result = tag_streams(df, reference, expected_interval_s=interval_s, window_hours=window_hours)
    if out:
        result.to_csv(out, index=False)
        click.echo(f"wrote {out}: {len(result)} streams")
    else:
        click.echo(result.to_string(index=False))


if __name__ == "__main__":
    main()
