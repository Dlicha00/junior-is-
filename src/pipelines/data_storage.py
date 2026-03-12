from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def latest_eligible_snapshot_path(data_dir: str | Path = "data/processed") -> Path:
    data_path = Path(data_dir)
    matches = sorted(
        data_path.glob("eligible_stocks_*.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if not matches:
        raise FileNotFoundError(
            "No eligible stock snapshot found. Run scripts/filter_sp500_eligibility.py first."
        )
    return matches[-1]


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def build_metrics_master(input_path: str | Path | None = None) -> pd.DataFrame:
    source_path = Path(input_path) if input_path else latest_eligible_snapshot_path()
    df = pd.read_csv(source_path)

    # Minimal canonical schema for downstream scoring/ranking.
    keep_cols = [
        "ticker",
        "company_name",
        "source",
        "fetched_at_utc",
        "report_date",
        "publish_date",
        "fiscal_year",
        "fiscal_period",
        "price_date",
        "close",
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "total_debt_simple",
        "cash_and_equivalents",
        "current_ratio_simple",
        "eps_simple",
        "pe_simple",
    ]

    missing = [c for c in keep_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in eligible snapshot: {missing}")

    out = df[keep_cols].copy()

    str_cols = ["ticker", "company_name", "source", "fiscal_period"]
    for col in str_cols:
        out[col] = out[col].astype("string")

    date_cols = ["fetched_at_utc", "report_date", "publish_date", "price_date"]
    for col in date_cols:
        out[col] = _to_datetime(out[col])

    num_cols = [
        "fiscal_year",
        "close",
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "total_debt_simple",
        "cash_and_equivalents",
        "current_ratio_simple",
        "eps_simple",
        "pe_simple",
    ]
    for col in num_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["storage_built_at_utc"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    return out


def save_metrics_master(
    input_path: str | Path | None = None,
    output_dir: str | Path = "data/processed",
) -> Path:
    df = build_metrics_master(input_path=input_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_date = datetime.now(UTC).date().isoformat()
    out_path = out_dir / f"metrics_master_{snapshot_date}.csv"
    df.to_csv(out_path, index=False)
    return out_path
