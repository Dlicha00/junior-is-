from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from io import StringIO
from urllib.request import Request, urlopen

import pandas as pd


WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


@dataclass(frozen=True)
class SP500SnapshotMetadata:
    source: str
    source_url: str
    fetched_at_utc: str
    record_count: int


def normalize_ticker(symbol: str) -> str:
    """Normalize symbols for a canonical internal format.

    Wikipedia uses dots for share classes (e.g. BRK.B). We preserve that
    canonical format here and let downstream providers map formats as needed.
    """
    return symbol.strip().upper()


def fetch_sp500_constituents() -> tuple[pd.DataFrame, SP500SnapshotMetadata]:
    """Fetch current S&P 500 constituents from Wikipedia."""
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

    # The first table is the constituent table on the page.
    raw = tables[0].copy()

    expected_cols = {"Symbol", "Security"}
    if not expected_cols.issubset(set(raw.columns)):
        raise RuntimeError(
            f"Unexpected Wikipedia table schema. Missing columns: "
            f"{sorted(expected_cols - set(raw.columns))}"
        )

    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    df = pd.DataFrame(
        {
            "ticker": raw["Symbol"].astype(str).map(normalize_ticker),
            "company_name": raw["Security"].astype(str).str.strip(),
            "gics_sector": raw.get("GICS Sector", pd.Series([""] * len(raw))).astype(str),
            "gics_sub_industry": raw.get(
                "GICS Sub-Industry", pd.Series([""] * len(raw))
            ).astype(str),
            "source": "wikipedia",
            "source_url": WIKIPEDIA_SP500_URL,
            "fetched_at_utc": fetched_at,
        }
    )

    # Drop duplicate ticker rows if the source ever changes unexpectedly.
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)

    if df.empty:
        raise RuntimeError("Fetched S&P 500 constituent list is empty.")

    if not 400 <= len(df) <= 600:
        raise RuntimeError(f"Unexpected constituent count: {len(df)}")

    metadata = SP500SnapshotMetadata(
        source="wikipedia",
        source_url=WIKIPEDIA_SP500_URL,
        fetched_at_utc=fetched_at,
        record_count=len(df),
    )
    return df, metadata


def save_sp500_snapshot(
    output_dir: str | Path = "data/raw",
    filename_prefix: str = "sp500_constituents",
) -> Path:
    """Fetch and save a dated S&P 500 constituent CSV snapshot."""
    df, _ = fetch_sp500_constituents()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_date = datetime.now(UTC).date().isoformat()
    output_path = out_dir / f"{filename_prefix}_{snapshot_date}.csv"
    df.to_csv(output_path, index=False)
    return output_path
