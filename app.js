/**
 * Smart Money 200 DMA Paper Trading Terminal Frontend Logic
 * Dual-Mode Engine: Seamless Live FastAPI Backend + Standalone Cloud Snapshot (GitHub Pages & Mobile)
 */

const API_BASE = "";

// State
let appState = {
    isLiveBackend: false,
    portfolio: {},
    watchlist: [],
    upcomingTrades: [],
    positions: [],
    todayTrades: [],
    trades: [],
    logs: [],
    marketStatus: {},
    activeUpcomingFilter: "PENDING",
    searchTerm: ""
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

    // Update Badges
    const pendingCount = items.filter(i => i.status === "PENDING").length;
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
                        <td>${formatVolume(item.avg_volume_1m)}</td>
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
