from __future__ import annotations

import csv
import json
import math
import os
import re
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()


# Main folders used by the API.
ROOT_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
RAW_DIR = ROOT_DIR / "data" / "raw"
SIMFIN_CACHE_DIR = ROOT_DIR / "data" / "simfin_cache"
QUALITATIVE_SCORE_PREFIX = "qualitative_scores_"
QUALITATIVE_KEYS = [
    "moat_points",
    "leadership_points",
    "secular_trend_points",
    "culture_mission_points",
    "talent_quality_points",
    "recession_resilience_points",
]
QUANTITATIVE_KEYS = [
    "cash_vs_debt_points",
    "revenue_growth_points",
    "operating_margin_points",
    "short_interest_points",
    "institutional_ownership_points",
    "scalability_points",
    "share_vs_sp500_points",
]
GEMINI_API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


app = FastAPI(title="Stock Filter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request options for running Gemini scoring from the frontend/API.
class QualitativeScoreRequest(BaseModel):
    tickers: list[str] | None = Field(default=None, description="Optional ticker subset to score.")
    limit: int = Field(default=2000, ge=1, le=2000, description="Max rows to score if tickers are not provided.")
    overwrite: bool = Field(default=False, description="When true, rescoring happens even if cached.")
    max_seconds: int = Field(default=20, ge=5, le=120, description="Max server work time for one request.")
    batch_size: int = Field(default=8, ge=1, le=20, description="How many tickers to score per Gemini call.")


def _normalize_points_bucket(value: Any) -> int | None:
    # Keep all scores on the 0/5/10 scale.
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 2.5:
        return 0
    if numeric < 7.5:
        return 5
    return 10


def _qualitative_default_map() -> dict[str, int | None]:
    return {key: None for key in QUALITATIVE_KEYS}


def _is_fully_qual_scored(payload: dict[str, Any]) -> bool:
    return all(payload.get(key) in (0, 5, 10) for key in QUALITATIVE_KEYS)


def _latest_qualitative_file() -> Path | None:
    # Load the newest saved LLM score file.
    matches = sorted(PROCESSED_DIR.glob(f"{QUALITATIVE_SCORE_PREFIX}*.csv"), key=_extract_date_key)
    if not matches:
        return None
    # Prefer full snapshots: qualitative_scores_YYYY-MM-DD.csv
    full_run = [p for p in matches if p.stem.count("_") == 2]
    return full_run[-1] if full_run else matches[-1]


def _load_qualitative_score_map() -> tuple[dict[str, dict[str, Any]], Path | None]:
    # Cache saved soft scores by ticker.
    file_path = _latest_qualitative_file()
    if file_path is None:
        return {}, None

    score_map: dict[str, dict[str, Any]] = {}
    with file_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            payload = _qualitative_default_map()
            for key in QUALITATIVE_KEYS:
                payload[key] = _normalize_points_bucket(row.get(key))
            payload["qualitative_summary"] = (row.get("qualitative_summary") or "").strip()
            payload["qualitative_model"] = (row.get("qualitative_model") or "").strip()
            payload["qualitative_scored_at_utc"] = (row.get("qualitative_scored_at_utc") or "").strip()
            score_map[ticker] = payload
    return score_map, file_path


def _save_qualitative_score_map(score_map: dict[str, dict[str, Any]]) -> Path:
    # Save Gemini scores so we do not rescore every refresh.
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_date = datetime.now(UTC).date().isoformat()
    out_path = PROCESSED_DIR / f"{QUALITATIVE_SCORE_PREFIX}{snapshot_date}.csv"

    fieldnames = ["ticker", *QUALITATIVE_KEYS, "qualitative_summary", "qualitative_model", "qualitative_scored_at_utc"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ticker in sorted(score_map):
            payload = score_map[ticker]
            writer.writerow(
                {
                    "ticker": ticker,
                    **{k: payload.get(k) for k in QUALITATIVE_KEYS},
                    "qualitative_summary": payload.get("qualitative_summary", ""),
                    "qualitative_model": payload.get("qualitative_model", ""),
                    "qualitative_scored_at_utc": payload.get("qualitative_scored_at_utc", ""),
                }
            )
    return out_path


def _gemini_model_name() -> str:
    configured = (os.getenv("GEMINI_MODEL") or "").strip()
    if not configured:
        return ""
    return configured.removeprefix("models/").strip()


def _gemini_api_key() -> str:
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY environment variable.")
    return key


@lru_cache(maxsize=1)
def _gemini_generate_content_models(api_key: str) -> list[str]:
    # Ask Gemini which models can generate text.
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urlrequest.Request(url=list_url, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=35) as response:
            body = response.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini ListModels error ({exc.code}): {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Gemini ListModels request failed: {exc.reason}") from exc

    parsed = json.loads(body)
    models = parsed.get("models", [])
    supported: list[str] = []
    for model in models:
        methods = model.get("supportedGenerationMethods", [])
        name = str(model.get("name") or "")
        if "generateContent" in methods and name.startswith("models/"):
            supported.append(name.removeprefix("models/"))
    return supported


def _resolve_gemini_model_candidates(api_key: str) -> list[str]:
    # Use a configured model first, otherwise try a few good defaults.
    configured = _gemini_model_name()
    if configured:
        return [configured]

    available = _gemini_generate_content_models(api_key)
    preferred_order = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    ordered = [candidate for candidate in preferred_order if candidate in available]
    for model in available:
        if model not in ordered:
            ordered.append(model)
    if not ordered:
        raise RuntimeError("No Gemini models supporting generateContent were returned by ListModels.")
    return ordered


def _extract_json_object(text: str) -> dict[str, Any]:
    # Gemini sometimes wraps JSON in extra text, so pull out the object.
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response did not contain JSON object.")
    return json.loads(text[start : end + 1])


def _gemini_prompt_for_rows(rows: list[dict[str, Any]]) -> str:
    # Build a strict prompt so the response is easy to parse.
    lines = [
        "You are scoring stocks across 6 qualitative metrics.",
        "Return JSON only in this exact object shape:",
        '{"scores":[{"ticker":"TICKER","moat_points":0|5|10,"leadership_points":0|5|10,"secular_trend_points":0|5|10,"culture_mission_points":0|5|10,"talent_quality_points":0|5|10,"recession_resilience_points":0|5|10,"qualitative_summary":"<=35 words"}]}',
        "Use only 0, 5, or 10 for points.",
        "",
        "Stocks:",
    ]
    for row in rows:
        lines.extend(
            [
                f"- ticker: {row.get('ticker')}",
                f"  company_name: {row.get('company_name')}",
                f"  sector: {row.get('sector')}",
                f"  revenue: {row.get('revenue')}",
                f"  pe_ratio: {row.get('pe_ratio')}",
                f"  debt: {row.get('debt')}",
                f"  cash: {row.get('cash')}",
                f"  operating_income: {row.get('operating_income')}",
            ]
        )
    return "\n".join(lines)


def _score_rows_with_gemini(rows: list[dict[str, Any]], api_key: str, models: list[str]) -> dict[str, dict[str, Any]]:
    # Ask Gemini to rate the qualitative metrics.
    if not rows:
        return {}

    prompt = _gemini_prompt_for_rows(rows)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.15},
    }
    errors: list[str] = []
    max_attempts = 4
    target_tickers = {str(r.get("ticker", "")).upper() for r in rows if r.get("ticker")}

    for model in models:
        for attempt in range(1, max_attempts + 1):
            req = urlrequest.Request(
                url=GEMINI_API_URL_TEMPLATE.format(model=model, key=api_key),
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlrequest.urlopen(req, timeout=35) as response:
                    body = response.read().decode("utf-8")
                parsed = json.loads(body)
                text_parts = (
                    parsed.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                text = "".join(part.get("text", "") for part in text_parts if isinstance(part, dict)).strip()
                if not text:
                    raise RuntimeError("Gemini response did not include text content.")

                obj = _extract_json_object(text)
                entries = obj.get("scores")
                if not isinstance(entries, list):
                    raise RuntimeError("Gemini response JSON missing 'scores' array.")

                now_utc = datetime.now(UTC).replace(microsecond=0).isoformat()
                scored_map: dict[str, dict[str, Any]] = {}
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    ticker = str(entry.get("ticker") or "").strip().upper()
                    if not ticker or ticker not in target_tickers:
                        continue
                    scored = _qualitative_default_map()
                    for key_name in QUALITATIVE_KEYS:
                        scored[key_name] = _normalize_points_bucket(entry.get(key_name))
                    scored["qualitative_summary"] = str(entry.get("qualitative_summary") or "").strip()
                    scored["qualitative_model"] = model
                    scored["qualitative_scored_at_utc"] = now_utc
                    scored_map[ticker] = scored

                if scored_map:
                    return scored_map
                raise RuntimeError("Gemini response did not include any valid ticker scores.")
            except urlerror.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                errors.append(f"{model} attempt {attempt}: HTTP {exc.code}")
                if exc.code in (429, 503) and attempt < max_attempts:
                    # Back off when Gemini is busy or rate-limited.
                    time.sleep(1.25 * (2 ** (attempt - 1)))
                    continue
                if exc.code == 404:
                    # Try next model candidate.
                    break
                if attempt < max_attempts:
                    time.sleep(1.0 * (2 ** (attempt - 1)))
                    continue
                errors.append(f"{model} detail: {detail[:280]}")
            except urlerror.URLError as exc:
                errors.append(f"{model} attempt {attempt}: URL error {exc.reason}")
                if attempt < max_attempts:
                    time.sleep(1.0 * (2 ** (attempt - 1)))
                    continue
            except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
                errors.append(f"{model} attempt {attempt}: {exc}")
                if attempt < max_attempts:
                    time.sleep(0.8 * (2 ** (attempt - 1)))
                    continue
                break
        # model loop continues to next candidate

    joined = "; ".join(errors[-6:]) if errors else "unknown failure"
    raise RuntimeError(f"Gemini qualitative scoring failed after retries: {joined}")


def _extract_date_key(path: Path) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else ""


def _latest_file(directory: Path, pattern: str) -> Path:
    files = list(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files found for pattern: {directory / pattern}")
    return max(files, key=_extract_date_key)


def _latest_simfin_snapshot_path() -> Path:
    matches = sorted(RAW_DIR.glob("simfin_financials_20*.csv"), key=_extract_date_key)
    if not matches:
        raise FileNotFoundError(f"No files found for pattern: {RAW_DIR / 'simfin_financials_20*.csv'}")
    full_run = [p for p in matches if p.stem.count("_") == 2]
    return full_run[-1] if full_run else matches[-1]


def _safe_growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous


@lru_cache(maxsize=1)
def _load_simfin_growth_map() -> dict[str, dict[str, float | None]]:
    # Pull simple growth values from cached SimFin files.
    growth_map: dict[str, dict[str, float | None]] = {}

    # Prefer quarterly YoY growth (same fiscal period), then fallback to annual.
    sources = [
        ("us-income-quarterly.csv", True),
        ("us-income-annual.csv", False),
    ]
    required = {"Ticker", "Fiscal Year", "Revenue", "Operating Expenses"}

    for filename, quarterly_mode in sources:
        income_path = SIMFIN_CACHE_DIR / filename
        if not income_path.exists():
            continue
        try:
            df = pd.read_csv(income_path, sep=";", low_memory=False)
        except Exception:
            continue
        if not required.issubset(set(df.columns)):
            continue

        pick_cols = ["Ticker", "Fiscal Year", "Revenue", "Operating Expenses"]
        if "Fiscal Period" in df.columns:
            pick_cols.append("Fiscal Period")
        if "Report Date" in df.columns:
            pick_cols.append("Report Date")

        df = df[pick_cols].copy()
        df["Ticker"] = df["Ticker"].astype(str).str.strip().str.upper()
        df = df[df["Ticker"] != ""]
        df["Fiscal Year"] = pd.to_numeric(df["Fiscal Year"], errors="coerce")
        df["Revenue"] = pd.to_numeric(df["Revenue"], errors="coerce")
        df["Operating Expenses"] = pd.to_numeric(df["Operating Expenses"], errors="coerce")
        if "Fiscal Period" in df.columns:
            df["Fiscal Period"] = df["Fiscal Period"].astype(str).str.strip().str.upper()
        else:
            df["Fiscal Period"] = "FY"
        if "Report Date" in df.columns:
            df["Report Date"] = pd.to_datetime(df["Report Date"], errors="coerce")
        else:
            df["Report Date"] = pd.NaT

        df = df.dropna(subset=["Fiscal Year"])

        if quarterly_mode:
            # YoY in same quarter/period; fallback to previous record if needed.
            df = df.sort_values(["Ticker", "Fiscal Period", "Fiscal Year", "Report Date"])
            df["prev_revenue"] = df.groupby(["Ticker", "Fiscal Period"])["Revenue"].shift(1)
            df["prev_opex"] = df.groupby(["Ticker", "Fiscal Period"])["Operating Expenses"].shift(1)
            df = df.sort_values(["Ticker", "Report Date", "Fiscal Year"])
            df["prev_revenue_any"] = df.groupby("Ticker")["Revenue"].shift(1)
            df["prev_opex_any"] = df.groupby("Ticker")["Operating Expenses"].shift(1)
            df["prev_revenue"] = df["prev_revenue"].fillna(df["prev_revenue_any"])
            df["prev_opex"] = df["prev_opex"].fillna(df["prev_opex_any"])
        else:
            df = df.sort_values(["Ticker", "Fiscal Year"])
            df["prev_revenue"] = df.groupby("Ticker")["Revenue"].shift(1)
            df["prev_opex"] = df.groupby("Ticker")["Operating Expenses"].shift(1)
            df = df.sort_values(["Ticker", "Report Date", "Fiscal Year"])

        latest = df.groupby("Ticker", as_index=False).tail(1)
        for _, rec in latest.iterrows():
            ticker = str(rec.get("Ticker", "")).strip().upper()
            if not ticker or ticker in growth_map:
                continue
            revenue = _to_float(str(rec.get("Revenue"))) if pd.notna(rec.get("Revenue")) else None
            prev_revenue = _to_float(str(rec.get("prev_revenue"))) if pd.notna(rec.get("prev_revenue")) else None
            opex = _to_float(str(rec.get("Operating Expenses"))) if pd.notna(rec.get("Operating Expenses")) else None
            prev_opex = _to_float(str(rec.get("prev_opex"))) if pd.notna(rec.get("prev_opex")) else None
            growth_map[ticker] = {
                "revenue_growth_pct": _safe_growth(revenue, prev_revenue),
                "opex_growth_pct": _safe_growth(opex, prev_opex),
            }

    return growth_map


def _to_float(value: str | None) -> float | None:
    # Clean up numeric CSV values before scoring.
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        numeric = float(value)
    except ValueError:
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _sanitize_debt(value: float | None) -> float | None:
    if value is None:
        return None
    # Debt cannot be negative in this rubric; use magnitude.
    return abs(value)


def _resolve_total_debt(
    total_debt: float | None,
    short_term_debt: float | None = None,
    long_term_debt: float | None = None,
) -> tuple[float | None, bool]:
    # SimFin can show debt signs differently, so normalize it here.
    corrected = False
    if total_debt is not None and total_debt >= 0:
        return total_debt, corrected

    short_clean = _sanitize_debt(short_term_debt)
    long_clean = _sanitize_debt(long_term_debt)
    if short_clean is not None or long_clean is not None:
        corrected = (
            (total_debt is not None and total_debt < 0)
            or (short_term_debt is not None and short_term_debt < 0)
            or (long_term_debt is not None and long_term_debt < 0)
        )
        return (short_clean or 0.0) + (long_clean or 0.0), corrected

    if total_debt is not None:
        corrected = total_debt < 0
        return _sanitize_debt(total_debt), corrected
    return None, corrected


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


def _to_percent(value: float | None) -> float | None:
    if value is None:
        return None
    # Accept either decimal form (0.18) or percent form (18.0).
    return value * 100 if abs(value) <= 1 else value


def _points_cash_vs_debt(cash: float | None, debt: float | None) -> int | None:
    # Score each stock based on the threshold rules.
    if cash is None or debt is None:
        return 0
    if debt <= 0:
        return 10 if cash >= 0 else 0
    ratio = cash / debt
    if ratio >= 2:
        return 10
    if ratio >= 1:
        return 5
    return 0


def _points_revenue_growth(revenue_growth_pct: float | None) -> int | None:
    pct = _to_percent(revenue_growth_pct)
    if pct is None:
        return 0
    if pct >= 20:
        return 10
    if pct >= 10:
        return 5
    return 0


def _points_operating_margin(operating_income: float | None, revenue: float | None) -> int | None:
    if operating_income is None or revenue in (None, 0):
        return 0
    margin_pct = (operating_income / revenue) * 100
    if margin_pct >= 25:
        return 10
    if margin_pct >= 10:
        return 5
    return 0


def _points_short_interest(short_interest_pct: float | None) -> int | None:
    pct = _to_percent(short_interest_pct)
    if pct is None:
        return 0
    if pct < 5:
        return 10
    if pct < 10:
        return 5
    return 0


def _points_institutional_ownership(inst_own_pct: float | None) -> int | None:
    pct = _to_percent(inst_own_pct)
    if pct is None:
        return 0
    if pct >= 60:
        return 10
    if pct >= 30:
        return 5
    return 0


def _points_scalability(revenue_growth_pct: float | None, opex_growth_pct: float | None) -> int | None:
    rev = _to_percent(revenue_growth_pct)
    opex = _to_percent(opex_growth_pct)
    if rev is None or opex is None:
        return 0
    if rev > opex + 2:
        return 10
    if abs(rev - opex) <= 2:
        return 5
    return 0


def _points_share_vs_sp500(stock_return_5y_pct: float | None, sp500_return_5y_pct: float | None) -> int | None:
    stock = _to_percent(stock_return_5y_pct)
    spx = _to_percent(sp500_return_5y_pct)
    if stock is None or spx is None:
        return 0
    if stock > spx:
        return 10
    if stock >= spx - 20:
        return 5
    return 0


def _load_sector_map() -> tuple[dict[str, str], Path]:
    # Add sector labels from the S&P 500 snapshot.
    sp500_file = _latest_file(RAW_DIR, "sp500_constituents_*.csv")
    mapping: dict[str, str] = {}
    with sp500_file.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if ticker:
                mapping[ticker] = (row.get("gics_sector") or "N/A").strip() or "N/A"
    return mapping, sp500_file


def _first_float(row: dict[str, str], keys: list[str]) -> float | None:
    for key in keys:
        value = _to_float(row.get(key))
        if value is not None:
            return value
    return None


def _load_rows_from_simfin_snapshot(sector_map: dict[str, str]) -> tuple[list[dict[str, Any]], Path]:
    # Load the newest raw SimFin snapshot for the API.
    simfin_file = _latest_simfin_snapshot_path()
    growth_map = _load_simfin_growth_map()
    rows: list[dict[str, Any]] = []
    with simfin_file.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            revenue = _to_float(row.get("revenue"))
            pe_ratio = _to_float(row.get("pe_simple"))
            total_debt_raw = _to_float(row.get("total_debt_simple"))
            short_debt_raw = _to_float(row.get("short_term_debt"))
            long_debt_raw = _to_float(row.get("long_term_debt"))
            debt, debt_sign_corrected = _resolve_total_debt(
                total_debt_raw,
                short_term_debt=short_debt_raw,
                long_term_debt=long_debt_raw,
            )
            cash = _to_float(row.get("cash_and_equivalents"))
            operating_income = _to_float(row.get("operating_income"))

            derived = growth_map.get(ticker, {})
            revenue_growth_pct = _first_float(
                row,
                [
                    "revenue_growth_pct",
                    "revenueGrowthPct",
                    "revenueGrowth",
                ],
            )
            opex_growth_pct = _first_float(
                row,
                [
                    "opex_growth_pct",
                    "operatingExpensesGrowthPct",
                    "opexGrowth",
                ],
            )
            if revenue_growth_pct is None:
                revenue_growth_pct = derived.get("revenue_growth_pct")
            if opex_growth_pct is None:
                opex_growth_pct = derived.get("opex_growth_pct")

            rows.append(
                {
                    "ticker": ticker,
                    "company_name": (row.get("company_name") or "").strip() or ticker,
                    "sector": sector_map.get(ticker, "N/A"),
                    "report_date": (row.get("report_date") or "").strip() or None,
                    "publish_date": (row.get("publish_date") or "").strip() or None,
                    "price_date": (row.get("price_date") or "").strip() or None,
                    "fetched_at_utc": (row.get("fetched_at_utc") or "").strip() or None,
                    "revenue": revenue,
                    "pe_ratio": pe_ratio,
                    "debt": debt,
                    "debt_sign_corrected": debt_sign_corrected,
                    "cash": cash,
                    "operating_income": operating_income,
                    "revenue_growth_pct": revenue_growth_pct,
                    "opex_growth_pct": opex_growth_pct,
                    "short_interest_pct": _first_float(row, ["short_interest_pct", "shortInterestPct"]),
                    "institutional_ownership_pct": _first_float(
                        row, ["institutional_ownership_pct", "institutionalOwnershipPct"]
                    ),
                    "stock_return_5y_pct": _first_float(row, ["stock_return_5y_pct", "five_year_return_pct"]),
                    "sp500_return_5y_pct": _first_float(row, ["sp500_return_5y_pct"]),
                    "revenue_display": _fmt_compact_usd(revenue),
                    "pe_display": _fmt_number(pe_ratio, 1),
                    "debt_display": _fmt_compact_usd(debt),
                }
            )
    if not rows:
        raise ValueError(f"No usable rows found in {simfin_file.name}")
    return rows, simfin_file


def _load_rows_from_processed_eligible(sector_map: dict[str, str]) -> tuple[list[dict[str, Any]], Path]:
    # Fallback if only the filtered processed file is available.
    eligible_file = _latest_file(PROCESSED_DIR, "eligible_stocks_*.csv")
    growth_map = _load_simfin_growth_map()
    rows: list[dict[str, Any]] = []
    with eligible_file.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            revenue = _to_float(row.get("revenue"))
            pe_ratio = _to_float(row.get("pe_simple"))
            total_debt_raw = _to_float(row.get("total_debt_simple"))
            short_debt_raw = _to_float(row.get("short_term_debt"))
            long_debt_raw = _to_float(row.get("long_term_debt"))
            debt, debt_sign_corrected = _resolve_total_debt(
                total_debt_raw,
                short_term_debt=short_debt_raw,
                long_term_debt=long_debt_raw,
            )
            cash = _to_float(row.get("cash_and_equivalents"))
            operating_income = _to_float(row.get("operating_income"))
            derived = growth_map.get(ticker, {})
            revenue_growth_pct = _first_float(row, ["revenue_growth_pct", "revenueGrowthPct"])
            opex_growth_pct = _first_float(row, ["opex_growth_pct", "operatingExpensesGrowthPct"])
            if revenue_growth_pct is None:
                revenue_growth_pct = derived.get("revenue_growth_pct")
            if opex_growth_pct is None:
                opex_growth_pct = derived.get("opex_growth_pct")

            rows.append(
                {
                    "ticker": ticker,
                    "company_name": (row.get("company_name") or "").strip() or ticker,
                    "sector": sector_map.get(ticker, "N/A"),
                    "report_date": (row.get("report_date") or "").strip() or None,
                    "publish_date": (row.get("publish_date") or "").strip() or None,
                    "price_date": (row.get("price_date") or "").strip() or None,
                    "fetched_at_utc": (row.get("fetched_at_utc") or "").strip() or None,
                    "revenue": revenue,
                    "pe_ratio": pe_ratio,
                    "debt": debt,
                    "debt_sign_corrected": debt_sign_corrected,
                    "cash": cash,
                    "operating_income": operating_income,
                    "revenue_growth_pct": revenue_growth_pct,
                    "opex_growth_pct": opex_growth_pct,
                    "short_interest_pct": _first_float(row, ["short_interest_pct", "shortInterestPct"]),
                    "institutional_ownership_pct": _first_float(
                        row, ["institutional_ownership_pct", "institutionalOwnershipPct"]
                    ),
                    "stock_return_5y_pct": _first_float(row, ["stock_return_5y_pct", "five_year_return_pct"]),
                    "sp500_return_5y_pct": _first_float(row, ["sp500_return_5y_pct"]),
                    "revenue_display": _fmt_compact_usd(revenue),
                    "pe_display": _fmt_number(pe_ratio, 1),
                    "debt_display": _fmt_compact_usd(debt),
                }
            )
    return rows, eligible_file


def _load_eligible_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Build the ranked rows that get sent to the frontend.
    sector_map, sp500_file = _load_sector_map()

    source_kind = "simfin_raw"
    try:
        rows, source_file = _load_rows_from_simfin_snapshot(sector_map)
    except (FileNotFoundError, ValueError):
        rows, source_file = _load_rows_from_processed_eligible(sector_map)
        source_kind = "eligible_processed"
    qualitative_map, qualitative_file = _load_qualitative_score_map()
    qual_metric_keys = list(QUALITATIVE_KEYS)

    # Combine hard and soft scores into one total.
    for row in rows:
        cached_qual = qualitative_map.get((row.get("ticker") or "").upper(), _qualitative_default_map())
        metric_points: dict[str, int | None] = {
            "cash_vs_debt_points": _points_cash_vs_debt(row.get("cash"), row.get("debt")),
            "revenue_growth_points": _points_revenue_growth(row.get("revenue_growth_pct")),
            "operating_margin_points": _points_operating_margin(
                row.get("operating_income"), row.get("revenue")
            ),
            "short_interest_points": _points_short_interest(row.get("short_interest_pct")),
            "institutional_ownership_points": _points_institutional_ownership(
                row.get("institutional_ownership_pct")
            ),
            "scalability_points": _points_scalability(
                row.get("revenue_growth_pct"), row.get("opex_growth_pct")
            ),
            "share_vs_sp500_points": _points_share_vs_sp500(
                row.get("stock_return_5y_pct"), row.get("sp500_return_5y_pct")
            ),
            "moat_points": cached_qual.get("moat_points"),
            "leadership_points": cached_qual.get("leadership_points"),
            "secular_trend_points": cached_qual.get("secular_trend_points"),
            "culture_mission_points": cached_qual.get("culture_mission_points"),
            "talent_quality_points": cached_qual.get("talent_quality_points"),
            "recession_resilience_points": cached_qual.get("recession_resilience_points"),
        }
        row.update(metric_points)
        row["qualitative_summary"] = cached_qual.get("qualitative_summary", "")
        row["qualitative_model"] = cached_qual.get("qualitative_model", "")
        row["qualitative_scored_at_utc"] = cached_qual.get("qualitative_scored_at_utc", "")

        quant_points = sum((row[k] or 0) for k in QUANTITATIVE_KEYS)
        qual_points = sum((row[k] or 0) for k in qual_metric_keys)
        total_points = quant_points + qual_points

        row["revenue_score_display"] = str(row["revenue_growth_points"]) if row["revenue_growth_points"] is not None else "N/A"
        row["pe_score_display"] = str(row["short_interest_points"]) if row["short_interest_points"] is not None else "N/A"
        row["debt_score_display"] = str(row["cash_vs_debt_points"]) if row["cash_vs_debt_points"] is not None else "N/A"

        row["quant_score"] = float(quant_points)
        row["quant_score_display"] = f"{quant_points} / 70"
        row["total_score"] = float(total_points)
        row["total_score_display"] = f"{total_points} / 130"
        row["qual_score_display"] = f"{qual_points} / 60"

    scored_rows = [r for r in rows if r["total_score"] is not None]
    # Highest total score gets the best rank.
    scored_rows.sort(
        key=lambda r: (
            r["total_score"],
            r["quant_score"],
            r["ticker"],
        ),
        reverse=True,
    )
    for idx, row in enumerate(scored_rows, start=1):
        row["quant_rank"] = idx
    for row in rows:
        if "quant_rank" not in row:
            row["quant_rank"] = None

    rows.sort(
        key=lambda r: (
            r["quant_rank"] is None,
            r["quant_rank"] if r["quant_rank"] is not None else 10**9,
            r["ticker"],
        )
    )

    filled_rows = [r for r in rows if r["revenue"] is not None and r["debt"] is not None and r["cash"] is not None]
    debt_corrected_rows = [r for r in rows if r.get("debt_sign_corrected")]
    qualitative_scored_rows = [r for r in rows if _is_fully_qual_scored(r)]
    # Coverage is measured against the full S&P 500 universe, not only eligible rows.
    coverage_denominator = len(sector_map)
    coverage_pct = (len(filled_rows) / coverage_denominator * 100) if coverage_denominator else 0.0

    snapshot = {
        "data_source": source_kind,
        "data_file": source_file.name,
        "sp500_file": sp500_file.name,
        "universe_count": len(sector_map),
        "eligible_count": len(rows),
        "complete_required_fields_count": len(filled_rows),
        "quant_scored_count": len(scored_rows),
        "qual_scored_count": len(qualitative_scored_rows),
        "score_model": "13-metric-130-points",
        "quant_points_max": 70,
        "qual_points_max": 60,
        "total_points_max": 130,
        "debt_corrected_count": len(debt_corrected_rows),
        "qualitative_file": qualitative_file.name if qualitative_file else None,
        "coverage_pct": round(coverage_pct, 1),
    }
    return rows, snapshot


@app.post("/qualitative/score")
def qualitative_score(request: QualitativeScoreRequest) -> dict[str, Any]:
    # API route that runs Gemini scoring in small batches.
    try:
        rows, _ = _load_eligible_rows()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    row_by_ticker = {str(r.get("ticker", "")).upper(): r for r in rows if r.get("ticker")}
    if request.tickers:
        targets = [t.strip().upper() for t in request.tickers if t.strip()]
        targets = [t for t in targets if t in row_by_ticker]
    else:
        ranked = [r for r in rows if r.get("ticker")]
        targets = [str(r["ticker"]).upper() for r in ranked[: request.limit]]

    if not targets:
        return {
            "requested": 0,
            "scored": 0,
            "skipped": 0,
            "failed": [],
            "remaining": 0,
            "done": True,
            "qualitative_file": None,
            "snapshot": _load_eligible_rows()[1],
        }

    score_map, old_file = _load_qualitative_score_map()
    scored = 0
    skipped = 0
    failed: list[dict[str, str]] = []

    pending = []
    for ticker in targets:
        # Skip stocks that already have saved soft scores.
        existing = score_map.get(ticker, {})
        already_scored = _is_fully_qual_scored(existing)
        if already_scored and not request.overwrite:
            skipped += 1
            continue
        pending.append(ticker)

    if pending:
        try:
            api_key = _gemini_api_key()
            model_candidates = _resolve_gemini_model_candidates(api_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        api_key = ""
        model_candidates = []

    start_monotonic = time.monotonic()
    processed = skipped

    index = 0
    while index < len(pending):
        if time.monotonic() - start_monotonic >= request.max_seconds:
            break

        batch_tickers = pending[index : index + request.batch_size]
        batch_rows = [row_by_ticker[t] for t in batch_tickers if t in row_by_ticker]

        try:
            batch_scored = _score_rows_with_gemini(
                batch_rows,
                api_key=api_key,
                models=model_candidates,
            )
        except RuntimeError as exc:
            for ticker in batch_tickers:
                failed.append({"ticker": ticker, "error": str(exc)})
                processed += 1
            index += request.batch_size
            continue

        for ticker in batch_tickers:
            scored_payload = batch_scored.get(ticker)
            if scored_payload:
                score_map[ticker] = scored_payload
                scored += 1
            else:
                failed.append(
                    {
                        "ticker": ticker,
                        "error": "Ticker missing from Gemini batch response.",
                    }
                )
            processed += 1

        index += request.batch_size

    out_file = old_file
    if scored > 0:
        out_file = _save_qualitative_score_map(score_map)

    remaining = 0
    for ticker in targets:
        existing = score_map.get(ticker, {})
        is_scored = _is_fully_qual_scored(existing)
        if not is_scored:
            remaining += 1

    _, snapshot = _load_eligible_rows()
    return {
        "requested": len(targets),
        "processed": processed,
        "scored": scored,
        "skipped": skipped,
        "failed": failed,
        "remaining": remaining,
        "done": remaining == 0,
        "qualitative_file": out_file.name if out_file else None,
        "snapshot": snapshot,
    }


@app.get("/health")
def health() -> dict[str, str]:
    # Tiny endpoint for checking if the backend is alive.
    return {"status": "ok"}


@app.get("/stocks/eligible")
def eligible_stocks(limit: int = Query(default=500, ge=1, le=2000)) -> dict[str, Any]:
    # Send ranked results to the frontend.
    try:
        rows, snapshot = _load_eligible_rows()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"snapshot": snapshot, "items": rows[:limit]}


@app.get("/stocks/eligible/{ticker}")
def eligible_stock_detail(ticker: str) -> dict[str, Any]:
    # Return one stock with its score breakdown.
    target = ticker.strip().upper()
    try:
        rows, snapshot = _load_eligible_rows()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    for row in rows:
        if row["ticker"] == target:
            return {"snapshot": snapshot, "item": row}

    raise HTTPException(status_code=404, detail=f"Ticker not found in eligible list: {target}")
