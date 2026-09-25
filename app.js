/**
 * Smart Money 200 DMA Paper Trading Terminal Frontend Logic
 * Dual-Mode Engine: Seamless Live FastAPI Backend + Standalone Cloud Snapshot (GitHub Pages & Mobile)
 */

const API_BASE = "";

// State
let appState = {
    isLiveBackend: false,
    activePortfolio: 1,          // 1 = Portfolio 1 (200 DMA), 2 = Portfolio 2 (Wyckoff)
    portfolio: {},
    watchlist: [],
    upcomingTrades: [],
    positions: [],
    todayTrades: [],
    trades: [],
    logs: [],
    marketStatus: {},
    activeUpcomingFilter: "PENDING",
    searchTerm: "",
    // Portfolio 2
    p2Portfolio: {},
    p2Watchlist: [],
    p2Positions: [],
    p2Trades: []
};

// Local storage key for offline/snapshot trade overrides
const LOCAL_REJECTED_KEY = "portfolio_rejected_trades_v1";

function getLocalRejectedIds() {
    try {
        return JSON.parse(localStorage.getItem(LOCAL_REJECTED_KEY) || "[]");
    } catch (e) {
        return [];
    }
}

function saveLocalRejectedIds(ids) {
    try {
        localStorage.setItem(LOCAL_REJECTED_KEY, JSON.stringify(ids));
    } catch (e) {}
}

// DOM Elements
const el = {
    // Nav & Badges
    marketStatusBadge: document.getElementById("market-status-badge"),
    marketStatusText: document.getElementById("market-status-text"),
    istClockText: document.getElementById("ist-clock-text"),
    syncModeBadge: document.getElementById("sync-mode-badge"),
    btnRunCheck: document.getElementById("btn-run-check"),
    btnSyncSheets: document.getElementById("btn-sync-sheets"),
    btnOpenSettings: document.getElementById("btn-open-settings"),
    btnMobileMenu: document.getElementById("btn-mobile-menu"),

    // Metrics
    valTotalPortfolio: document.getElementById("val-total-portfolio"),
    valTotalReturn: document.getElementById("val-total-return"),
    valCashBalance: document.getElementById("val-cash-balance"),
    valInvestedCapital: document.getElementById("val-invested-capital"),
    valPositionsMkt: document.getElementById("val-positions-mkt"),
    valPositionsCount: document.getElementById("val-positions-count"),
    valTotalPnl: document.getElementById("val-total-pnl"),
    valRealizedPnl: document.getElementById("val-realized-pnl"),
    valUnrealizedPnl: document.getElementById("val-unrealized-pnl"),
    slotsDotsContainer: document.getElementById("slots-dots-container"),
    allocationFillCash: document.getElementById("allocation-fill-cash"),
    allocationFillInvested: document.getElementById("allocation-fill-invested"),
    allocationPctCash: document.getElementById("allocation-pct-cash"),
    allocationPctInvested: document.getElementById("allocation-pct-invested"),

    // Tabs
    tabLinks: document.querySelectorAll(".tab-link"),
    tabPanes: document.querySelectorAll(".tab-pane"),
    bottomNavItems: document.querySelectorAll(".bottom-nav-item"),
    badgeUpcomingCount: document.getElementById("badge-upcoming-count"),
    badgePositionsCount: document.getElementById("badge-positions-count"),
    badgeTodayCount: document.getElementById("badge-today-count"),
    badgeTradesCount: document.getElementById("badge-trades-count"),
    bottomBadgeUpcoming: document.getElementById("bottom-badge-upcoming"),
    bottomBadgePositions: document.getElementById("bottom-badge-positions"),
    bottomBadgeToday: document.getElementById("bottom-badge-today"),

    // Upcoming Section
    upcomingTableBody: document.getElementById("upcoming-table-body"),
    upcomingMobileCards: document.getElementById("upcoming-mobile-cards"),
    filterUpcomingButtons: document.querySelectorAll(".filter-btn-upcoming"),
    inputSearchUpcoming: document.getElementById("input-search-upcoming"),

    // Positions Section
    positionsTableBody: document.getElementById("positions-table-body"),
    positionsMobileCards: document.getElementById("positions-mobile-cards"),

    // Today's Trades Section
    todayTradesTableBody: document.getElementById("today-trades-table-body"),
    todayTradesMobileCards: document.getElementById("today-trades-mobile-cards"),
    todayStatCount: document.getElementById("today-stat-count"),
    todayStatBuys: document.getElementById("today-stat-buys"),
    todayStatExits: document.getElementById("today-stat-exits"),
    todayStatPnl: document.getElementById("today-stat-pnl"),

    // Trades History & Logs
    tradesTableBody: document.getElementById("trades-table-body"),
    systemLogsList: document.getElementById("system-logs-list"),
    emailPreviewIframe: document.getElementById("email-preview-iframe"),
    btnSendEmailNow: document.getElementById("btn-send-email-now"),
    btnResetPortfolio: document.getElementById("btn-reset-portfolio"),
    btnRefreshLogs: document.getElementById("btn-refresh-logs"),

    // Modals
    modalSettings: document.getElementById("modal-settings"),
    modalPaste: document.getElementById("modal-paste"),
    modalManualStock: document.getElementById("modal-manual-stock"),
    modalSimulatePrice: document.getElementById("modal-simulate-price"),
    toastContainer: document.getElementById("toast-container")
};

// Initialization
document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initBottomNav();
    initFilters();
    initSearch();
    initModals();
    initActionButtons();
    initPortfolioToggle();   // ← Portfolio 1/2 switcher

    // Initial data fetch
    refreshAllData();

    // Timers
    setInterval(updateClock, 1000);
    setInterval(refreshAllData, 25000);
});

// Toast notification helper
function showToast(message, type = "info") {
    if (!el.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    el.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Clock updater in IST
function updateClock() {
    try {
        const now = new Date();
        const options = { timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" };
        const istString = now.toLocaleTimeString("en-GB", options);
        if (el.istClockText) {
            el.istClockText.textContent = `${istString} IST`;
        }
    } catch (e) {}
}

// Tab navigation handling
function switchTab(tabId) {
    el.tabLinks.forEach(t => t.classList.toggle("active", t.getAttribute("data-tab") === tabId));
    el.tabPanes.forEach(p => p.classList.toggle("active", p.id === tabId));
    el.bottomNavItems.forEach(b => b.classList.toggle("active", b.getAttribute("data-tab") === tabId));

    if (tabId === "tab-preview") {
        loadEmailPreview();
    }
}

function initTabs() {
    el.tabLinks.forEach(tab => {
        tab.addEventListener("click", () => {
            switchTab(tab.getAttribute("data-tab"));
        });
    });
}

function initBottomNav() {
    el.bottomNavItems.forEach(item => {
        item.addEventListener("click", () => {
            switchTab(item.getAttribute("data-tab"));
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    });
}

function initFilters() {
    el.filterUpcomingButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            el.filterUpcomingButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            appState.activeUpcomingFilter = btn.getAttribute("data-filter");
            renderUpcomingTrades();
        });
    });
}

function initSearch() {
    if (el.inputSearchUpcoming) {
        el.inputSearchUpcoming.addEventListener("input", (e) => {
            appState.searchTerm = e.target.value.trim().toLowerCase();
            renderUpcomingTrades();
        });
    }
}

// Primary Data Fetcher (Dual-Mode: Live API or Static Snapshot)
async function refreshAllData() {
    let loadedViaApi = false;

    // 1. Try Live API (only if not forcing snapshot)
    if (window.location.protocol !== "file:") {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 3500);

            const [statusRes, portRes, upRes, posRes, todayRes, trRes] = await Promise.all([
                fetch(`${API_BASE}/api/status`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/portfolio`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/trades/upcoming`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/positions`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/trades/today`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/trades`, { signal: controller.signal }).then(r => r.json())
            ]);
            clearTimeout(timeoutId);

            appState.isLiveBackend = true;
            appState.marketStatus = statusRes;
            appState.portfolio = portRes;
            appState.upcomingTrades = upRes;
            appState.positions = posRes;
            appState.todayTrades = todayRes.trades || [];
            appState.trades = trRes;
            loadedViaApi = true;
            loadLogs();
        } catch (e) {
            // Live API not available or timed out (e.g. running on GitHub Pages)
            loadedViaApi = false;
        }
    }

    // 2. Fallback to Cloud Snapshot (For Mobile / GitHub Pages)
    if (!loadedViaApi) {
        try {
            const snapshotPaths = [
                "./data/portfolio_snapshot.json",
                "./portfolio_snapshot.json",
                "../data/portfolio_snapshot.json",
                "https://raw.githubusercontent.com/digant2207/portfolio1/main/data/portfolio_snapshot.json"
            ];
            let snap = null;
            for (const path of snapshotPaths) {
                try {
                    const r = await fetch(`${path}?t=${Date.now()}`);
                    if (r.ok) {
                        snap = await r.json();
                        break;
                    }
                } catch (err) {}
            }

            if (snap) {
                appState.isLiveBackend = false;
                appState.portfolio = snap.portfolio || {};
                appState.positions = snap.positions || [];
                appState.todayTrades = snap.today_trades || [];
                appState.trades = snap.all_trades || [];
                appState.upcomingTrades = snap.upcoming_trades || [];
                appState.marketStatus = {
                    market: { is_open: false, message: `Snapshot from ${snap.generated_at}` },
                    snapshot_mode: true
                };

                // Also absorb any P2 data bundled inside the main snapshot
                if (snap.portfolio2)  appState.p2Portfolio  = snap.portfolio2;
                if (snap.p2_positions) appState.p2Positions = snap.p2_positions;
                if (snap.p2_trades)    appState.p2Trades    = snap.p2_trades;
                if (snap.p2_watchlist) appState.p2Watchlist = snap.p2_watchlist;
            }

            // Try dedicated P2 snapshot (data/p2_snapshot.json) separately
            const p2SnapPaths = [
                "./data/p2_snapshot.json",
                "./p2_snapshot.json",
                "https://raw.githubusercontent.com/digant2207/portfolio1/main/data/p2_snapshot.json"
            ];
            for (const p of p2SnapPaths) {
                try {
                    const r2 = await fetch(`${p}?t=${Date.now()}`);
                    if (r2.ok) {
                        const p2snap = await r2.json();
                        if (p2snap.portfolio2)  appState.p2Portfolio  = p2snap.portfolio2;
                        if (p2snap.p2_positions) appState.p2Positions = p2snap.p2_positions;
                        if (p2snap.p2_trades)    appState.p2Trades    = p2snap.p2_trades;
                        if (p2snap.p2_watchlist) appState.p2Watchlist = p2snap.p2_watchlist;
                        break;
                    }
                } catch (_) {}
            }
        } catch (snapshotErr) {
            console.warn("Could not load snapshot:", snapshotErr);
        }
    }

    // Apply local storage overrides for rejected trades (useful on mobile static view)
    applyLocalRejections();

    // Render components
    renderModeBadge();
    renderMarketStatus();
    renderMetrics();
    renderUpcomingTrades();
    renderPositions();
    renderTodayTrades();
    renderTradesHistory();
}

function applyLocalRejections() {
    const localRejected = getLocalRejectedIds();
    if (!localRejected || localRejected.length === 0) return;

    appState.upcomingTrades.forEach(item => {
        if (localRejected.includes(item.id) || localRejected.includes(item.symbol)) {
            item.status = "REJECTED";
        }
    });
}

function renderModeBadge() {
    if (!el.syncModeBadge) return;
    if (appState.isLiveBackend) {
        el.syncModeBadge.innerHTML = `<span class="pulse-dot" style="background:#00f2fe;box-shadow:0 0 8px #00f2fe;"></span> Live Engine`;
        el.syncModeBadge.style.color = "var(--cyan-neon)";
        el.syncModeBadge.title = "Connected to live FastAPI trading server";
    } else {
        el.syncModeBadge.innerHTML = `☁️ Cloud Sync (Mobile)`;
        el.syncModeBadge.style.color = "var(--text-secondary)";
        el.syncModeBadge.title = "Viewing cloud snapshot on GitHub Pages / Mobile";
    }
}

function renderMarketStatus() {
    const market = appState.marketStatus?.market || {};
    const isOpen = market.is_open;

    if (isOpen) {
        el.marketStatusBadge.className = "status-badge";
        el.marketStatusText.textContent = "NSE: Market Open";
    } else {
        el.marketStatusBadge.className = "status-badge closed";
        el.marketStatusText.textContent = "NSE: Market Closed";
    }
}

function renderMetrics() {
    const p = appState.portfolio || {};
    const totalVal = p.total_portfolio_value || 100000;
    const cash = p.cash_balance !== undefined ? p.cash_balance : 100000;
    const invested = p.invested_capital || 0;
    const mktVal = p.positions_market_value || 0;
    const posCount = p.open_positions_count || appState.positions.length || 0;
    const ret = p.total_return_pct || 0;
    const totalPnl = p.total_pnl || 0;
    const realizedPnl = p.realized_pnl || 0;
    const unrealizedPnl = p.unrealized_pnl || 0;

    el.valTotalPortfolio.textContent = `₹${totalVal.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    el.valCashBalance.textContent = `₹${cash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    el.valInvestedCapital.textContent = `₹${invested.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    el.valPositionsMkt.textContent = `₹${mktVal.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    el.valPositionsCount.textContent = `${posCount} / 10 Active Trades`;

    // Return indicator
    const sign = ret >= 0 ? "+" : "";
    el.valTotalReturn.textContent = `${sign}${ret.toFixed(2)}%`;
    el.valTotalReturn.className = `return-indicator ${ret < 0 ? 'negative' : ''}`;

    // Total P&L
    const pnlSign = totalPnl >= 0 ? "+" : "";
    el.valTotalPnl.textContent = `${pnlSign}₹${totalPnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    el.valTotalPnl.style.color = totalPnl >= 0 ? "var(--success)" : "var(--danger)";

    el.valRealizedPnl.textContent = `${realizedPnl >= 0 ? '+' : ''}₹${realizedPnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    el.valRealizedPnl.className = realizedPnl >= 0 ? "text-positive" : "text-danger";

    el.valUnrealizedPnl.textContent = `${unrealizedPnl >= 0 ? '+' : ''}₹${unrealizedPnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    el.valUnrealizedPnl.className = unrealizedPnl >= 0 ? "text-positive" : "text-danger";

    // 10 Slot Dots
    if (el.slotsDotsContainer) {
        let dotsHtml = "";
        for (let i = 0; i < 10; i++) {
            dotsHtml += `<span class="slot-dot ${i < posCount ? 'filled' : ''}" title="Slot ${i + 1}: ${i < posCount ? 'Active' : 'Empty'}"></span>`;
        }
        el.slotsDotsContainer.innerHTML = dotsHtml;
    }

    // Asset Allocation Bar
    const totalAssets = Math.max(1, cash + mktVal);
    const cashPct = Math.round((cash / totalAssets) * 100);
    const invPct = Math.max(0, 100 - cashPct);

    if (el.allocationFillCash) el.allocationFillCash.style.width = `${cashPct}%`;
    if (el.allocationFillInvested) el.allocationFillInvested.style.width = `${invPct}%`;
    if (el.allocationPctCash) el.allocationPctCash.textContent = `${cashPct}%`;
    if (el.allocationPctInvested) el.allocationPctInvested.textContent = `${invPct}%`;
}

// ==========================================================================
// 1. UPCOMING TRADES (Breakout Watchlist)
// ==========================================================================
function renderUpcomingTrades() {
    const items = appState.upcomingTrades || [];
    let filtered = items;

    // Apply Filter Tab
    if (appState.activeUpcomingFilter === "PENDING") {
        filtered = items.filter(i => i.status === "PENDING");
    } else if (appState.activeUpcomingFilter === "REJECTED") {
        filtered = items.filter(i => i.status === "REJECTED");
    } else if (appState.activeUpcomingFilter === "TRIGGERED") {
        filtered = items.filter(i => i.status === "TRIGGERED");
    }

    // Apply Search
    if (appState.searchTerm) {
        filtered = filtered.filter(i => 
            (i.symbol || "").toLowerCase().includes(appState.searchTerm) ||
            (i.stock_name || "").toLowerCase().includes(appState.searchTerm)
        );
    }

    // Deduplicate by symbol (prevent duplicate rows for the same stock)
    const seenSymbols = new Set();
    const uniqueFiltered = [];
    for (const item of filtered) {
        if (!seenSymbols.has(item.symbol)) {
            seenSymbols.add(item.symbol);
            uniqueFiltered.push(item);
        }
    }
    filtered = uniqueFiltered;

    // Update Badges (unique symbols)
    const seenPending = new Set();
    let pendingCount = 0;
    for (const i of items) {
        if (i.status === "PENDING" && !seenPending.has(i.symbol)) {
            seenPending.add(i.symbol);
            pendingCount++;
        }
    }
    if (el.badgeUpcomingCount) el.badgeUpcomingCount.textContent = pendingCount;
    if (el.bottomBadgeUpcoming) el.bottomBadgeUpcoming.textContent = pendingCount;

    // Desktop Table Render
    if (el.upcomingTableBody) {
        if (filtered.length === 0) {
            el.upcomingTableBody.innerHTML = `
                <tr>
                    <td colspan="9" class="table-empty">
                        No stocks found under current filter (${appState.activeUpcomingFilter}). 
                        Click "Sync Sheets" to fetch screened 200 DMA breakout candidates.
                    </td>
                </tr>
            `;
        } else {
            let tableHtml = "";
            filtered.forEach(item => {
                const isRejected = item.status === "REJECTED";
                const isTriggered = item.status === "TRIGGERED";
                const isAbove = item.section === "above_200_dma";

                const sectionBadge = isAbove 
                    ? `<span class="badge badge-above">Above 200 DMA</span>` 
                    : `<span class="badge badge-below">Below 200 DMA</span>`;

                const triggerBadge = item.sheet_trigger 
                    ? `<span class="badge badge-warning" style="font-size:10px; padding:1px 5px;" title="Custom Trigger Price from Sheet">⚡ Custom Trigger</span>` 
                    : "";

                let statusBadge = `<span class="badge badge-pending">Ready</span>`;
                if (isRejected) {
                    statusBadge = `<span class="badge badge-rejected">🛑 STOPPED</span>`;
                } else if (isTriggered) {
                    statusBadge = `<span class="badge badge-triggered">Triggered (Bought)</span>`;
                }

                const livePrice = item.current_price || item.cmp_report;
                const triggerPrice = item.trigger_price;
                const dma200 = item.dma_200;
                const proximityPct = Math.min(100, Math.max(0, Math.round((livePrice / triggerPrice) * 100)));
                const distPct = item.distance_pct !== undefined ? item.distance_pct : round2(((triggerPrice - livePrice) / triggerPrice) * 100);

                let proxColor = "var(--primary)";
                if (proximityPct >= 98) proxColor = "var(--success)";
                else if (proximityPct >= 95) proxColor = "var(--warning)";

                // Action button: Stop/Reject or Restore
                let actionBtn = "";
                if (isRejected) {
                    actionBtn = `
                        <button class="btn btn-sm btn-success-outline" onclick="restoreUpcomingTrade(${item.id}, '${item.symbol}')">
                            ↺ Enable / Restore
                        </button>
                    `;
                } else if (!isTriggered) {
                    actionBtn = `
                        <div style="display:flex; gap:6px;">
                            <button class="btn btn-sm btn-danger-outline" onclick="rejectUpcomingTrade(${item.id}, '${item.symbol}')" title="Stop & Reject: Engine will not buy this stock">
                                🛑 Stop / Reject
                            </button>
                            <button class="btn btn-sm btn-outline" onclick="openSimulatePrice('${item.symbol}', ${triggerPrice})" title="Test Breakout Trigger">
                                🧪 Test
                            </button>
                        </div>
                    `;
                } else {
                    actionBtn = `<span style="font-size:11px; color:var(--text-muted);">Already Triggered</span>`;
                }

                tableHtml += `
                    <tr class="${isRejected ? 'row-rejected' : ''}">
                        <td class="stock-symbol-cell">
                            ${item.symbol} ${triggerBadge}
                            <span class="stock-name-sub">${item.stock_name}</span>
                        </td>
                        <td>${sectionBadge}</td>
                        <td>₹${dma200.toFixed(2)}</td>
                        <td style="color: var(--cyan-neon); font-weight: 700; font-family: var(--font-mono);">₹${triggerPrice.toFixed(2)}</td>
                        <td style="font-weight: 600; font-family: var(--font-mono);">₹${livePrice.toFixed(2)}</td>
                        <td>
                            <div class="progress-bar-container">
                                <div class="progress-bar-fill" style="width: ${proximityPct}%; background: ${proxColor};"></div>
                            </div>
                            <span style="font-size: 11px; font-family: var(--font-mono);">${proximityPct}% (${distPct > 0 ? distPct + '% away' : 'Crossed'})</span>
                        </td>
                        <td>
                            ${formatVolume(item.avg_volume_1m)}
                            ${item.vol_pct ? `<br><span class="badge ${item.vol_pct >= 50 ? 'badge-success' : 'badge-warning'}" style="font-size:10px; padding:1px 5px;" title="Today Volume vs 1-Month Avg">Vol: ${item.vol_pct}%</span>` : ''}
                        </td>
                        <td>${statusBadge}</td>
                        <td>${actionBtn}</td>
                    </tr>
                `;
            });
            el.upcomingTableBody.innerHTML = tableHtml;
        }
    }

    // Mobile Card Render
    if (el.upcomingMobileCards) {
        if (filtered.length === 0) {
            el.upcomingMobileCards.innerHTML = `
                <div class="table-empty">
                    No upcoming trades in filter (${appState.activeUpcomingFilter}).
                </div>
            `;
        } else {
            let cardsHtml = "";
            filtered.forEach(item => {
                const isRejected = item.status === "REJECTED";
                const isTriggered = item.status === "TRIGGERED";
                const livePrice = item.current_price || item.cmp_report;
                const triggerPrice = item.trigger_price;
                const proximityPct = Math.min(100, Math.max(0, Math.round((livePrice / triggerPrice) * 100)));
                const distPct = item.distance_pct !== undefined ? item.distance_pct : round2(((triggerPrice - livePrice) / triggerPrice) * 100);

                let statusBadge = `<span class="badge badge-pending">Ready</span>`;
                if (isRejected) {
                    statusBadge = `<span class="badge badge-rejected">🛑 STOPPED</span>`;
                } else if (isTriggered) {
                    statusBadge = `<span class="badge badge-triggered">Triggered</span>`;
                }

                let cardAction = "";
                if (isRejected) {
                    cardAction = `
                        <button class="btn btn-success-outline" onclick="restoreUpcomingTrade(${item.id}, '${item.symbol}')">
                            ↺ Restore Trade
                        </button>
                    `;
                } else if (!isTriggered) {
                    cardAction = `
                        <button class="btn btn-danger-outline" onclick="rejectUpcomingTrade(${item.id}, '${item.symbol}')">
                            🛑 Stop / Reject Trade
                        </button>
                        <button class="btn btn-outline" style="max-width:90px;" onclick="openSimulatePrice('${item.symbol}', ${triggerPrice})">
                            🧪 Test
                        </button>
                    `;
                }

                cardsHtml += `
                    <div class="stock-mobile-card ${isRejected ? 'card-rejected' : ''}">
                        <div class="mobile-card-top">
                            <div>
                                <span class="mobile-card-symbol">${item.symbol}</span>
                                <div class="mobile-card-name">${item.stock_name}</div>
                            </div>
                            <div>${statusBadge}</div>
                        </div>
                        <div class="mobile-card-stats">
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Live CMP</span>
                                <span class="mobile-stat-val">₹${livePrice.toFixed(2)}</span>
                            </div>
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Buy Trigger</span>
                                <span class="mobile-stat-val text-cyan">₹${triggerPrice.toFixed(2)}</span>
                            </div>
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">200 DMA</span>
                                <span class="mobile-stat-val">₹${item.dma_200.toFixed(2)}</span>
                            </div>
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Vol %</span>
                                <span class="mobile-stat-val" style="color: ${item.vol_pct >= 50 ? 'var(--success)' : 'var(--text-muted)'}; font-weight:600;">${item.vol_pct ? item.vol_pct + '%' : '-'}</span>
                            </div>
                        </div>
                        <div>
                            <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
                                <span style="color:var(--text-muted);">Proximity to Buy Trigger:</span>
                                <span style="font-family:var(--font-mono); font-weight:700;">${proximityPct}% (${distPct > 0 ? distPct + '% away' : 'At Trigger'})</span>
                            </div>
                            <div class="progress-bar-container" style="width:100%;">
                                <div class="progress-bar-fill" style="width: ${proximityPct}%; background: ${proximityPct >= 98 ? 'var(--success)' : 'var(--primary)'};"></div>
                            </div>
                        </div>
                        <div class="mobile-card-actions">
                            ${cardAction}
                        </div>
                    </div>
                `;
            });
            el.upcomingMobileCards.innerHTML = cardsHtml;
        }
    }
}

// ==========================================================================
// Stop / Reject & Restore Actions
// ==========================================================================
window.rejectUpcomingTrade = async function(watchlistId, symbol) {
    if (!confirm(`Are you sure you want to STOP and REJECT upcoming trade for ${symbol}?\n\nThe automated trading engine will NOT execute buy orders for this stock.`)) {
        return;
    }

    // If live API mode
    if (appState.isLiveBackend) {
        try {
            const res = await fetch(`${API_BASE}/api/watchlist/${watchlistId}/reject`, { method: "POST" });
            const data = await res.json();
            if (data.success) {
                showToast(`🛑 ${symbol} trade stopped and rejected.`, "warning");
                refreshAllData();
                return;
            }
        } catch (e) {
            console.warn("API reject failed, falling back to local storage:", e);
        }
    }

    // Static / Mobile mode fallback
    const local = getLocalRejectedIds();
    if (!local.includes(watchlistId)) local.push(watchlistId);
    if (!local.includes(symbol)) local.push(symbol);
    saveLocalRejectedIds(local);

    // Update in memory
    const target = appState.upcomingTrades.find(i => i.id === watchlistId || i.symbol === symbol);
    if (target) target.status = "REJECTED";

    showToast(`🛑 ${symbol} marked as STOPPED in your mobile browser.`, "warning");
    renderUpcomingTrades();
};

window.restoreUpcomingTrade = async function(watchlistId, symbol) {
    // If live API mode
    if (appState.isLiveBackend) {
        try {
            const res = await fetch(`${API_BASE}/api/watchlist/${watchlistId}/restore`, { method: "POST" });
            const data = await res.json();
            if (data.success) {
                showToast(`✅ ${symbol} restored to active pending watchlist.`, "success");
                refreshAllData();
                return;
            }
        } catch (e) {
            console.warn("API restore failed, falling back to local storage:", e);
        }
    }

    // Static / Mobile mode fallback
    let local = getLocalRejectedIds();
    local = local.filter(id => id !== watchlistId && id !== symbol);
    saveLocalRejectedIds(local);

    const target = appState.upcomingTrades.find(i => i.id === watchlistId || i.symbol === symbol);
    if (target) target.status = "PENDING";

    showToast(`✅ ${symbol} restored and ready for breakout trigger.`, "success");
    renderUpcomingTrades();
};

// ==========================================================================
// 2. CURRENT POSITIONS (Active Holdings)
// ==========================================================================
function renderPositions() {
    const positions = appState.positions || [];
    if (el.badgePositionsCount) el.badgePositionsCount.textContent = positions.length;
    if (el.bottomBadgePositions) el.bottomBadgePositions.textContent = positions.length;

    // Desktop Table Render
    if (el.positionsTableBody) {
        if (positions.length === 0) {
            el.positionsTableBody.innerHTML = `
                <tr>
                    <td colspan="9" class="table-empty">
                        No active open positions. Max capacity: 10 trades (₹10,000 per slot).
                        When an upcoming stock crosses 200 DMA + 1%, it automatically enters here.
                    </td>
                </tr>
            `;
        } else {
            let tableHtml = "";
            positions.forEach(p => {
                const cmp = p.current_price || p.buy_price;
                const pnl = p.current_pnl || round2((cmp - p.buy_price) * p.quantity);
                const pnlPct = p.current_pnl_pct || round2(((cmp - p.buy_price) / p.buy_price) * 100);
                const pnlClass = pnl >= 0 ? "text-positive" : "text-danger";
                const sign = pnl >= 0 ? "+" : "";

                // Gauge from SL (-2%) to Target (+5%)
                const sl = p.stop_loss;
                const tgt = p.target_price;
                const rangeSpan = tgt - sl;
                const gaugePct = rangeSpan > 0 ? Math.min(100, Math.max(0, Math.round(((cmp - sl) / rangeSpan) * 100))) : 50;

                tableHtml += `
                    <tr>
                        <td class="stock-symbol-cell">
                            ${p.symbol}
                            <span class="stock-name-sub">${p.stock_name}</span>
                        </td>
                        <td style="font-family: var(--font-mono);">${p.quantity}</td>
                        <td style="font-family: var(--font-mono);">₹${p.buy_price.toFixed(2)}</td>
                        <td style="font-family: var(--font-mono);">₹${p.invested_amount.toFixed(2)}</td>
                        <td style="font-weight: 700; font-family: var(--font-mono);">₹${cmp.toFixed(2)}</td>
                        <td>
                            <div class="range-gauge-wrap">
                                <div class="range-gauge-track">
                                    <div class="range-gauge-fill" style="width: ${gaugePct}%; background: ${pnl >= 0 ? 'var(--success)' : 'var(--danger)'};"></div>
                                </div>
                                <div class="range-gauge-labels">
                                    <span style="color:var(--danger);">SL: ₹${sl.toFixed(1)}</span>
                                    <span style="color:var(--success);">Tgt: ₹${tgt.toFixed(1)}</span>
                                </div>
                            </div>
                        </td>
                        <td class="${pnlClass}" style="font-family: var(--font-mono); font-weight:700;">
                            ${sign}₹${pnl.toFixed(2)} (${sign}${pnlPct}%)
                        </td>
                        <td>
                            <div style="display:flex; gap:6px;">
                                <button class="btn btn-sm btn-danger-outline" onclick="closePositionManual(${p.id})">
                                    Close Position
                                </button>
                                <button class="btn btn-sm btn-outline" onclick="openSimulatePrice('${p.symbol}', ${p.target_price})">
                                    🧪 Target
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            });
            el.positionsTableBody.innerHTML = tableHtml;
        }
    }

    // Mobile Cards Render
    if (el.positionsMobileCards) {
        if (positions.length === 0) {
            el.positionsMobileCards.innerHTML = `
                <div class="table-empty">No active open positions.</div>
            `;
        } else {
            let cardsHtml = "";
            positions.forEach(p => {
                const cmp = p.current_price || p.buy_price;
                const pnl = p.current_pnl || round2((cmp - p.buy_price) * p.quantity);
                const pnlPct = p.current_pnl_pct || round2(((cmp - p.buy_price) / p.buy_price) * 100);
                const sign = pnl >= 0 ? "+" : "";

                cardsHtml += `
                    <div class="stock-mobile-card">
                        <div class="mobile-card-top">
                            <div>
                                <span class="mobile-card-symbol">${p.symbol}</span>
                                <div class="mobile-card-name">${p.stock_name} (${p.quantity} shares)</div>
                            </div>
                            <span class="badge ${pnl >= 0 ? 'badge-triggered' : 'badge-rejected'}" style="font-family:var(--font-mono); font-size:12px;">
                                ${sign}₹${pnl.toFixed(2)} (${sign}${pnlPct}%)
                            </span>
                        </div>
                        <div class="mobile-card-stats">
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Buy Price</span>
                                <span class="mobile-stat-val">₹${p.buy_price.toFixed(2)}</span>
                            </div>
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Live CMP</span>
                                <span class="mobile-stat-val text-cyan">₹${cmp.toFixed(2)}</span>
                            </div>
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Invested</span>
                                <span class="mobile-stat-val">₹${p.invested_amount.toFixed(2)}</span>
                            </div>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-muted);">
                            <span>Stop-Loss: <strong style="color:var(--danger);">₹${p.stop_loss.toFixed(2)} (-2%)</strong></span>
                            <span>Target: <strong style="color:var(--success);">₹${p.target_price.toFixed(2)} (+5%)</strong></span>
                        </div>
                        <div class="mobile-card-actions">
                            <button class="btn btn-danger-outline" onclick="closePositionManual(${p.id})">
                                Close Position (Manual Exit)
                            </button>
                        </div>
                    </div>
                `;
            });
            el.positionsMobileCards.innerHTML = cardsHtml;
        }
    }
}

// ==========================================================================
// 3. TODAY'S TRADES (Executed Today)
// ==========================================================================
function renderTodayTrades() {
    const todayTrades = appState.todayTrades || [];
    const count = todayTrades.length;
    const buys = todayTrades.filter(t => t.trade_type === "BUY").length;
    const exits = todayTrades.filter(t => t.trade_type === "SELL").length;
    const pnl = todayTrades.filter(t => t.trade_type === "SELL").reduce((acc, t) => acc + (t.pnl || 0), 0);

    if (el.badgeTodayCount) el.badgeTodayCount.textContent = count;
    if (el.bottomBadgeToday) el.bottomBadgeToday.textContent = count;
    if (el.todayStatCount) el.todayStatCount.textContent = count;
    if (el.todayStatBuys) el.todayStatBuys.textContent = buys;
    if (el.todayStatExits) el.todayStatExits.textContent = exits;
    if (el.todayStatPnl) {
        el.todayStatPnl.textContent = `${pnl >= 0 ? '+' : ''}₹${pnl.toFixed(2)}`;
        el.todayStatPnl.className = `today-stat-value ${pnl >= 0 ? 'text-positive' : 'text-danger'}`;
    }

    // Desktop Table Render
    if (el.todayTradesTableBody) {
        if (count === 0) {
            el.todayTradesTableBody.innerHTML = `
                <tr>
                    <td colspan="8" class="table-empty">
                        No trades executed today yet. When the automated engine buys a breakout or hits a target/SL, it will appear here.
                    </td>
                </tr>
            `;
        } else {
            let tableHtml = "";
            todayTrades.forEach(t => {
                const isBuy = t.trade_type === "BUY";
                const badge = isBuy 
                    ? `<span class="badge badge-triggered">BUY</span>` 
                    : `<span class="badge badge-above">SELL</span>`;
                const pnlVal = t.pnl || 0;
                const pnlStr = !isBuy 
                    ? `<span class="${pnlVal >= 0 ? 'text-positive' : 'text-danger'}" style="font-family:var(--font-mono); font-weight:700;">${pnlVal >= 0 ? '+' : ''}₹${pnlVal.toFixed(2)}</span>` 
                    : '-';

                tableHtml += `
                    <tr>
                        <td style="color: var(--text-muted); font-family: var(--font-mono); font-size: 11px;">${t.timestamp}</td>
                        <td class="stock-symbol-cell">${t.symbol}</td>
                        <td>${badge}</td>
                        <td style="font-family: var(--font-mono);">₹${t.price.toFixed(2)}</td>
                        <td style="font-family: var(--font-mono);">${t.quantity}</td>
                        <td style="font-family: var(--font-mono);">₹${t.total_value.toFixed(2)}</td>
                        <td>${pnlStr}</td>
                        <td style="font-size: 12px; color: var(--text-secondary);">${t.exit_reason || 'ENTRY (Breakout)'}</td>
                    </tr>
                `;
            });
            el.todayTradesTableBody.innerHTML = tableHtml;
        }
    }

    // Mobile Cards Render
    if (el.todayTradesMobileCards) {
        if (count === 0) {
            el.todayTradesMobileCards.innerHTML = `
                <div class="table-empty">No trades executed today.</div>
            `;
        } else {
            let cardsHtml = "";
            todayTrades.forEach(t => {
                const isBuy = t.trade_type === "BUY";
                cardsHtml += `
                    <div class="stock-mobile-card">
                        <div class="mobile-card-top">
                            <div>
                                <span class="mobile-card-symbol">${t.symbol}</span>
                                <div class="mobile-card-name">${t.timestamp}</div>
                            </div>
                            <span class="badge ${isBuy ? 'badge-triggered' : 'badge-above'}">${t.trade_type}</span>
                        </div>
                        <div class="mobile-card-stats">
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Price</span>
                                <span class="mobile-stat-val">₹${t.price.toFixed(2)}</span>
                            </div>
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Quantity</span>
                                <span class="mobile-stat-val">${t.quantity}</span>
                            </div>
                            <div class="mobile-stat-col">
                                <span class="mobile-stat-label">Total Value</span>
                                <span class="mobile-stat-val">₹${t.total_value.toFixed(2)}</span>
                            </div>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:12px;">
                            <span style="color:var(--text-muted);">Reason: ${t.exit_reason || 'Breakout Entry'}</span>
                            ${!isBuy ? `<span>P&L: <strong class="${t.pnl >= 0 ? 'text-positive' : 'text-danger'}">${t.pnl >= 0 ? '+' : ''}₹${(t.pnl || 0).toFixed(2)}</strong></span>` : ''}
                        </div>
                    </div>
                `;
            });
            el.todayTradesMobileCards.innerHTML = cardsHtml;
        }
    }
}

// ==========================================================================
// 4. ALL TRADES HISTORY
// ==========================================================================
function renderTradesHistory() {
    const trades = appState.trades || [];
    if (el.badgeTradesCount) el.badgeTradesCount.textContent = trades.length;

    if (!el.tradesTableBody) return;
    if (trades.length === 0) {
        el.tradesTableBody.innerHTML = `
            <tr>
                <td colspan="8" class="table-empty">No trade history recorded yet.</td>
            </tr>
        `;
        return;
    }

    let rowsHtml = "";
    trades.forEach(t => {
        const isBuy = t.trade_type === "BUY";
        const badge = isBuy 
            ? `<span class="badge badge-triggered">BUY</span>` 
            : `<span class="badge badge-above">SELL</span>`;
        const pnlVal = t.pnl || 0;
        const pnlStr = !isBuy 
            ? `<span class="${pnlVal >= 0 ? 'text-positive' : 'text-danger'}" style="font-family:var(--font-mono); font-weight:700;">${pnlVal >= 0 ? '+' : ''}₹${pnlVal.toFixed(2)}</span>` 
            : '-';

        rowsHtml += `
            <tr>
                <td style="color: var(--text-muted); font-size: 11px; font-family: var(--font-mono);">${t.timestamp}</td>
                <td class="stock-symbol-cell">${t.symbol}</td>
                <td>${badge}</td>
                <td style="font-family: var(--font-mono);">₹${t.price.toFixed(2)}</td>
                <td style="font-family: var(--font-mono);">${t.quantity}</td>
                <td style="font-family: var(--font-mono);">₹${t.total_value.toFixed(2)}</td>
                <td>${pnlStr}</td>
                <td style="color: var(--text-secondary); font-size: 12px;">${t.exit_reason || 'ENTRY'}</td>
            </tr>
        `;
    });
    el.tradesTableBody.innerHTML = rowsHtml;
}

// ==========================================================================
// System Logs & Reports
// ==========================================================================
async function loadLogs() {
    if (!el.systemLogsList || !appState.isLiveBackend) return;
    try {
        const res = await fetch(`${API_BASE}/api/logs`);
        const logs = await res.json();
        if (!logs || logs.length === 0) {
            el.systemLogsList.innerHTML = '<div style="color: var(--text-muted); padding: 12px;">No activity logs recorded yet.</div>';
            return;
        }

        let html = "";
        logs.forEach(l => {
            html += `
                <div class="log-entry ${l.level}">
                    <span class="log-time">${l.timestamp}</span>
                    <span class="log-level">[${l.level}]</span>
                    <span class="log-msg">${l.message}</span>
                </div>
            `;
        });
        el.systemLogsList.innerHTML = html;
    } catch (e) {}
}

function loadEmailPreview() {
    if (el.emailPreviewIframe && appState.isLiveBackend) {
        el.emailPreviewIframe.src = `${API_BASE}/api/actions/preview-daily-report?t=${Date.now()}`;
    }
}

// Action Button Handlers
function initActionButtons() {
    if (el.btnRunCheck) {
        el.btnRunCheck.addEventListener("click", async () => {
            if (!appState.isLiveBackend) {
                showToast("Live check requires the local Python server.", "warning");
                return;
            }
            try {
                el.btnRunCheck.disabled = true;
                el.btnRunCheck.innerHTML = `⌛ Checking...`;
                const res = await fetch(`${API_BASE}/api/actions/run-cycle`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ force_market_open: true })
                });
                const data = await res.json();
                const summary = data.summary || {};
                const buys = summary.buys_triggered?.length || 0;
                const tgts = summary.targets_hit?.length || 0;
                const sls = summary.stop_losses_hit?.length || 0;
                showToast(`Cycle complete: ${buys} buys, ${tgts} targets, ${sls} stop-losses.`, "success");
                await refreshAllData();
            } catch (e) {
                showToast(`Check failed: ${e.message}`, "error");
            } finally {
                el.btnRunCheck.disabled = false;
                el.btnRunCheck.innerHTML = `⚡ Run Check`;
            }
        });
    }

    if (el.btnSyncSheets) {
        el.btnSyncSheets.addEventListener("click", async () => {
            if (!appState.isLiveBackend) {
                showToast("Fetching sheets requires the local Python engine or cloud runner.", "warning");
                return;
            }
            try {
                el.btnSyncSheets.disabled = true;
                el.btnSyncSheets.innerHTML = `⌛ Syncing...`;
                const res = await fetch(`${API_BASE}/api/actions/fetch-mail`, { method: "POST" });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message, "success");
                    await refreshAllData();
                } else {
                    showToast(data.message, "warning");
                }
            } catch (e) {
                showToast(`Sync failed: ${e.message}`, "error");
            } finally {
                el.btnSyncSheets.disabled = false;
                el.btnSyncSheets.innerHTML = `📊 Sync Sheets`;
            }
        });
    }

    if (el.btnSendEmailNow) {
        el.btnSendEmailNow.addEventListener("click", async () => {
            try {
                el.btnSendEmailNow.disabled = true;
                el.btnSendEmailNow.textContent = "Sending Email...";
                const res = await fetch(`${API_BASE}/api/actions/send-daily-report`, { method: "POST" });
                const data = await res.json();
                showToast(data.message, data.success ? "success" : "error");
            } catch (e) {
                showToast(`Failed: ${e.message}`, "error");
            } finally {
                el.btnSendEmailNow.disabled = false;
                el.btnSendEmailNow.textContent = "🚀 Send Daily Email Report To My Inbox";
            }
        });
    }

    if (el.btnResetPortfolio) {
        el.btnResetPortfolio.addEventListener("click", async () => {
            if (!confirm("Are you sure you want to reset the portfolio back to initial ₹1,00,000 cash balance? This will clear open positions and trade history.")) {
                return;
            }
            try {
                const res = await fetch(`${API_BASE}/api/actions/reset-portfolio`, { method: "POST" });
                const data = await res.json();
                showToast(data.message, "warning");
                await refreshAllData();
            } catch (e) {
                showToast(`Reset failed: ${e.message}`, "error");
            }
        });
    }

    if (el.btnRefreshLogs) {
        el.btnRefreshLogs.addEventListener("click", loadLogs);
    }
}

// Modals Setup
function initModals() {
    if (el.btnOpenSettings) {
        el.btnOpenSettings.addEventListener("click", async () => {
            try {
                const res = await fetch(`${API_BASE}/api/settings`);
                const cfg = await res.json();
                const setVal = (id, val) => {
                    const elem = document.getElementById(id);
                    if (elem) elem.value = val !== undefined && val !== null ? val : "";
                };
                setVal("input-sheet-id", cfg.google_sheet_id || cfg.google_sheet_id_1 || "");
                setVal("input-gmail-user", cfg.gmail_user || "");
                setVal("input-gmail-pwd", cfg.gmail_app_password || "");
                setVal("input-telegram-token", cfg.telegram_bot_token || "");
                setVal("input-telegram-chat-id", cfg.telegram_chat_id || "");
                setVal("input-total-capital", cfg.total_capital || 100000);
                setVal("input-trade-alloc", cfg.trade_allocation || 10000);
                setVal("input-trigger-buf", cfg.trigger_buffer_pct || 1.0);
                setVal("input-max-breakout-buf", cfg.max_breakout_buffer_pct !== undefined ? cfg.max_breakout_buffer_pct : 5.0);
                setVal("input-require-50-dma", cfg.require_above_50_dma !== false ? "true" : "false");
                setVal("input-stop-loss", cfg.stop_loss_pct || 2.0);
                setVal("input-target", cfg.target_pct || 5.0);
                setVal("input-min-price", cfg.min_stock_price !== undefined ? cfg.min_stock_price : 20.0);
                setVal("input-min-vol", cfg.min_1m_avg_volume !== undefined ? cfg.min_1m_avg_volume : 10000);

                el.modalSettings.classList.add("active");
            } catch (e) {
                showToast("Failed to load settings (server not active)", "error");
            }
        });
    }

    const closeSettings = () => el.modalSettings?.classList.remove("active");
    document.getElementById("btn-close-settings")?.addEventListener("click", closeSettings);
    document.getElementById("btn-cancel-settings")?.addEventListener("click", closeSettings);

    document.getElementById("settings-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const getVal = (id, fallback = "") => document.getElementById(id)?.value.trim() || fallback;
        const getNum = (id, fallback = 0) => parseFloat(document.getElementById(id)?.value) || fallback;
        const getInt = (id, fallback = 0) => parseInt(document.getElementById(id)?.value, 10) || fallback;

        const payload = {
            google_sheet_id: getVal("input-sheet-id"),
            google_sheet_id_1: getVal("input-sheet-id"),
            gmail_user: getVal("input-gmail-user"),
            gmail_app_password: getVal("input-gmail-pwd"),
            telegram_bot_token: getVal("input-telegram-token"),
            telegram_chat_id: getVal("input-telegram-chat-id"),
            total_capital: getNum("input-total-capital", 100000),
            trade_allocation: getNum("input-trade-alloc", 10000),
            trigger_buffer_pct: getNum("input-trigger-buf", 1.0),
            max_breakout_buffer_pct: getNum("input-max-breakout-buf", 5.0),
            require_above_50_dma: document.getElementById("input-require-50-dma")?.value === "true",
            stop_loss_pct: getNum("input-stop-loss", 2.0),
            target_pct: getNum("input-target", 5.0),
            min_stock_price: getNum("input-min-price", 20.0),
            min_1m_avg_volume: getInt("input-min-vol", 10000)
        };

        try {
            const res = await fetch(`${API_BASE}/api/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.success) {
                showToast("Settings saved successfully!", "success");
                el.modalSettings.classList.remove("active");
                refreshAllData();
            }
        } catch (err) {
            showToast(`Error saving settings: ${err.message}`, "error");
        }
    });

    // Simulate Modal
    document.getElementById("btn-close-sim-price")?.addEventListener("click", () => el.modalSimulatePrice?.classList.remove("active"));
    document.getElementById("btn-cancel-sim-price")?.addEventListener("click", () => el.modalSimulatePrice?.classList.remove("active"));

    document.getElementById("simulate-price-form")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const symbol = document.getElementById("sim-stock-symbol").value;
        const price = parseFloat(document.getElementById("sim-new-price").value);

        try {
            const res = await fetch(`${API_BASE}/api/actions/simulate-price`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol, price })
            });
            const data = await res.json();
            showToast(data.message, "success");
            el.modalSimulatePrice?.classList.remove("active");
            el.btnRunCheck?.click();
        } catch (err) {
            showToast(`Simulation failed: ${err.message}`, "error");
        }
    });
}

// Global actions exposed
window.closePositionManual = async function(posId) {
    if (!confirm("Are you sure you want to manually close this position at CMP?")) return;
    try {
        const res = await fetch(`${API_BASE}/api/positions/${posId}/close`, { method: "POST" });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            refreshAllData();
        }
    } catch (e) {
        showToast(`Close failed: ${e.message}`, "error");
    }
};

window.openSimulatePrice = function(symbol, defaultPrice) {
    const symEl = document.getElementById("sim-stock-symbol");
    const prEl = document.getElementById("sim-new-price");
    if (symEl && prEl && el.modalSimulatePrice) {
        symEl.value = symbol;
        prEl.value = Number(defaultPrice).toFixed(2);
        el.modalSimulatePrice.classList.add("active");
    }
};

function formatVolume(vol) {
    const v = Number(vol) || 0;
    if (v >= 10000000) return (v / 10000000).toFixed(2) + " Cr";
    if (v >= 100000) return (v / 100000).toFixed(2) + " L";
    if (v >= 1000) return (v / 1000).toFixed(1) + " K";
    return v > 0 ? v.toLocaleString('en-IN') : "-";
}

function round2(num) {
    return Math.round((Number(num) || 0) * 100) / 100;
}

// ============================================================================
// PORTFOLIO 1 <-> PORTFOLIO 2 TOGGLE
// ============================================================================

function initPortfolioToggle() {
    const btnP1 = document.getElementById("btn-p1");
    const btnP2 = document.getElementById("btn-p2");
    if (!btnP1 || !btnP2) return;

    btnP1.addEventListener("click", () => switchPortfolio(1));
    btnP2.addEventListener("click", () => switchPortfolio(2));

    // Wyckoff Scan button
    const btnScan = document.getElementById("btn-p2-scan");
    if (btnScan) {
        btnScan.addEventListener("click", runWyckoffScan);
    }

    // P2 tabs
    document.querySelectorAll("#p2-tab-nav .tab-link").forEach(tab => {
        tab.addEventListener("click", () => switchP2Tab(tab.getAttribute("data-tab")));
    });
}

function switchPortfolio(portfolioNum) {
    appState.activePortfolio = portfolioNum;

    const btnP1 = document.getElementById("btn-p1");
    const btnP2 = document.getElementById("btn-p2");
    const p1Nav = document.getElementById("p1-tab-nav");
    const p2Nav = document.getElementById("p2-tab-nav");
    const brandTitle = document.getElementById("brand-title");
    const brandStrategy = document.getElementById("brand-strategy");
    const brandSubtitle = document.getElementById("brand-subtitle");

    // All P1 tab panes
    const p1Panes = document.querySelectorAll(".tab-pane:not(.p2-tab-pane)");
    const p2Panes = document.querySelectorAll(".p2-tab-pane");

    if (portfolioNum === 2) {
        // Activate P2
        btnP1 && btnP1.classList.remove("active");
        btnP2 && btnP2.classList.add("active");
        p1Nav && (p1Nav.style.display = "none");
        p2Nav && (p2Nav.style.display = "");
        p1Panes.forEach(p => p.style.display = "none");
        if (brandTitle)   brandTitle.childNodes[0].textContent = "PORTFOLIO 2 ";
        if (brandStrategy) brandStrategy.textContent = "Wyckoff";
        if (brandSubtitle) brandSubtitle.textContent = "Swing Delivery (5\u201310 Days)";

        // Activate first P2 tab
        switchP2Tab("tab-p2-watchlist");

        // Update metrics for Portfolio 2
        renderP2Metrics();

        // Load P2 data
        if (appState.isLiveBackend) loadP2Data();
    } else {
        // Activate P1
        btnP1 && btnP1.classList.add("active");
        btnP2 && btnP2.classList.remove("active");
        p1Nav && (p1Nav.style.display = "");
        p2Nav && (p2Nav.style.display = "none");
        p2Panes.forEach(p => p.style.display = "none");
        if (brandTitle)   brandTitle.childNodes[0].textContent = "PORTFOLIO 1 ";
        if (brandStrategy) brandStrategy.textContent = "200 DMA";
        if (brandSubtitle) brandSubtitle.textContent = "Smart Money Trading Ledger";

        // Restore first P1 tab
        const firstP1Tab = document.querySelector("#p1-tab-nav .tab-link");
        if (firstP1Tab) {
            document.querySelectorAll("#p1-tab-nav .tab-link").forEach(t => t.classList.remove("active"));
            firstP1Tab.classList.add("active");
        }
        const upcomingPane = document.getElementById("tab-upcoming");
        if (upcomingPane) {
            p1Panes.forEach(p => p.style.display = "");
            p1Panes.forEach(p => p.classList.remove("active"));
            upcomingPane.classList.add("active");
        }
        renderMetrics();
    }
}

function switchP2Tab(tabId) {
    document.querySelectorAll("#p2-tab-nav .tab-link").forEach(t =>
        t.classList.toggle("active", t.getAttribute("data-tab") === tabId)
    );
    document.querySelectorAll(".p2-tab-pane").forEach(p => {
        p.style.display = (p.id === tabId) ? "" : "none";
    });
}

// ============================================================================
// PORTFOLIO 2 DATA LOADER
// ============================================================================

async function loadP2Data() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const [portRes, posRes, trRes, wlRes] = await Promise.all([
            fetch(`${API_BASE}/api/p2/portfolio`,  { signal: controller.signal }).then(r => r.json()),
            fetch(`${API_BASE}/api/p2/positions`,  { signal: controller.signal }).then(r => r.json()),
            fetch(`${API_BASE}/api/p2/trades`,     { signal: controller.signal }).then(r => r.json()),
            fetch(`${API_BASE}/api/p2/watchlist`,  { signal: controller.signal }).then(r => r.json()),
        ]);
        clearTimeout(timeoutId);
        appState.p2Portfolio = portRes || {};
        appState.p2Positions = posRes  || [];
        appState.p2Trades    = trRes   || [];
        appState.p2Watchlist = wlRes   || [];
        renderP2Metrics();
        renderP2Watchlist();
        renderP2Positions();
        renderP2Trades();
        updateP2Badges();
    } catch (e) {
        console.warn("P2 data load error:", e);
    }
}

async function runWyckoffScan() {
    const btn = document.getElementById("btn-p2-scan");
    if (btn) { btn.disabled = true; btn.textContent = "\ud83d\udd04 Scanning..."; }
    try {
        const res = await fetch(`${API_BASE}/api/p2/actions/scan`, { method: "POST" });
        const data = await res.json();
        if (data.success) {
            showToast(`\u2705 ${data.message}`, "success");
            await loadP2Data();
        } else {
            showToast(data.message || "Scan failed", "error");
        }
    } catch (e) {
        showToast(`Scan error: ${e.message}`, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "\ud83d\udd0d Run Wyckoff Scan"; }
    }
}

// ============================================================================
// PORTFOLIO 2 METRICS (swap the header cards when on P2)
// ============================================================================

function renderP2Metrics() {
    const p = appState.p2Portfolio;
    if (!p || !Object.keys(p).length) return;

    const totalVal   = p.total_portfolio_value  ?? 100000;
    const cash       = p.cash_balance           ?? 100000;
    const invested   = p.invested_capital       ?? 0;
    const mktVal     = p.positions_market_value ?? 0;
    const posCount   = p.open_positions_count   ?? 0;
    const ret        = p.total_return_pct       ?? 0;
    const totalPnl   = p.total_pnl              ?? 0;
    const realized   = p.realized_pnl           ?? 0;
    const unrealized = p.unrealized_pnl         ?? 0;

    const fmt = (n) => `\u20b9${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    if (el.valTotalPortfolio) el.valTotalPortfolio.textContent = fmt(totalVal);
    if (el.valCashBalance)    el.valCashBalance.textContent    = fmt(cash);
    if (el.valInvestedCapital) el.valInvestedCapital.textContent = fmt(invested);
    if (el.valPositionsMkt)   el.valPositionsMkt.textContent   = fmt(mktVal);
    if (el.valPositionsCount) el.valPositionsCount.textContent = `${posCount} / 5 Swing Slots`;

    const sign = ret >= 0 ? "+" : "";
    if (el.valTotalReturn) {
        el.valTotalReturn.textContent = `${sign}${ret.toFixed(2)}%`;
        el.valTotalReturn.className   = `return-indicator ${ret < 0 ? 'negative' : ''}`;
    }

    const pnlSign = totalPnl >= 0 ? "+" : "";
    if (el.valTotalPnl) {
        el.valTotalPnl.textContent = `${pnlSign}${fmt(totalPnl).slice(1)}`;
        el.valTotalPnl.style.color = totalPnl >= 0 ? "var(--success)" : "var(--danger)";
    }
    if (el.valRealizedPnl) {
        el.valRealizedPnl.textContent = `${realized >= 0 ? '+' : ''}${fmt(realized).slice(1)}`;
        el.valRealizedPnl.className   = realized >= 0 ? "text-positive" : "text-danger";
    }
    if (el.valUnrealizedPnl) {
        el.valUnrealizedPnl.textContent = `${unrealized >= 0 ? '+' : ''}${fmt(unrealized).slice(1)}`;
        el.valUnrealizedPnl.className   = unrealized >= 0 ? "text-positive" : "text-danger";
    }

    // Slot dots (5 for P2)
    if (el.slotsDotsContainer) {
        let dots = "";
        for (let i = 0; i < 5; i++) {
            dots += `<span class="slot-dot ${i < posCount ? 'filled wyckoff' : ''}" title="Slot ${i+1}: ${i < posCount ? 'Active' : 'Empty'}"></span>`;
        }
        el.slotsDotsContainer.innerHTML = dots;
    }

    // Allocation bar
    const totalAssets = Math.max(1, cash + mktVal);
    const cashPct = Math.round((cash / totalAssets) * 100);
    const invPct  = Math.max(0, 100 - cashPct);
    if (el.allocationFillCash)     el.allocationFillCash.style.width     = `${cashPct}%`;
    if (el.allocationFillInvested) el.allocationFillInvested.style.width = `${invPct}%`;
    if (el.allocationPctCash)      el.allocationPctCash.textContent      = `${cashPct}%`;
    if (el.allocationPctInvested)  el.allocationPctInvested.textContent  = `${invPct}%`;
}

function updateP2Badges() {
    const wlBadge  = document.getElementById("badge-p2-watchlist-count");
    const posBadge = document.getElementById("badge-p2-positions-count");
    const trBadge  = document.getElementById("badge-p2-trades-count");
    if (wlBadge)  wlBadge.textContent  = appState.p2Watchlist.length;
    if (posBadge) posBadge.textContent = appState.p2Positions.length;
    if (trBadge)  trBadge.textContent  = appState.p2Trades.length;
}

// ============================================================================
// PORTFOLIO 2 RENDER FUNCTIONS
// ============================================================================

function renderP2Watchlist() {
    const items = appState.p2Watchlist || [];
    const tbody = document.getElementById("p2-watchlist-table-body");
    const mobileDiv = document.getElementById("p2-watchlist-mobile-cards");
    if (!tbody) return;

    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="11" class="table-empty">No Wyckoff candidates yet. Run a scan.</td></tr>';
        if (mobileDiv) mobileDiv.innerHTML = "";
        return;
    }

    const scoreColor = (s) => s >= 80 ? "var(--success)" : s >= 60 ? "var(--warning, #f59e0b)" : "var(--text-muted)";
    const phaseIcon = { "PHASE_D_MARKUP": "\ud83d\ude80", "PHASE_C_SPRING": "\ud83c�", "PHASE_B_ACCUMULATION": "\ud83d�", "PHASE_A_STOPPING": "\u23f8\ufe0f", "UNCERTAIN": "\u2753" };
    const fmt = (n) => `\u20b9${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    tbody.innerHTML = items.map(item => {
        const score = Number(item.wyckoff_score || 0);
        const phase = item.phase_label || "UNKNOWN";
        const icon  = phaseIcon[phase] || "\u2753";
        const spring = item.spring_detected ? "<span class='badge-yes'>\u2705 Spring</span>" : "<span class='badge-no'>\u2013</span>";
        const sos    = item.sos_detected    ? "<span class='badge-yes'>\u2705 SOS</span>"    : "<span class='badge-no'>\u2013</span>";
        const statusClass = { PENDING: "text-cyan", TRIGGERED: "text-positive", EXPIRED: "text-muted", REJECTED: "text-danger" }[item.status] || "";
        return `
        <tr>
            <td><strong style="color:#f8fafc;">${item.symbol}</strong>
                <div style="font-size:11px;color:#94a3b8;">${item.stock_name || ""}</div></td>
            <td><span style="color:${scoreColor(score)};font-weight:700;font-size:15px;">${score.toFixed(0)}</span><span style="color:#64748b;font-size:11px;">/100</span></td>
            <td><span title="${phase}">${icon} <span style="font-size:11px;">${phase.replace(/_/g,' ')}</span></span></td>
            <td style="font-weight:600;">${fmt(item.cmp_report)}</td>
            <td style="font-size:12px;color:#94a3b8;">
                <span style="color:var(--danger)">${fmt(item.support)}</span> /
                <span style="color:var(--success)">${fmt(item.resistance)}</span>
            </td>
            <td>${spring}</td>
            <td>${sos}</td>
            <td style="color:#f8fafc;">${fmt(item.entry_price)}</td>
            <td style="color:var(--danger);">${fmt(item.suggested_stop_loss)} <span style="font-size:10px;color:#64748b;">(-${Number(item.sl_pct||0).toFixed(1)}%)</span></td>
            <td style="color:var(--success);">${fmt(item.suggested_target)} <span style="font-size:10px;color:#64748b;">(+${Number(item.target_pct||0).toFixed(0)}%)</span></td>
            <td><span class="${statusClass}">${item.status}</span></td>
        </tr>`;
    }).join("");

    // Mobile cards
    if (mobileDiv) {
        mobileDiv.innerHTML = items.map(item => {
            const score = Number(item.wyckoff_score || 0);
            const phase = item.phase_label || "UNKNOWN";
            const icon  = phaseIcon[phase] || "\u2753";
            return `
            <div class="position-card" style="border-left:3px solid ${scoreColor(score)};">
                <div class="pos-card-header">
                    <div>
                        <span class="pos-symbol">${item.symbol}</span>
                        <span class="pos-name">${item.stock_name || ""}</span>
                    </div>
                    <div style="text-align:right;">
                        <span style="color:${scoreColor(score)};font-weight:700;font-size:18px;">${score.toFixed(0)}</span>
                        <div style="font-size:10px;color:#64748b;">Wyckoff Score</div>
                    </div>
                </div>
                <div class="pos-card-grid">
                    <div><span class="pos-label">Phase</span><span>${icon} ${phase.replace(/_/g,' ')}</span></div>
                    <div><span class="pos-label">CMP</span><span>${fmt(item.cmp_report)}</span></div>
                    <div><span class="pos-label">Entry</span><span style="color:#f8fafc;font-weight:600;">${fmt(item.entry_price)}</span></div>
                    <div><span class="pos-label">SL</span><span style="color:var(--danger);">${fmt(item.suggested_stop_loss)}</span></div>
                    <div><span class="pos-label">Target</span><span style="color:var(--success);">${fmt(item.suggested_target)}</span></div>
                    <div><span class="pos-label">Spring/SOS</span><span>${item.spring_detected?'\u2705 Spring':'\u2013'} ${item.sos_detected?'\u2705 SOS':''}</span></div>
                </div>
            </div>`;
        }).join("");
    }
}

function renderP2Positions() {
    const items = appState.p2Positions || [];
    const tbody = document.getElementById("p2-positions-table-body");
    const mobileDiv = document.getElementById("p2-positions-mobile-cards");
    if (!tbody) return;

    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="table-empty">No open Wyckoff swing positions.</td></tr>';
        if (mobileDiv) mobileDiv.innerHTML = "";
        return;
    }

    const fmt = (n) => `\u20b9${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    tbody.innerHTML = items.map(pos => {
        const pnl     = Number(pos.current_pnl || 0);
        const pnlPct  = Number(pos.current_pnl_pct || 0);
        const pnlColor= pnl >= 0 ? "var(--success)" : "var(--danger)";
        const pnlSign = pnl >= 0 ? "+" : "";
        const effSL   = pos.trailing_active ? pos.trailing_sl : pos.stop_loss;
        const trailing= pos.trailing_active
            ? `<span style="color:var(--success);font-size:11px;">\ud83d\udea8 Active @ ${fmt(pos.trailing_sl)}</span>`
            : `<span style="color:#64748b;font-size:11px;">Kicks in at +5%</span>`;
        const sessions = Number(pos.sessions_held || 0);
        const sessColor = sessions >= 8 ? "var(--danger)" : sessions >= 5 ? "var(--warning, #f59e0b)" : "var(--text-muted)";
        return `
        <tr>
            <td><strong style="color:#f8fafc;">${pos.symbol}</strong>
                <div style="font-size:11px;color:#94a3b8;">${pos.stock_name}</div></td>
            <td>${pos.quantity}</td>
            <td>${fmt(pos.buy_price)}</td>
            <td style="font-weight:600;">${fmt(pos.current_price || pos.buy_price)}</td>
            <td style="color:var(--danger);">${fmt(effSL)} <span style="font-size:10px;">(-${Number(pos.sl_pct||0).toFixed(1)}%)</span></td>
            <td style="color:var(--success);">${fmt(pos.target_price)} <span style="font-size:10px;">(+${Number(pos.target_pct||0).toFixed(0)}%)</span></td>
            <td style="color:${sessColor};font-weight:600;">${sessions}<span style="color:#64748b;font-size:11px;">/10</span></td>
            <td>${trailing}</td>
            <td style="color:${pnlColor};font-weight:700;">${pnlSign}${fmt(pnl).slice(1)}
                <div style="font-size:11px;">(${pnlSign}${pnlPct.toFixed(2)}%)</div></td>
        </tr>`;
    }).join("");

    if (mobileDiv) {
        mobileDiv.innerHTML = items.map(pos => {
            const pnl     = Number(pos.current_pnl || 0);
            const pnlPct  = Number(pos.current_pnl_pct || 0);
            const pnlColor= pnl >= 0 ? "var(--success)" : "var(--danger)";
            const pnlSign = pnl >= 0 ? "+" : "";
            const effSL   = pos.trailing_active ? pos.trailing_sl : pos.stop_loss;
            const sessions = Number(pos.sessions_held || 0);
            return `
            <div class="position-card" style="border-left:3px solid ${pnlColor};">
                <div class="pos-card-header">
                    <div><span class="pos-symbol">${pos.symbol}</span><span class="pos-name">${pos.stock_name}</span></div>
                    <div style="text-align:right;color:${pnlColor};font-weight:700;">${pnlSign}${fmt(pnl).slice(1)}<div style="font-size:11px;">${pnlSign}${pnlPct.toFixed(2)}%</div></div>
                </div>
                <div class="pos-card-grid">
                    <div><span class="pos-label">Qty</span><span>${pos.quantity} shares</span></div>
                    <div><span class="pos-label">Buy</span><span>${fmt(pos.buy_price)}</span></div>
                    <div><span class="pos-label">CMP</span><span style="font-weight:600;">${fmt(pos.current_price||pos.buy_price)}</span></div>
                    <div><span class="pos-label">Eff. SL</span><span style="color:var(--danger);">${fmt(effSL)}</span></div>
                    <div><span class="pos-label">Target</span><span style="color:var(--success);">${fmt(pos.target_price)}</span></div>
                    <div><span class="pos-label">Sessions</span><span>${sessions}/10 ${pos.trailing_active?'\ud83d\udea8 Trail':''}</span></div>
                </div>
            </div>`;
        }).join("");
    }
}

function renderP2Trades() {
    const trades = appState.p2Trades || [];
    const tbody  = document.getElementById("p2-trades-table-body");
    if (!tbody) return;

    if (!trades.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="table-empty">No Portfolio 2 trades recorded yet.</td></tr>';
        return;
    }

    const fmt = (n) => `\u20b9${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    const reasonLabel = { TARGET_HIT: "\ud83c� Target", STOP_LOSS_HIT: "\ud83d� Stop-Loss", TIME_STOP: "\u23f0 Time-Stop", TRAILING_STOP: "\ud83d� Trailing", MANUAL: "\u270b Manual" };

    tbody.innerHTML = trades.map((t, i) => {
        const isBuy  = t.trade_type === "BUY";
        const pnl    = Number(t.pnl || 0);
        const pnlStr = !isBuy
            ? `<span style="color:${pnl>=0?'var(--success)':'var(--danger)'};">${pnl>=0?'+':''}${fmt(pnl).slice(1)}</span>`
            : `<span style="color:#64748b;">\u2014</span>`;
        return `
        <tr>
            <td style="color:#64748b;">${t.id || i+1}</td>
            <td><span class="trade-type-badge ${isBuy?'buy':'sell'}">${t.trade_type}</span></td>
            <td><strong>${t.symbol}</strong><div style="font-size:11px;color:#94a3b8;">${t.stock_name||''}</div></td>
            <td>${fmt(t.price)}</td>
            <td>${t.quantity}</td>
            <td>${fmt(t.total_value)}</td>
            <td>${pnlStr}</td>
            <td style="font-size:12px;">${reasonLabel[t.exit_reason] || (t.exit_reason || '\u2014')}</td>
            <td style="font-size:11px;color:#64748b;">${(t.timestamp||'').split('.')[0]}</td>
        </tr>`;
    }).join("");
}
