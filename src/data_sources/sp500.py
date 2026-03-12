from __future__ import annotations
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def normalize_ticker(symbol):
    return symbol.strip().upper()
#removes extra spaces and converts to uppercase (This makes tickers consistent.)

def fetch_sp500_constituents():
    #Fetch current S&P 500 constituents from Wikipedia.
    request = Request(
        #This creates a request to the Wikipedia page.
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
        #Visit the page and store its HTML text.

    tables = pd.read_html(StringIO(html))
    if not tables:
        raise RuntimeError("No tables found on Wikipedia S&P 500 page.")

    # The first table is the constituent table on the page.
    raw = tables[0].copy()

    #check if required columns are present in the table. If not, raise an error with details.
    expected_cols = {"Symbol", "Security"}
    if not expected_cols.issubset(set(raw.columns)):
        raise RuntimeError(
            print("Unexpected Wikipedia table schema. Missing columns: ", sorted(expected_cols - set(raw.columns)))
        )
    # keep track of when the data was fetched for debugging purposes in the future .
    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()


    # clean and normalize the data into a consistent format. We also handle missing optional columns gracefully by filling them with empty strings.
    df = pd.DataFrame(
    {
        "ticker": raw["Symbol"].astype(str).map(normalize_ticker),
        "company_name": raw["Security"].astype(str).str.strip(),
        "gics_sector": raw.get("GICS Sector", pd.Series([""] * len(raw))).astype(str),
        "gics_sub_industry": raw.get( "GICS Sub-Industry", pd.Series([""] * len(raw))).astype(str),
        "source": "wikipedia",
        "source_url": WIKIPEDIA_SP500_URL,
        "fetched_at_utc": fetched_at,
    }
    )

    # Drop duplicate ticker rows if the source ever changes unexpectedly.
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)


    #Check if there is major issues with the fetched data.
    if df.empty:
        raise RuntimeError("Fetched S&P 500 constituent list is empty.")

    if not 400 <= len(df) <= 600:
        raise RuntimeError(f"Unexpected constituent count: {len(df)}")

    return df

# this function fetches the latest cleaned S&P 500 constituents and saves them as a date-stamped CSV file
def save_sp500_snapshot(
    output_dir: str | Path = "data/raw",
    filename_prefix: str = "sp500_constituents",
) -> Path:
    """Fetch and save a dated S&P 500 constituent CSV snapshot."""
    df = fetch_sp500_constituents()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_date = datetime.now(UTC).date().isoformat()
    output_path = out_dir / f"{filename_prefix}_{snapshot_date}.csv"
    df.to_csv(output_path, index=False)

    return output_path
