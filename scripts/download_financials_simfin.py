from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipelines.financial_ingestion_simfin import save_simfin_financial_metrics_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download raw financial metrics for S&P 500 tickers using SimFin."
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="SimFin API key (overrides SIMFIN_API_KEY env var).",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=None,
        help="Limit output to first N S&P 500 tickers for testing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        out_path = save_simfin_financial_metrics_snapshot(
            api_key=args.api_key,
            max_tickers=args.max_tickers,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Saved SimFin financial metrics snapshot to: {out_path}")


if __name__ == "__main__":
    main()
