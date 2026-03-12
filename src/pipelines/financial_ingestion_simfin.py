import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import simfin as sf

#this function looks to find the most recent S&P 500 snapshot CSV and get the path to it.
def latest_sp500_snapshot_path(data_dir: str | Path = "data/raw") -> Path:
    data_path = Path(data_dir)
    matches = sorted(data_path.glob("sp500_constituents_*.csv"))
    if not matches:
        raise FileNotFoundError(
            "No S&P 500 snapshot found. Run scripts/download_sp500.py first."
        )
    return matches[-1]

#This function opens the S&P 500 CSV file and returns a clean Python list of ticker symbols.
def load_sp500_tickers(snapshot_path: str | Path | None = None) -> list[str]:
    path = Path(snapshot_path) if snapshot_path else latest_sp500_snapshot_path()
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        raise ValueError(f"Ticker column not found in {path}")
    tickers = [
        ticker
        for ticker in (str(t).strip().upper() for t in df["ticker"].dropna())
        if ticker
    ]
    if not tickers:
        raise ValueError(f"No tickers loaded from {path}")
    return tickers

#for each stock ticker, keep only the newest financial row
def _latest_by_ticker(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index().sort_values(["Ticker", "Report Date"])
    out = out.groupby("Ticker", as_index=False).tail(1)
    return out.reset_index(drop=True)

#It keeps only the most recent stock price row for each ticker.
def _latest_shareprice_by_ticker(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index().sort_values(["Ticker", "Date"])
    out = out.groupby("Ticker", as_index=False).tail(1)
    return out.reset_index(drop=True)

# prevents errors from happenning 
def _safe_divide(numer: pd.Series, denom: pd.Series) -> pd.Series:
    return numer / denom.replace({0: pd.NA})


def build_simfin_financial_snapshot(
    sp500_snapshot_path: str | Path | None = None,
    api_key: str | None = None,
    data_dir: str | Path = "data/simfin_cache",
    max_tickers: int | None = None,
) -> pd.DataFrame:
    """Load bulk SimFin datasets and build a raw metrics snapshot for S&P 500 tickers."""
    key = api_key or os.getenv("SIMFIN_API_KEY")
    if not key:
        raise ValueError("Missing SimFin API key. Set SIMFIN_API_KEY and retry.")

    tickers = load_sp500_tickers(sp500_snapshot_path)
    if max_tickers is not None:
        tickers = tickers[:max_tickers]

    sf.set_api_key(key)
    sf.set_data_dir(str(data_dir))

    companies = sf.load_companies(market="us").reset_index()
    income = _latest_by_ticker(sf.load_income(variant="annual", market="us"))
    balance = _latest_by_ticker(sf.load_balance(variant="annual", market="us"))
    shareprices = _latest_shareprice_by_ticker(sf.load_shareprices(variant="latest", market="us"))

    # Keep raw provider names for transparency in this stage.
    df = (
        pd.DataFrame({"ticker": tickers})
        .merge(companies[["Ticker", "Company Name", "SimFinId"]], left_on="ticker", right_on="Ticker", how="left")
        .merge(
            income[
                [
                    "Ticker",
                    "Report Date",
                    "Publish Date",
                    "Fiscal Year",
                    "Fiscal Period",
                    "Shares (Basic)",
                    "Shares (Diluted)",
                    "Revenue",
                    "Gross Profit",
                    "Operating Income (Loss)",
                    "Net Income",
                    "Net Income (Common)",
                ]
            ],
            on="Ticker",
            how="left",
        )
        .merge(
            balance[
                [
                    "Ticker",
                    "Total Assets",
                    "Total Liabilities",
                    "Total Equity",
                    "Short Term Debt",
                    "Long Term Debt",
                    "Cash, Cash Equivalents & Short Term Investments",
                    "Total Current Assets",
                    "Total Current Liabilities",
                ]
            ],
            on="Ticker",
            how="left",
        )
        .merge(
            shareprices[
                [
                    "Ticker",
                    "Date",
                    "Close",
                    "Adj. Close",
                    "Shares Outstanding",
                    "Volume",
                ]
            ],
            on="Ticker",
            how="left",
        )
    )

    # Compute simple derived fields useful for later scoring. These are not
    # SimFin "derived" endpoint metrics; they are local calculations.
    shares_for_eps = df["Shares (Diluted)"].fillna(df["Shares (Basic)"])
    df["eps_simple"] = _safe_divide(df["Net Income (Common)"], shares_for_eps)
    df["pe_simple"] = _safe_divide(df["Close"], df["eps_simple"])
    df["totalDebt_simple"] = df["Short Term Debt"].fillna(0) + df["Long Term Debt"].fillna(0)
    df["currentRatio_simple"] = _safe_divide(
        df["Total Current Assets"], df["Total Current Liabilities"]
    )

    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    output = pd.DataFrame(
        {
            "ticker": df["ticker"],
            "company_name": df["Company Name"],
            "simfin_id": df["SimFinId"],
            "source": "simfin",
            "source_dataset_income": "us-income-annual",
            "source_dataset_balance": "us-balance-annual",
            "source_dataset_shareprices": "us-shareprices-latest",
            "fetched_at_utc": fetched_at,
            "report_date": df["Report Date"],
            "publish_date": df["Publish Date"],
            "fiscal_year": df["Fiscal Year"],
            "fiscal_period": df["Fiscal Period"],
            "price_date": df["Date"],
            "close": df["Close"],
            "adj_close": df["Adj. Close"],
            "volume": df["Volume"],
            "shares_outstanding_latest": df["Shares Outstanding"],
            "shares_basic": df["Shares (Basic)"],
            "shares_diluted": df["Shares (Diluted)"],
            "revenue": df["Revenue"],
            "gross_profit": df["Gross Profit"],
            "operating_income": df["Operating Income (Loss)"],
            "net_income": df["Net Income"],
            "net_income_common": df["Net Income (Common)"],
            "total_assets": df["Total Assets"],
            "total_liabilities": df["Total Liabilities"],
            "total_equity": df["Total Equity"],
            "short_term_debt": df["Short Term Debt"],
            "long_term_debt": df["Long Term Debt"],
            "total_debt_simple": df["totalDebt_simple"],
            "cash_and_equivalents": df["Cash, Cash Equivalents & Short Term Investments"],
            "total_current_assets": df["Total Current Assets"],
            "total_current_liabilities": df["Total Current Liabilities"],
            "current_ratio_simple": df["currentRatio_simple"],
            "eps_simple": df["eps_simple"],
            "pe_simple": df["pe_simple"],
        }
    )

    return output


def save_simfin_financial_metrics_snapshot(
    api_key: str | None = None,
    output_dir: str | Path = "data/raw",
    sp500_snapshot_path: str | Path | None = None,
    max_tickers: int | None = None,
) -> Path:
    df = build_simfin_financial_snapshot(
        sp500_snapshot_path=sp500_snapshot_path,
        api_key=api_key,
        max_tickers=max_tickers,
    )

    if df.empty:
        raise RuntimeError("No rows produced for SimFin financial metrics snapshot.")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_date = datetime.now(UTC).date().isoformat()
    suffix = f"_{max_tickers}" if max_tickers is not None else ""
    out_path = out_dir / f"simfin_financials_{snapshot_date}{suffix}.csv"
    df.to_csv(out_path, index=False)
    return out_path
