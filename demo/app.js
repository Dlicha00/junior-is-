const API_BASE =
  window.location.port === "8000"
    ? "http://127.0.0.1:8001"
    : "http://127.0.0.1:8000";
// UI paging sizes.
const INITIAL_VISIBLE_ROWS = 10;
const SHOW_MORE_STEP = 10;

// Page state.
const state = {
  selectedTicker: null,
  stocks: [],
  visibleCount: INITIAL_VISIBLE_ROWS,
  snapshot: {},
  qualitativeJobStarted: false,
  qualitativeJobRunning: false
};

const emptyState = document.getElementById("emptyState");
const table = document.getElementById("rankingTable");
const tbody = table.querySelector("tbody");
const detailContent = document.getElementById("detailContent");
const detailTemplate = document.getElementById("detailTemplate");
const detailBadge = document.getElementById("detailBadge");
const rowsLoaded = document.getElementById("rowsLoaded");
const universeCount = document.getElementById("universeCount");
const coveragePct = document.getElementById("coveragePct");
const eligibleCount = document.getElementById("eligibleCount");
const showMoreBtn = document.getElementById("showMoreBtn");
const llmStatus = document.getElementById("llmStatus");

// Toggle loading/empty view.
function showLoadingState(title, copy) {
  emptyState.querySelector(".empty-title").textContent = title;
  emptyState.querySelector(".empty-copy").textContent = copy;
  emptyState.hidden = false;
  table.hidden = true;
  showMoreBtn.hidden = true;
}

// Top stats summary.
function updateSummary(snapshot) {
  universeCount.textContent = String(snapshot.universe_count ?? "-");
  coveragePct.textContent = snapshot.coverage_pct != null ? `${snapshot.coverage_pct}%` : "-";
  eligibleCount.textContent = String(snapshot.quant_scored_count ?? snapshot.eligible_count ?? 0);
  const shown = Math.min(state.visibleCount, state.stocks.length);
  rowsLoaded.textContent = `${shown} / ${state.stocks.length} shown`;
  if (!state.qualitativeJobRunning) {
    const qualDone = snapshot.qual_scored_count ?? 0;
    const qualDenom = snapshot.eligible_count ?? 0;
    llmStatus.textContent = `Soft metrics: ${qualDone} / ${qualDenom} scored`;
  }
}

// Fetch eligible stocks.
async function loadStocksFromApi() {
  const response = await fetch(`${API_BASE}/stocks/eligible?limit=1000`);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json();
}

function applyPayload(payload, options = {}) {
  // Keep the same selected stock after refresh if it still exists.
  const { preserveSelection = true } = options;
  const previousTicker = preserveSelection ? state.selectedTicker : null;
  state.stocks = payload.items ?? [];
  state.snapshot = payload.snapshot ?? {};
  updateSummary(state.snapshot);

  if (state.stocks.length === 0) {
    showLoadingState("No data", "No ranked stocks were returned by the API.");
    detailBadge.textContent = "No selection";
    return false;
  }

  renderTable();
  const selectedTicker = state.stocks.some((s) => s.ticker === previousTicker)
    ? previousTicker
    : state.stocks[0].ticker;
  selectStock(selectedTicker);
  return true;
}

async function refreshRankingsSilently() {
  // Refresh scores without resetting the page.
  const payload = await loadStocksFromApi();
  applyPayload(payload, { preserveSelection: true });
}

async function startAutoGeminiScoring() {
  // Start soft scoring once, then reuse saved results.
  if (state.qualitativeJobStarted || state.qualitativeJobRunning) {
    return;
  }
  state.qualitativeJobStarted = true;

  const qualDone = state.snapshot.qual_scored_count ?? 0;
  const qualDenom = state.snapshot.eligible_count ?? 0;
  const hasSavedQualitative = Boolean(state.snapshot.qualitative_file)
    && qualDenom > 0
    && qualDone >= qualDenom;
  if (hasSavedQualitative) {
    llmStatus.textContent = `Soft metrics: ${qualDone} / ${qualDenom} scored (cached)`;
    return;
  }

  state.qualitativeJobRunning = true;
  llmStatus.textContent = "Auto-running Gemini qualitative scoring...";
  try {
    let rounds = 0;
    const maxRounds = 240;
    let done = false;

    while (!done && rounds < maxRounds) {
      // Score a small batch so the request does not run too long.
      rounds += 1;
      const response = await fetch(`${API_BASE}/qualitative/score`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 2000, overwrite: false, max_seconds: 15, batch_size: 10 })
      });
      if (!response.ok) {
        let detail = `status ${response.status}`;
        try {
          const payload = await response.json();
          if (payload?.detail) detail = payload.detail;
        } catch {
          // Ignore JSON parse failure and keep status detail.
        }
        throw new Error(`Qualitative scoring failed: ${detail}`);
      }

      const payload = await response.json();
      // Show progress while Gemini fills in the soft metrics.
      const snap = payload.snapshot ?? {};
      const qualDone = snap.qual_scored_count ?? 0;
      const qualDenom = snap.eligible_count ?? 0;
      const failedCount = payload.failed?.length ?? 0;
      llmStatus.textContent =
        `Gemini progress: ${qualDone}/${qualDenom} scored (round ${rounds}, +${payload.scored}, remaining ${payload.remaining}, failed ${failedCount})`;

      await refreshRankingsSilently();

      done = Boolean(payload.done);
      if (!done) {
        await new Promise((resolve) => setTimeout(resolve, 300));
      }
    }

    if (!done) {
      llmStatus.textContent = "Auto Gemini run paused after many rounds. It will continue on next refresh.";
    } else {
      const qualDone = state.snapshot.qual_scored_count ?? 0;
      const qualDenom = state.snapshot.eligible_count ?? 0;
      llmStatus.textContent = `Soft metrics: ${qualDone} / ${qualDenom} scored`;
    }
  } catch (error) {
    llmStatus.textContent = `Gemini error: ${error.message}`;
  } finally {
    state.qualitativeJobRunning = false;
  }
}

// Build ranking rows.
function renderTable() {
  // Build the ranking rows shown on the left.
  tbody.innerHTML = "";
  const visibleStocks = state.stocks.slice(0, state.visibleCount);

  for (const stock of visibleStocks) {
    const tr = document.createElement("tr");
    tr.dataset.ticker = stock.ticker;
    tr.tabIndex = 0;
    tr.setAttribute("role", "button");
    tr.setAttribute("aria-label", `Select ${stock.ticker} from ranked list`);
    tr.innerHTML = `
      <td>${stock.quant_rank ?? "-"}</td>
      <td class="ticker-cell">${stock.ticker}</td>
      <td>${stock.total_score_display ?? stock.quant_score_display}</td>
      <td>${stock.sector}</td>
      <td>${stock.revenue_display}</td>
      <td>${stock.pe_display}</td>
      <td>${stock.debt_display}</td>
    `;
    tr.addEventListener("click", () => selectStock(stock.ticker));
    tr.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectStock(stock.ticker);
      }
    });
    tbody.appendChild(tr);
  }

  document.querySelectorAll("#rankingTable tbody tr").forEach((row) => {
    row.classList.toggle("active", row.dataset.ticker === state.selectedTicker);
  });

  emptyState.hidden = true;
  table.hidden = false;
  showMoreBtn.hidden = state.visibleCount >= state.stocks.length;
}

// Build right-side detail panel.
function renderDetail(stock) {
  // Show the selected stock's full scorecard.
  detailContent.classList.remove("is-empty");
  detailContent.innerHTML = "";
  const fragment = detailTemplate.content.cloneNode(true);
  const pts10 = (value) => (value == null ? "N/A" : `${value} / 10`);
  const fmtDate = (value) => {
    if (!value) return "N/A";
    const s = String(value);
    return s.length >= 10 ? s.slice(0, 10) : s;
  };

  fragment.querySelector(".detail-name").textContent = `${stock.ticker} - ${stock.company_name}`;
  fragment.querySelector(".detail-sub").textContent = stock.sector;
  fragment.querySelector(".detail-meta").textContent =
    `Financials: ${fmtDate(stock.report_date)} | Price: ${fmtDate(stock.price_date)}`;
  fragment.querySelector(".detail-rank").textContent = stock.quant_rank ?? "-";
  fragment.querySelector(".detail-total-score").textContent = stock.total_score_display ?? "N/A";
  fragment.querySelector(".detail-quant-score").textContent = stock.quant_score_display ?? "N/A";
  fragment.querySelector(".detail-qual-score").textContent = stock.qual_score_display ?? "0 / 60";
  fragment.querySelector(".detail-revenue").textContent = stock.revenue_display;
  fragment.querySelector(".detail-pe").textContent = stock.pe_display;
  fragment.querySelector(".detail-debt").textContent = stock.debt_display;
  fragment.querySelector(".pts-cash-vs-debt").textContent = pts10(stock.cash_vs_debt_points);
  fragment.querySelector(".pts-revenue-growth").textContent = pts10(stock.revenue_growth_points);
  fragment.querySelector(".pts-operating-margin").textContent = pts10(stock.operating_margin_points);
  fragment.querySelector(".pts-short-interest").textContent = pts10(stock.short_interest_points);
  fragment.querySelector(".pts-inst-ownership").textContent = pts10(stock.institutional_ownership_points);
  fragment.querySelector(".pts-scalability").textContent = pts10(stock.scalability_points);
  fragment.querySelector(".pts-share-vs-sp500").textContent = pts10(stock.share_vs_sp500_points);
  fragment.querySelector(".pts-moat").textContent = pts10(stock.moat_points);
  fragment.querySelector(".pts-leadership").textContent = pts10(stock.leadership_points);
  fragment.querySelector(".pts-secular-trend").textContent = pts10(stock.secular_trend_points);
  fragment.querySelector(".pts-culture").textContent = pts10(stock.culture_mission_points);
  fragment.querySelector(".pts-talent").textContent = pts10(stock.talent_quality_points);
  fragment.querySelector(".pts-recession").textContent = pts10(stock.recession_resilience_points);

  detailContent.appendChild(fragment);
  detailContent.classList.add("flash");
  setTimeout(() => detailContent.classList.remove("flash"), 400);
  detailBadge.textContent = stock.quant_rank != null ? `Rank #${stock.quant_rank}` : "Not scored";
}

// Set active row and detail card.
function selectStock(ticker) {
  state.selectedTicker = ticker;
  const stock = state.stocks.find((s) => s.ticker === ticker);
  if (!stock) return;

  document.querySelectorAll("#rankingTable tbody tr").forEach((row) => {
    row.classList.toggle("active", row.dataset.ticker === ticker);
  });

  renderDetail(stock);
}

// Main data load flow.
async function loadRankings() {
  // Main page load: fetch rankings, then fill missing soft scores.
  showLoadingState("Loading", "Loading quantitative rankings...");

  try {
    const payload = await loadStocksFromApi();
    state.visibleCount = INITIAL_VISIBLE_ROWS;
    const hasData = applyPayload(payload, { preserveSelection: true });
    if (!hasData) {
      return;
    }
    await startAutoGeminiScoring();
  } catch (error) {
    rowsLoaded.textContent = "0 loaded";
    showLoadingState("API unavailable", `Start backend on ${API_BASE}, then refresh.`);
    detailBadge.textContent = "Unavailable";
  }
}

// Load extra rows.
showMoreBtn.addEventListener("click", () => {
  state.visibleCount = Math.min(state.visibleCount + SHOW_MORE_STEP, state.stocks.length);
  renderTable();
  updateSummary(state.snapshot);
});

// Initial render.
loadRankings();
