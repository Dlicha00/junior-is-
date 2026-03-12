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

| **Feature/Task** | **Target Date** | **Status** | **Notes** |
| --- | --- | --- | --- |
| Initial Setup | Feb 13, 2026 | Done | Python env + FastAPI setup in place |
| Stock List Download | Feb 16, 2026 | Done | `scripts/download_sp500.py` writes dated raw snapshot |
| Financial Data Ingestion (SimFin) | Feb 20, 2026 | Done | `scripts/download_financials_simfin.py` writes dated financial snapshot |
| S&P Standards Filter | Feb 23, 2026 | Done | `scripts/filter_sp500_eligibility.py` outputs eligible + excluded files |
| Data Storage (metrics master) | Feb 26, 2026 | Done | `scripts/build_metrics_master.py` writes `metrics_master_YYYY-MM-DD.csv` |
| Data API (`/stocks/eligible`) | Mar 10, 2026 | Done | Endpoints: `/health`, `/stocks/eligible`, `/stocks/eligible/{ticker}` |
| Web Dashboard | Mar 13, 2026 | Done | `demo/` frontend loads eligible stocks and renders table + detail panel |
| Detailed View | Mar 15, 2026 | Done | Row selection renders metric detail card in right panel |
| Numerical Scoring | Mar 1, 2026 | Not started | 1-10 scoring pipeline is not in current code |
| AI Qualitative Analysis | Mar 4, 2026 | Not started | No AI-driven qualitative metrics in current API/pipeline |
| Ranking Engine | Mar 7, 2026 | Not started | No combined rank output endpoint yet |
| Stretch: Live Search Bar | If time permits | Not started | Dashboard has pagination but no search input |
| Stretch: Watchlist | If time permits | Not started | No persistence/watchlist flow yet |

## Current Issues

- No automated tests yet for pipeline scripts, data transforms, or API endpoints.
- API currently serves eligibility and base metric fields, but not final ranked scores.
- Frontend requires backend running locally and only shows a generic availability error when API is down.

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

## S&P Standards Filter

Filter the raw SimFin snapshot into:
- eligible stocks for scoring
- excluded stocks with `exclusion_reason`

Run:

```powershell
.\.venv\Scripts\python.exe .\scripts\filter_sp500_eligibility.py
```

Outputs:

- `data/processed/eligible_stocks_YYYY-MM-DD.csv`
- `data/processed/excluded_stocks_YYYY-MM-DD.csv`

## Data Storage

Build the canonical processed DataFrame for downstream scoring:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_metrics_master.py
```

Output:

- `data/processed/metrics_master_YYYY-MM-DD.csv`
