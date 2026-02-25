const stocks = [
  {
    rank: 1,
    ticker: "MSFT",
    name: "Microsoft",
    total: 92,
    quality: 9.6,
    value: 7.1,
    trend: 9.1,
    ai: 8.8,
    revenue: "$245B",
    pe: "34.2",
    debt: "$47B",
    sector: "Software",
    headline: "AI product momentum remains strong while enterprise demand stays resilient."
  },
  {
    rank: 2,
    ticker: "NVDA",
    name: "NVIDIA",
    total: 90,
    quality: 9.8,
    value: 5.4,
    trend: 9.9,
    ai: 9.5,
    revenue: "$130B",
    pe: "56.0",
    debt: "$11B",
    sector: "Semiconductors",
    headline: "Data-center expansion and AI infrastructure spending continue to support growth."
  },
  {
    rank: 3,
    ticker: "AVGO",
    name: "Broadcom",
    total: 87,
    quality: 9.1,
    value: 6.3,
    trend: 8.7,
    ai: 8.2,
    revenue: "$51B",
    pe: "31.8",
    debt: "$74B",
    sector: "Semiconductors",
    headline: "Strong AI connectivity demand offsets softness in select legacy segments."
  },
  {
    rank: 4,
    ticker: "AAPL",
    name: "Apple",
    total: 84,
    quality: 8.9,
    value: 6.0,
    trend: 7.8,
    ai: 7.4,
    revenue: "$391B",
    pe: "29.1",
    debt: "$106B",
    sector: "Consumer Tech",
    headline: "Services growth remains a stabilizer while hardware cycle sentiment is mixed."
  },
  {
    rank: 5,
    ticker: "GOOGL",
    name: "Alphabet",
    total: 83,
    quality: 8.7,
    value: 7.4,
    trend: 7.3,
    ai: 8.4,
    revenue: "$350B",
    pe: "25.6",
    debt: "$27B",
    sector: "Internet Platforms",
    headline: "Cloud and AI monetization support positive outlook despite competitive pressure."
  },
  {
    rank: 6,
    ticker: "ABT",
    name: "Abbott Laboratories",
    total: 80,
    quality: 8.4,
    value: 7.8,
    trend: 6.8,
    ai: 7.0,
    revenue: "$42B",
    pe: "15.0",
    debt: "$14B",
    sector: "Health Care",
    headline: "Defensive cash flow profile and diversified product mix support score stability."
  }
];

const stagePresets = {
  raw: { universe: 503, coverage: "87%", eligible: 503, top: "N/A", loaded: "0 loaded" },
  filtered: { universe: 503, coverage: "87%", eligible: 441, top: "N/A", loaded: "0 loaded" },
  ranked: { universe: 503, coverage: "87%", eligible: 441, top: "MSFT", loaded: `${stocks.length} loaded` }
};

const state = {
  loaded: false,
  selectedTicker: null,
  showBreakdown: false,
  stage: "raw"
};

const loadBtn = document.getElementById("loadBtn");
const explainBtn = document.getElementById("explainBtn");
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
const topTicker = document.getElementById("topTicker");

function formatNum(value) {
  return Number.isFinite(value) ? value.toFixed(1) : "-";
}

function metricBarCell(value) {
  return `
    <div class="delta">
      <div class="delta-bar"><span style="width:${Math.max(0, Math.min(100, value * 10))}%"></span></div>
      <small>${formatNum(value)}</small>
    </div>
  `;
}

function renderTable() {
  tbody.innerHTML = "";
  for (const stock of stocks) {
    const tr = document.createElement("tr");
    tr.dataset.ticker = stock.ticker;
    tr.innerHTML = `
      <td><span class="rank-badge">${stock.rank}</span></td>
      <td class="ticker-cell">${stock.ticker}</td>
      <td class="score-text">${stock.total}</td>
      <td>${metricBarCell(stock.quality)}</td>
      <td>${metricBarCell(stock.value)}</td>
      <td>${metricBarCell(stock.trend)}</td>
    `;
    tr.addEventListener("click", () => selectStock(stock.ticker));
    tbody.appendChild(tr);
  }
}

function setStage(stageKey) {
  state.stage = stageKey;
  const p = stagePresets[stageKey];
  universeCount.textContent = p.universe;
  coveragePct.textContent = p.coverage;
  eligibleCount.textContent = p.eligible;
  topTicker.textContent = p.top;
  rowsLoaded.textContent = state.loaded ? `${stocks.length} loaded` : p.loaded;

  document.querySelectorAll(".chip").forEach((chip) => {
    const active = chip.dataset.stage === stageKey;
    chip.classList.toggle("active", active);
    chip.setAttribute("aria-selected", String(active));
  });
}

function renderDetail(stock) {
  detailContent.classList.remove("is-empty");
  detailContent.innerHTML = "";
  const fragment = detailTemplate.content.cloneNode(true);

  fragment.querySelector(".detail-name").textContent = `${stock.ticker} · ${stock.name}`;
  fragment.querySelector(".detail-sub").textContent = stock.sector;
  fragment.querySelector(".detail-total").textContent = stock.total;
  fragment.querySelector(".detail-revenue").textContent = stock.revenue;
  fragment.querySelector(".detail-pe").textContent = stock.pe;
  fragment.querySelector(".detail-debt").textContent = stock.debt;
  fragment.querySelector(".detail-ai").textContent = `${stock.ai}/10`;
  fragment.querySelector(".detail-headline").textContent = stock.headline;

  const bars = fragment.querySelector(".bars");
  const breakdown = [
    ["Quality", stock.quality, false],
    ["Value", stock.value, false],
    ["Trend", stock.trend, false],
    ["AI", stock.ai, true]
  ];

  for (const [label, value, ai] of breakdown) {
    const row = document.createElement("div");
    row.className = `bar-row${ai ? " ai" : ""}`;
    row.innerHTML = `
      <label>${label}</label>
      <div class="bar-track"><span class="bar-fill"></span></div>
      <span>${formatNum(value)}</span>
    `;
    bars.appendChild(row);
    requestAnimationFrame(() => {
      row.querySelector(".bar-fill").style.width = `${Math.max(0, Math.min(100, value * 10))}%`;
    });
  }

  detailContent.appendChild(fragment);
  detailContent.classList.toggle("hidden-breakdown", !state.showBreakdown);
  detailContent.classList.add("flash");
  setTimeout(() => detailContent.classList.remove("flash"), 400);
  detailBadge.textContent = `Rank #${stock.rank}`;
}

function selectStock(ticker) {
  state.selectedTicker = ticker;
  const stock = stocks.find((s) => s.ticker === ticker);
  if (!stock) return;

  document.querySelectorAll("#rankingTable tbody tr").forEach((row) => {
    row.classList.toggle("active", row.dataset.ticker === ticker);
  });

  if (state.stage !== "ranked") setStage("ranked");
  renderDetail(stock);
}

function loadRankings() {
  if (!state.loaded) {
    renderTable();
    state.loaded = true;
    emptyState.hidden = true;
    table.hidden = false;
    setStage("ranked");
    loadBtn.textContent = "Reload Demo";
  } else {
    tbody.innerHTML = "";
    renderTable();
  }

  if (!state.selectedTicker) {
    selectStock(stocks[0].ticker);
  }
}

function toggleBreakdown() {
  state.showBreakdown = !state.showBreakdown;
  explainBtn.setAttribute("aria-pressed", String(state.showBreakdown));
  explainBtn.textContent = state.showBreakdown ? "Hide Score Breakdown" : "Show Score Breakdown";
  detailContent.classList.toggle("hidden-breakdown", !state.showBreakdown);
}

loadBtn.addEventListener("click", loadRankings);
explainBtn.addEventListener("click", toggleBreakdown);

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => setStage(chip.dataset.stage));
});

setStage("raw");
