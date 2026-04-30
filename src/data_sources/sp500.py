from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def normalize_ticker(symbol: str) -> str:
    return symbol.strip().upper()


def fetch_sp500_constituents() -> pd.DataFrame:
    """Fetch current S&P 500 constituents from Wikipedia."""
    # Use a browser-like request so Wikipedia accepts the fetch.
    request = Request(
        WIKIPEDIA_SP500_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )

    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    tables = pd.read_html(StringIO(html))
    if not tables:
        raise RuntimeError("No tables found on Wikipedia S&P 500 page.")

    raw = tables[0].copy()

    # Make sure the table still has the columns we expect.
    expected_cols = {"Symbol", "Security"}
    if not expected_cols.issubset(set(raw.columns)):
        missing = sorted(expected_cols - set(raw.columns))
        raise RuntimeError(f"Unexpected Wikipedia table schema. Missing columns: {missing}")

    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    df = pd.DataFrame(
        {
            "ticker": raw["Symbol"].astype(str).map(normalize_ticker),
            "company_name": raw["Security"].astype(str).str.strip(),
            "gics_sector": raw.get("GICS Sector", pd.Series([""] * len(raw))).astype(str),
            "gics_sub_industry": raw.get("GICS Sub-Industry", pd.Series([""] * len(raw))).astype(str),
            "source": "wikipedia",
            "source_url": WIKIPEDIA_SP500_URL,
            "fetched_at_utc": fetched_at,
        }
    )

    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)

    # Sanity check so a bad scrape does not quietly pass.
    if df.empty:
        raise RuntimeError("Fetched S&P 500 constituent list is empty.")

    if not 400 <= len(df) <= 600:
        raise RuntimeError(f"Unexpected constituent count: {len(df)}")

    return df


def save_sp500_snapshot(
    output_dir: str | Path = "data/raw",
    filename_prefix: str = "sp500_constituents",
) -> Path:
    """Fetch and save a dated S&P 500 constituent CSV snapshot."""
    # Keep snapshots dated so runs are reproducible.
    df = fetch_sp500_constituents()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_date = datetime.now(UTC).date().isoformat()
    output_path = out_dir / f"{filename_prefix}_{snapshot_date}.csv"
    df.to_csv(output_path, index=False)

    return output_path
