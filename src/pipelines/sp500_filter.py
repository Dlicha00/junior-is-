from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


def latest_simfin_snapshot_path(data_dir: str | Path = "data/raw") -> Path:
    data_path = Path(data_dir)
    matches = sorted(data_path.glob("simfin_financials_*.csv"), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(
            "No SimFin financial snapshot found. Run scripts/download_financials_simfin.py first."
        )
    # Prefer full-run files like simfin_financials_YYYY-MM-DD.csv over test files
    # such as simfin_financials_YYYY-MM-DD_5.csv when both exist.
    full_run = [
        p
        for p in matches
        if p.stem.count("_") == 2  # simfin + financials + YYYY-MM-DD
    ]
    if full_run:
        return full_run[-1]
    return matches[-1]


def _is_missing(series: pd.Series) -> pd.Series:
    return series.isna() | (series.astype(str).str.strip() == "")


def apply_sp500_eligibility_filter(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required_columns = [
        "ticker",
        "company_name",
        "revenue",
        "net_income",
        "close",
        "pe_simple",
    ]
    missing_columns = [c for c in required_columns if c not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    working = df.copy()
    working["exclusion_reason"] = ""

    reason_checks: list[tuple[str, pd.Series]] = [
        ("missing_company_name", _is_missing(working["company_name"])),
        ("missing_revenue", working["revenue"].isna()),
        ("missing_net_income", working["net_income"].isna()),
        ("missing_close", working["close"].isna()),
        ("missing_pe_simple", working["pe_simple"].isna()),
        ("non_positive_revenue", working["revenue"].fillna(0) <= 0),
        ("non_positive_close", working["close"].fillna(0) <= 0),
        ("non_positive_total_assets", working.get("total_assets", pd.Series([1] * len(working))).fillna(0) <= 0),
    ]

    for reason, mask in reason_checks:
        working.loc[mask, "exclusion_reason"] = (
            working.loc[mask, "exclusion_reason"]
            .replace("", reason)
            .where(working.loc[mask, "exclusion_reason"] == "", working.loc[mask, "exclusion_reason"] + ";" + reason)
        )

    # Keep only one row per ticker if duplicates exist.
    duplicates = working["ticker"].duplicated(keep="first")
    working.loc[duplicates, "exclusion_reason"] = working.loc[duplicates, "exclusion_reason"].replace("", "duplicate_ticker")
    working.loc[duplicates & (working["exclusion_reason"] != "duplicate_ticker"), "exclusion_reason"] = (
        working.loc[duplicates & (working["exclusion_reason"] != "duplicate_ticker"), "exclusion_reason"] + ";duplicate_ticker"
    )

    excluded = working[working["exclusion_reason"] != ""].copy()
    eligible = working[working["exclusion_reason"] == ""].copy()

    return eligible.reset_index(drop=True), excluded.reset_index(drop=True)


def save_sp500_filter_outputs(
    input_path: str | Path | None = None,
    output_dir: str | Path = "data/processed",
) -> tuple[Path, Path]:
    source_path = Path(input_path) if input_path else latest_simfin_snapshot_path()
    df = pd.read_csv(source_path)

    eligible, excluded = apply_sp500_eligibility_filter(df)
    filtered_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    eligible["filtered_at_utc"] = filtered_at
    excluded["filtered_at_utc"] = filtered_at

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_date = datetime.now(UTC).date().isoformat()

    eligible_path = out_dir / f"eligible_stocks_{snapshot_date}.csv"
    excluded_path = out_dir / f"excluded_stocks_{snapshot_date}.csv"

    eligible.to_csv(eligible_path, index=False)
    excluded.to_csv(excluded_path, index=False)
    return eligible_path, excluded_path
