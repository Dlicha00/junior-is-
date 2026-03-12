from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipelines.sp500_filter import save_sp500_filter_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter SimFin S&P 500 snapshot into eligible and excluded stocks."
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default=None,
        help="Optional path to a specific simfin_financials_*.csv input file.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/processed",
        help="Directory for eligible/excluded output files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        eligible_path, excluded_path = save_sp500_filter_outputs(
            input_path=args.input_path,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Saved eligible stocks to: {eligible_path}")
    print(f"Saved excluded stocks to: {excluded_path}")


if __name__ == "__main__":
    main()
