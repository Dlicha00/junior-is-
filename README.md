# Web-Based Stock Scoring Engine

## Overview

Web-Based Stock Scoring Engine is a web-based decision-support tool that ranks S&P 500 companies using a 130-point model. The model contains 13 metrics: 7 quantitative metrics from financial and market data, plus 6 qualitative metrics scored with Gemini/LLM assistance.

The project is designed to help users compare companies and inspect why a company ranked where it did. It is not a stock prediction system, investment advice, or a guarantee of investment returns.

## Features

- S&P 500 company data pipeline
- SimFin financial data integration
- Quantitative scoring for financial and market-based metrics
- Gemini/LLM-assisted qualitative scoring
- 130-point total score across 13 metrics
- Ranked API output for scored companies
- Ranking table in the browser demo
- Individual stock score breakdowns
- Browser-based HTML/CSS/JavaScript demo frontend
- API endpoints for ranked results and stock details

## Tech Stack

- Python
- FastAPI
- Uvicorn
- pandas
- SimFin API
- Gemini/LLM API
- HTML/CSS/JavaScript demo frontend

## Installation

1. Clone the repository:

```powershell
git clone <repository-url>
cd junior-is-
```

2. Create a virtual environment:

```powershell
python -m venv .venv
```

3. Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

4. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Environment Variables

Create a local `.env` file from `.env.example` and fill in your real keys:

```powershell
Copy-Item .env.example .env
```

Required variables:

- `SIMFIN_API_KEY`: API key used by the SimFin financial data ingestion script.
- `GEMINI_API_KEY`: API key used by Gemini/LLM qualitative scoring.

Real API keys should only be stored in your local `.env` file or local shell environment. Do not commit real keys or secrets.

## How to Run

Start the FastAPI backend:

```powershell
uvicorn src.main:app --reload
```

Verify the backend is running:

- Health check: `http://127.0.0.1:8000/health`
- Ranked stock output: `http://127.0.0.1:8000/stocks/eligible`
- Individual stock detail: `http://127.0.0.1:8000/stocks/eligible/AAPL`

Open the browser demo:

1. Start the backend with Uvicorn.
2. Open `demo/index.html` in a browser.
3. The demo loads ranked results from the local API and displays a ranking table.
4. Click a stock row to view the individual score breakdown.

## Data Pipeline

Download the current S&P 500 constituents:

```powershell
.\.venv\Scripts\python.exe .\scripts\download_sp500.py
```

Download financial data from SimFin:

```powershell
.\.venv\Scripts\python.exe .\scripts\download_financials_simfin.py
```

Run a smaller SimFin test batch:

```powershell
.\.venv\Scripts\python.exe .\scripts\download_financials_simfin.py --max-tickers 5
```

Filter companies with missing required fields:

```powershell
.\.venv\Scripts\python.exe .\scripts\filter_sp500_eligibility.py
```

Build the canonical metrics master file:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_metrics_master.py
```

Generate qualitative Gemini/LLM scores through the API:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/qualitative/score -ContentType "application/json" -Body "{}"
```

## Project Structure

- `src/main.py`: FastAPI application, ranking output, 130-point scoring, and Gemini qualitative scoring endpoint.
- `src/data_sources/`: S&P 500 data source helpers.
- `src/pipelines/`: data ingestion, filtering, and storage pipeline code.
- `scripts/`: command-line scripts for downloading data and building processed files.
- `demo/index.html`: browser-based frontend for viewing rankings and stock detail breakdowns.
- `demo/app.js`: frontend API calls, ranking table rendering, and stock detail rendering.
- `requirements.txt`: Python runtime dependencies.
- `.env.example`: placeholder environment variables for local API keys.
- `data/raw/`: raw downloaded data snapshots.
- `data/processed/`: processed eligibility, metric, and qualitative score outputs.

## Testing

There are no automated tests yet.

The system has been manually tested by verifying:

- S&P 500 company data collection creates dated raw CSV snapshots.
- Missing value handling excludes companies with incomplete required fields.
- Quantitative score calculation produces component scores for the 7 quantitative metrics.
- Gemini qualitative score generation writes 6 qualitative component scores.
- Total score calculation combines quantitative and qualitative metrics out of 130 points.
- Ranked API output is returned by `/stocks/eligible`.
- Individual stock detail output is returned by `/stocks/eligible/{ticker}`.
- Frontend ranking table displays ranked results.
- Frontend stock detail view displays individual metric breakdowns.

## Limitations

- Metric thresholds are manually selected and have not yet been statistically validated.
- Qualitative scores depend on LLM consistency and the quality of the input data.
- Free or limited data APIs may not always provide the freshest market or financial data.
- The tool is for decision support, not stock prediction, investment advice, or guaranteed investment returns.

## Future Work

- Add automated tests for pipeline scripts, scoring logic, API endpoints, and frontend behavior.
- Validate scores against historical performance.
- Add user-adjustable metric weights.
- Improve data freshness handling and stale-data warnings.
- Add stronger visualizations for score drivers and comparison.
- Refine qualitative prompts and add consistency checks for LLM output.
