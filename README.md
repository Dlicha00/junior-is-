# Stock ranking web app

Initial project setup for a stock ranking pipeline and web API.

## Setup (Python + FastAPI)

1. Create a virtual environment:

```powershell
python -m venv .venv
```

2. Activate it (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Run the API:

```powershell
uvicorn src.main:app --reload
```

5. Verify health endpoint:

- Open `http://127.0.0.1:8000/health`
- Expected response: `{"status":"ok"}`

## Feature Calendar

| **Feature/Task** | **Due date** | **Notes** |
| --- | --- | --- |
| Initial Setup | Feb 13, 2026 | Python env; install pandas + web framework |
| Stock List Download | Feb 16, 2026 | Pull current S&P 500 tickers |
| Financial Data Ingestion | Feb 20, 2026 | Download raw metrics (P/E, revenue, etc.) |
| S&P Standards Filter | Feb 23, 2026 | Apply official S&P eligibility rules |
| Data Storage | Feb 26, 2026 | Structure pandas DataFrame for all metrics |
| Numerical Scoring | Mar 1, 2026 | Convert ratios to 1–10 score |
| AI Qualitative Analysis | Mar 4, 2026 | Use AI API on headlines for "soft" metrics |
| Ranking Engine | Mar 7, 2026 | Sum 13 metrics and sort descending |
| Data API | Mar 10, 2026 | Backend endpoint for ranked data |
| Web Dashboard | Mar 13, 2026 | Main table of top-ranked stocks |
| Detailed View | Mar 15, 2026 | Per-stock breakdown of scores |
| Stretch Goal: Live Search Bar | if time permits | Instant ticker search |
| Stretch Goal: Watchlist | if time permits | Save favorite stocks |

## Stock List Download (Wikipedia)

Download the current S&P 500 constituents and save a dated CSV snapshot:

```powershell
.\.venv\Scripts\python.exe .\scripts\download_sp500.py
```

Output example:

- `data/raw/sp500_constituents_2026-02-24.csv`

## Financial Data Ingestion (SimFin API)

This step downloads raw financial data (for example, `revenue`, `net_income`,
debt and balance sheet fields) for the S&P 500 tickers using SimFin bulk
datasets, then computes simple helper metrics like `pe_simple` from the latest
price and EPS.

1. Set your SimFin API key:

```powershell
$env:SIMFIN_API_KEY="your_api_key_here"
```

2. Run a small test batch first:

```powershell
.\.venv\Scripts\python.exe .\scripts\download_financials_simfin.py --max-tickers 5
```

3. Run the full S&P 500 batch:

```powershell
.\.venv\Scripts\python.exe .\scripts\download_financials_simfin.py
```

Outputs:

- `data/raw/simfin_financials_YYYY-MM-DD.csv`
