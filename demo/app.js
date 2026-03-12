const API_BASE =
  window.location.port === "8000"
    ? "http://127.0.0.1:8001"
    : "http://127.0.0.1:8000";
// UI paging sizes.
const INITIAL_VISIBLE_ROWS = 10;
const SHOW_MORE_STEP = 10;

// Page state.
const state = {
  loaded: false,
  selectedTicker: null,
  stocks: [],
  visibleCount: INITIAL_VISIBLE_ROWS,
  snapshot: {}
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
  eligibleCount.textContent = String(snapshot.eligible_count ?? 0);
  const shown = Math.min(state.visibleCount, state.stocks.length);
  rowsLoaded.textContent = `${shown} / ${state.stocks.length} shown`;
}

// Fetch eligible stocks.
async function loadStocksFromApi() {
  const response = await fetch(`${API_BASE}/stocks/eligible?limit=1000`);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json();
}

// Build ranking rows.
function renderTable() {
  tbody.innerHTML = "";
  const visibleStocks = state.stocks.slice(0, state.visibleCount);

  for (const stock of visibleStocks) {
    const tr = document.createElement("tr");
    tr.dataset.ticker = stock.ticker;
    tr.tabIndex = 0;
    tr.setAttribute("role", "button");
    tr.setAttribute("aria-label", `Select ${stock.ticker} from filtered list`);
    tr.innerHTML = `
      <td class="ticker-cell">${stock.ticker}</td>
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
  detailContent.classList.remove("is-empty");
  detailContent.innerHTML = "";
  const fragment = detailTemplate.content.cloneNode(true);

  fragment.querySelector(".detail-name").textContent = `${stock.ticker} - ${stock.company_name}`;
  fragment.querySelector(".detail-sub").textContent = stock.sector;
  fragment.querySelector(".detail-revenue").textContent = stock.revenue_display;
  fragment.querySelector(".detail-pe").textContent = stock.pe_display;
  fragment.querySelector(".detail-debt").textContent = stock.debt_display;
  fragment.querySelector(".detail-name-short").textContent = stock.company_name;

  detailContent.appendChild(fragment);
  detailContent.classList.add("flash");
  setTimeout(() => detailContent.classList.remove("flash"), 400);
  detailBadge.textContent = "Eligible";
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
  showLoadingState("Loading", "Loading filtered stocks...");

  try {
    const payload = await loadStocksFromApi();
    state.stocks = payload.items ?? [];
    state.visibleCount = INITIAL_VISIBLE_ROWS;
    state.loaded = true;
    state.snapshot = payload.snapshot ?? {};
    updateSummary(state.snapshot);

    if (state.stocks.length === 0) {
      showLoadingState("No data", "No eligible stocks were returned by the API.");
      detailBadge.textContent = "No selection";
      return;
    }

    renderTable();
    selectStock(state.selectedTicker ?? state.stocks[0].ticker);
    updateSummary(state.snapshot);
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
