from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_sources.sp500 import save_sp500_snapshot


def main() -> None:
    output_path = save_sp500_snapshot()
    print(f"Saved S&P 500 constituents snapshot to: {output_path}")


if __name__ == "__main__":
    main()
