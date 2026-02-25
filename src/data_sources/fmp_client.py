from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class FMPClientError(RuntimeError):
    """Raised when the FMP API request fails after retries."""


@dataclass
class FMPClient:
    api_key: str
    base_url: str = "https://financialmodelingprep.com/stable"
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = dict(params or {})
        query["apikey"] = self.api_key
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}?{urlencode(query)}"

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                request = Request(
                    url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "junior-is-stock-ranking/0.1",
                    },
                )
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    payload = response.read().decode("utf-8", errors="replace")
                return json.loads(payload)
            except HTTPError as exc:
                last_error = exc
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body = ""
                # Retry on common rate-limit/transient server errors.
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * attempt)
                    continue
                detail = f": {body}" if body else ""
                raise FMPClientError(f"FMP HTTP error {exc.code} for {path}{detail}") from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * attempt)
                    continue
                raise FMPClientError(f"FMP request failed for {path}: {exc}") from exc

        raise FMPClientError(f"FMP request failed for {path}: {last_error}")

    def fetch_quote(self, symbol: str) -> dict[str, Any]:
        data = self._get_json("quote", params={"symbol": symbol})
        return data[0] if isinstance(data, list) and data else {}

    def fetch_income_statement(self, symbol: str, limit: int = 1) -> dict[str, Any]:
        data = self._get_json("income-statement", params={"symbol": symbol, "limit": limit})
        return data[0] if isinstance(data, list) and data else {}

    def fetch_balance_sheet(self, symbol: str, limit: int = 1) -> dict[str, Any]:
        data = self._get_json(
            "balance-sheet-statement",
            params={"symbol": symbol, "limit": limit},
        )
        return data[0] if isinstance(data, list) and data else {}

    def fetch_ratios_ttm(self, symbol: str) -> dict[str, Any]:
        data = self._get_json("ratios-ttm", params={"symbol": symbol})
        return data[0] if isinstance(data, list) and data else {}

    def fetch_core_metrics(self, symbol: str) -> dict[str, Any]:
        """Fetch a small, raw metrics bundle for a single ticker.

        This intentionally returns mostly provider field names to keep this step
        close to the raw source. Normalization/scoring happen later.
        """
        quote = self.fetch_quote(symbol)
        income = self.fetch_income_statement(symbol, limit=1)
        balance = self.fetch_balance_sheet(symbol, limit=1)
        ratios = self.fetch_ratios_ttm(symbol)

        return {
            "ticker": symbol,
            "source": "fmp",
            "quote_symbol": quote.get("symbol"),
            "quote_name": quote.get("name"),
            "price": quote.get("price"),
            "marketCap": quote.get("marketCap"),
            "pe": quote.get("pe"),
            "eps": quote.get("eps"),
            "income_statement_date": income.get("date"),
            "income_statement_period": income.get("period"),
            "revenue": income.get("revenue"),
            "grossProfit": income.get("grossProfit"),
            "operatingIncome": income.get("operatingIncome"),
            "netIncome": income.get("netIncome"),
            "ebitda": income.get("ebitda"),
            "balance_sheet_date": balance.get("date"),
            "totalAssets": balance.get("totalAssets"),
            "totalLiabilities": balance.get("totalLiabilities"),
            "totalDebt": balance.get("totalDebt"),
            "cashAndCashEquivalents": balance.get("cashAndCashEquivalents"),
            "currentRatioTTM": ratios.get("currentRatioTTM"),
            "debtEquityRatioTTM": ratios.get("debtEquityRatioTTM"),
            "netProfitMarginTTM": ratios.get("netProfitMarginTTM"),
            "returnOnEquityTTM": ratios.get("returnOnEquityTTM"),
            "priceToSalesRatioTTM": ratios.get("priceToSalesRatioTTM"),
            "priceToBookRatioTTM": ratios.get("priceToBookRatioTTM"),
            "peRatioTTM": ratios.get("peRatioTTM"),
        }
