from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.data_sources.fmp_client import FMPClient, FMPClientError


def latest_sp500_snapshot_path(data_dir: str | Path = "data/raw") -> Path:
    data_path = Path(data_dir)
    matches = sorted(data_path.glob("sp500_constituents_*.csv"))
    if not matches:
        raise FileNotFoundError(
            "No S&P 500 snapshot found. Run scripts/download_sp500.py first."
        )
    return matches[-1]


def load_sp500_tickers(snapshot_path: str | Path | None = None) -> list[str]:
    path = Path(snapshot_path) if snapshot_path else latest_sp500_snapshot_path()
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        raise ValueError(f"Ticker column not found in {path}")
    tickers = [str(t).strip().upper() for t in df["ticker"].dropna().tolist()]
    tickers = [t for t in tickers if t]
    if not tickers:
        raise ValueError(f"No tickers loaded from {path}")
    return tickers


def _timestamp_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def download_fmp_financial_metrics(
    tickers: list[str],
    api_key: str,
    sleep_seconds: float = 0.25,
    max_tickers: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download raw financial metrics for a list of tickers.

    Returns a tuple of (metrics_df, failures_df).
    """
    client = FMPClient(api_key=api_key)
    rows: list[dict] = []
    failures: list[dict] = []

    iterable = tickers[:max_tickers] if max_tickers is not None else tickers

    for idx, ticker in enumerate(iterable, start=1):
        try:
            row = client.fetch_core_metrics(ticker)
            row["fetched_at_utc"] = _timestamp_utc()
            rows.append(row)
        except FMPClientError as exc:
            failures.append(
                {
                    "ticker": ticker,
                    "error": str(exc),
                    "failed_at_utc": _timestamp_utc(),
                }
            )
        if sleep_seconds > 0 and idx < len(iterable):
            time.sleep(sleep_seconds)

    metrics_df = pd.DataFrame(rows)
    failures_df = pd.DataFrame(failures)
    return metrics_df, failures_df


def save_fmp_financial_metrics_snapshot(
    api_key: str | None = None,
    output_dir: str | Path = "data/raw",
    sp500_snapshot_path: str | Path | None = None,
    max_tickers: int | None = None,
    sleep_seconds: float = 0.25,
) -> tuple[Path, Path | None]:
    """Read the latest S&P 500 list, download FMP metrics, and save snapshots."""
    key = api_key or os.getenv("FMP_API_KEY")
    if not key:
        raise ValueError("Missing FMP API key. Set FMP_API_KEY and retry.")

    tickers = load_sp500_tickers(sp500_snapshot_path)
    metrics_df, failures_df = download_fmp_financial_metrics(
        tickers=tickers,
        api_key=key,
        sleep_seconds=sleep_seconds,
        max_tickers=max_tickers,
    )

    if metrics_df.empty:
        raise RuntimeError("No financial metrics were downloaded successfully.")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_date = datetime.now(UTC).date().isoformat()
    suffix = f"_{max_tickers}" if max_tickers is not None else ""

    metrics_path = out_dir / f"fmp_financials_{snapshot_date}{suffix}.csv"
    metrics_df.to_csv(metrics_path, index=False)

    failures_path: Path | None = None
    if not failures_df.empty:
        failures_path = out_dir / f"fmp_financials_failures_{snapshot_date}{suffix}.csv"
        failures_df.to_csv(failures_path, index=False)

    return metrics_path, failures_path
