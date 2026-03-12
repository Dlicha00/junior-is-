from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware


ROOT_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
RAW_DIR = ROOT_DIR / "data" / "raw"


app = FastAPI(title="Stock Filter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _extract_date_key(path: Path) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else ""


def _latest_file(directory: Path, pattern: str) -> Path:
    files = list(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found for pattern: {directory / pattern}")
    return max(files, key=_extract_date_key)


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _fmt_compact_usd(value: float | None) -> str:
    if value is None:
        return "N/A"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.1f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _fmt_number(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def _load_sector_map() -> tuple[dict[str, str], Path]:
    sp500_file = _latest_file(RAW_DIR, "sp500_constituents_*.csv")
    mapping: dict[str, str] = {}
    with sp500_file.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if ticker:
                mapping[ticker] = (row.get("gics_sector") or "N/A").strip() or "N/A"
    return mapping, sp500_file


def _load_eligible_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eligible_file = _latest_file(PROCESSED_DIR, "eligible_stocks_*.csv")
    sector_map, sp500_file = _load_sector_map()

    rows: list[dict[str, Any]] = []
    with eligible_file.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            revenue = _to_float(row.get("revenue"))
            pe_ratio = _to_float(row.get("pe_simple"))
            debt = _to_float(row.get("total_debt_simple"))

            rows.append(
                {
                    "ticker": ticker,
                    "company_name": (row.get("company_name") or "").strip() or ticker,
                    "sector": sector_map.get(ticker, "N/A"),
                    "revenue": revenue,
                    "pe_ratio": pe_ratio,
                    "debt": debt,
                    "revenue_display": _fmt_compact_usd(revenue),
                    "pe_display": _fmt_number(pe_ratio, 1),
                    "debt_display": _fmt_compact_usd(debt),
                }
            )

    filled_rows = [r for r in rows if r["revenue"] is not None and r["pe_ratio"] is not None and r["debt"] is not None]
    # Coverage is measured against the full S&P 500 universe, not only eligible rows.
    coverage_denominator = len(sector_map)
    coverage_pct = (len(filled_rows) / coverage_denominator * 100) if coverage_denominator else 0.0

    snapshot = {
        "eligible_file": eligible_file.name,
        "sp500_file": sp500_file.name,
        "universe_count": len(sector_map),
        "eligible_count": len(rows),
        "complete_required_fields_count": len(filled_rows),
        "coverage_pct": round(coverage_pct, 1),
    }
    return rows, snapshot


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stocks/eligible")
def eligible_stocks(limit: int = Query(default=500, ge=1, le=2000)) -> dict[str, Any]:
    try:
        rows, snapshot = _load_eligible_rows()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"snapshot": snapshot, "items": rows[:limit]}


@app.get("/stocks/eligible/{ticker}")
def eligible_stock_detail(ticker: str) -> dict[str, Any]:
    target = ticker.strip().upper()
    try:
        rows, snapshot = _load_eligible_rows()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    for row in rows:
        if row["ticker"] == target:
            return {"snapshot": snapshot, "item": row}

    raise HTTPException(status_code=404, detail=f"Ticker not found in eligible list: {target}")
