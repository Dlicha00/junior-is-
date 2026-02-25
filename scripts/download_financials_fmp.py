from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipelines.financial_ingestion import save_fmp_financial_metrics_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download raw financial metrics for S&P 500 tickers using FMP."
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="FMP API key (overrides FMP_API_KEY env var).",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=None,
        help="Limit run size for testing (e.g. 5).",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.25,
        help="Delay between tickers to reduce rate-limit pressure.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        metrics_path, failures_path = save_fmp_financial_metrics_snapshot(
            api_key=args.api_key,
            max_tickers=args.max_tickers,
            sleep_seconds=args.sleep_seconds,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Saved FMP financial metrics snapshot to: {metrics_path}")
    if failures_path:
        print(f"Saved failures log to: {failures_path}")


if __name__ == "__main__":
    main()
