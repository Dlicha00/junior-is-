from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipelines.data_storage import save_metrics_master


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical metrics master DataFrame from eligible stocks."
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default=None,
        help="Optional path to specific eligible_stocks_*.csv file.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/processed",
        help="Directory for metrics_master output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        out_path = save_metrics_master(
            input_path=args.input_path,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Saved metrics master to: {out_path}")


if __name__ == "__main__":
    main()
