/**
 * Smart Money 200 DMA Paper Trading Terminal Frontend Logic
 */

const API_BASE = "";

// State
let appState = {
    portfolio: {},
    watchlist: [],
    positions: [],
    trades: [],
    logs: [],
    marketStatus: {},
    activeWatchlistFilter: "ALL"
};

// DOM Elements
const el = {
    // Top Nav & Status
    marketStatusBadge: document.getElementById("market-status-badge"),
    marketStatusText: document.getElementById("market-status-text"),
    istClockText: document.getElementById("ist-clock-text"),
    btnRunCheck: document.getElementById("btn-run-check"),
    btnSyncEmail: document.getElementById("btn-sync-email"),
    btnOpenPasteModal: document.getElementById("btn-open-paste-modal"),
    btnOpenSettings: document.getElementById("btn-open-settings"),
    
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
    
    // Tabs
    tabLinks: document.querySelectorAll(".tab-link"),
    tabPanes: document.querySelectorAll(".tab-pane"),
    badgeWatchlistCount: document.getElementById("badge-watchlist-count"),
    badgePositionsCount: document.getElementById("badge-positions-count"),
    badgeTradesCount: document.getElementById("badge-trades-count"),
    
    // Tables
    watchlistTableBody: document.getElementById("watchlist-table-body"),
    positionsTableBody: document.getElementById("positions-table-body"),
    tradesTableBody: document.getElementById("trades-table-body"),
    systemLogsList: document.getElementById("system-logs-list"),
    emailPreviewIframe: document.getElementById("email-preview-iframe"),
    
    // Filters & Actions
    filterWlButtons: document.querySelectorAll(".filter-btn"),
    btnAddStockModal: document.getElementById("btn-add-stock-modal"),
    btnResetPortfolio: document.getElementById("btn-reset-portfolio"),
    btnSendEmailNow: document.getElementById("btn-send-email-now"),
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
    initModals();
    initFilters();
    initActionButtons();
    
    // Initial data fetch
    refreshAllData();
    
    // Start interval timers
    setInterval(updateClock, 1000);
    setInterval(refreshAllData, 20000); // Poll data every 20s
});

// Toast notification helper
function showToast(message, type = "info") {
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
    } catch (e) {
        // Fallback
    }
}

// Tab navigation handling
function initTabs() {
    el.tabLinks.forEach(tab => {
        tab.addEventListener("click", () => {
            const target = tab.getAttribute("data-tab");
            
            el.tabLinks.forEach(t => t.classList.remove("active"));
            el.tabPanes.forEach(p => p.classList.remove("active"));
            
            tab.classList.add("active");
            const targetPane = document.getElementById(target);
            if (targetPane) targetPane.classList.add("active");
            
            if (target === "tab-preview") {
                loadEmailPreview();
            }
        });
    });
}

// Watchlist Filter
function initFilters() {
    el.filterWlButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            el.filterWlButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            appState.activeWatchlistFilter = btn.getAttribute("data-filter");
            renderWatchlist();
        });
    });
}

// Fetch all backend data
async function refreshAllData() {
    try {
        const [statusRes, portRes, wlRes, posRes, trRes] = await Promise.all([
            fetch(`${API_BASE}/api/status`).then(r => r.json()),
            fetch(`${API_BASE}/api/portfolio`).then(r => r.json()),
            fetch(`${API_BASE}/api/watchlist`).then(r => r.json()),
            fetch(`${API_BASE}/api/positions`).then(r => r.json()),
            fetch(`${API_BASE}/api/trades`).then(r => r.json())
        ]);

        appState.marketStatus = statusRes;
        appState.portfolio = portRes;
        appState.watchlist = wlRes;
        appState.positions = posRes;
        appState.trades = trRes;

        renderMarketStatus();
        renderMetrics();
        renderWatchlist();
        renderPositions();
        renderTrades();
        loadLogs();
    } catch (err) {
        console.error("Error refreshing data:", err);
    }
}

function renderMarketStatus() {
    const market = appState.marketStatus?.market || {};
    const isOpen = market.is_open;
    const isSimulated = appState.marketStatus?.simulate_market_hours;

    if (isOpen) {
        el.marketStatusBadge.className = "status-badge";
        el.marketStatusText.textContent = isSimulated ? "Market: Sim Open" : "NSE/BSE: Market Open";
    } else {
        el.marketStatusBadge.className = "status-badge closed";
        el.marketStatusText.textContent = "NSE/BSE: Market Closed";
    }
}

function renderMetrics() {
    const p = appState.portfolio;
    if (!p) return;

    el.valTotalPortfolio.textContent = `₹${(p.total_portfolio_value || 100000).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    el.valCashBalance.textContent = `₹${(p.cash_balance || 100000).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    el.valInvestedCapital.textContent = `₹${(p.invested_capital || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    el.valPositionsMkt.textContent = `₹${(p.positions_market_value || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    el.valPositionsCount.textContent = `${p.open_positions_count || 0} / 10 Trades`;

    const ret = p.total_return_pct || 0;
    const sign = ret >= 0 ? "+" : "";
    el.valTotalReturn.textContent = `${sign}${ret}%`;
    el.valTotalReturn.className = `return-indicator ${ret < 0 ? 'negative' : ''}`;

    const totalPnl = p.total_pnl || 0;
    const pnlSign = totalPnl >= 0 ? "+" : "";
    el.valTotalPnl.textContent = `${pnlSign}₹${totalPnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    el.valTotalPnl.style.color = totalPnl >= 0 ? "var(--success)" : "var(--danger)";

    el.valRealizedPnl.textContent = `₹${(p.realized_pnl || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    el.valUnrealizedPnl.textContent = `₹${(p.unrealized_pnl || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    el.valUnrealizedPnl.style.color = (p.unrealized_pnl || 0) >= 0 ? "var(--success)" : "var(--danger)";
}

function renderWatchlist() {
    const items = appState.watchlist || [];
    el.badgeWatchlistCount.textContent = items.length;

    let filtered = items;
    if (appState.activeWatchlistFilter === "PENDING") {
        filtered = items.filter(i => i.status === "PENDING");
    } else if (appState.activeWatchlistFilter === "TRIGGERED") {
        filtered = items.filter(i => i.status === "TRIGGERED");
    }

    if (filtered.length === 0) {
        el.watchlistTableBody.innerHTML = `
            <tr>
                <td colspan="9" class="table-empty">No stocks in current filter view. Click "Sync Gmail" or "Paste Report" to load your 6 PM report.</td>
            </tr>
        `;
        return;
    }

    let rowsHtml = "";
    filtered.forEach(item => {
        const isAbove = item.section === "above_200_dma";
        const sectionBadge = isAbove 
            ? `<span class="badge badge-above">Above 200 DMA</span>` 
            : `<span class="badge badge-below">Below 200 DMA</span>`;

        const statusBadge = item.status === "TRIGGERED"
            ? `<span class="badge badge-triggered">Triggered (Bought)</span>`
            : `<span class="badge badge-pending">Pending</span>`;

        const livePrice = item.current_price || item.cmp_report;
        const triggerPrice = item.trigger_price;
        
        // Calculate proximity percentage
        let proximityPct = 0;
        let proximityColor = "var(--primary)";
        if (triggerPrice > 0) {
            proximityPct = Math.min(100, Math.max(0, Math.round((livePrice / triggerPrice) * 100)));
            if (livePrice >= triggerPrice) proximityColor = "var(--success)";
        }

        rowsHtml += `
            <tr>
                <td class="stock-symbol-cell">
                    ${item.symbol}
                    <span class="stock-name-sub">${item.stock_name}</span>
                </td>
                <td>${sectionBadge}</td>
                <td>₹${item.cmp_report.toFixed(2)}</td>
                <td>₹${item.dma_200.toFixed(2)}</td>
                <td style="color: var(--primary); font-weight: 700;">₹${triggerPrice.toFixed(2)}</td>
                <td style="font-weight: 600;">₹${livePrice.toFixed(2)}</td>
                <td>
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" style="width: ${proximityPct}%; background: ${proximityColor};"></div>
                    </div>
                    <span style="font-size: 11px; font-family: var(--font-mono);">${proximityPct}%</span>
                </td>
                <td>${statusBadge}</td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="openSimulatePrice('${item.symbol}', ${triggerPrice})">
                        🧪 Test Trigger
                    </button>
                </td>
            </tr>
        `;
    });

    el.watchlistTableBody.innerHTML = rowsHtml;
}

function renderPositions() {
    const positions = appState.positions || [];
    el.badgePositionsCount.textContent = positions.length;

    if (positions.length === 0) {
        el.positionsTableBody.innerHTML = `
            <tr>
                <td colspan="9" class="table-empty">No active open positions. Max capacity: 10 trades (₹10,000 each).</td>
            </tr>
        `;
        return;
    }

    let rowsHtml = "";
    positions.forEach(p => {
        const pnl = p.current_pnl || 0;
        const pnlPct = p.current_pnl_pct || 0;
        const pnlClass = pnl >= 0 ? "text-positive" : "text-danger";
        const sign = pnl >= 0 ? "+" : "";

        rowsHtml += `
            <tr>
                <td class="stock-symbol-cell">
                    ${p.symbol}
                    <span class="stock-name-sub">${p.stock_name}</span>
                </td>
                <td>${p.quantity}</td>
                <td>₹${p.buy_price.toFixed(2)}</td>
                <td>₹${p.invested_amount.toFixed(2)}</td>
                <td style="font-weight: 700;">₹${(p.current_price || p.buy_price).toFixed(2)}</td>
                <td style="color: var(--danger); font-weight: 600;">₹${p.stop_loss.toFixed(2)} (-2%)</td>
                <td style="color: var(--success); font-weight: 600;">₹${p.target_price.toFixed(2)} (+5%)</td>
                <td class="${pnlClass}">${sign}₹${pnl.toFixed(2)} (${sign}${pnlPct}%)</td>
                <td>
                    <div style="display: flex; gap: 6px;">
                        <button class="btn btn-sm btn-outline" onclick="openSimulatePrice('${p.symbol}', ${p.target_price})">
                            🧪 Test Target
                        </button>
                        <button class="btn btn-sm btn-outline text-danger" onclick="closePositionManual(${p.id})">
                            Close
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    el.positionsTableBody.innerHTML = rowsHtml;
}

function renderTrades() {
    const trades = appState.trades || [];
    el.badgeTradesCount.textContent = trades.length;

    if (trades.length === 0) {
        el.tradesTableBody.innerHTML = `
            <tr>
                <td colspan="8" class="table-empty">No trades recorded yet.</td>
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
            ? `<span class="${pnlVal >= 0 ? 'text-positive' : 'text-danger'}">${pnlVal >= 0 ? '+' : ''}₹${pnlVal.toFixed(2)}</span>` 
            : '-';

        rowsHtml += `
            <tr>
                <td style="color: var(--text-muted); font-size: 12px;">${t.timestamp}</td>
                <td class="stock-symbol-cell">${t.symbol}</td>
                <td>${badge}</td>
                <td>₹${t.price.toFixed(2)}</td>
                <td>${t.quantity}</td>
                <td>₹${t.total_value.toFixed(2)}</td>
                <td>${pnlStr}</td>
                <td style="color: var(--text-secondary); font-size: 12px;">${t.exit_reason || 'ENTRY'}</td>
            </tr>
        `;
    });

    el.tradesTableBody.innerHTML = rowsHtml;
}

async function loadLogs() {
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
    } catch (e) {
        console.error("Error loading logs", e);
    }
}

function loadEmailPreview() {
    el.emailPreviewIframe.src = `${API_BASE}/api/actions/preview-daily-report?t=${Date.now()}`;
}

// Action Button Handlers
function initActionButtons() {
    // Run Market Check
    el.btnRunCheck.addEventListener("click", async () => {
        try {
            el.btnRunCheck.disabled = true;
            el.btnRunCheck.innerHTML = `<span class="btn-icon">⌛</span> Checking...`;
            
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
            
            showToast(`Market check finished: ${buys} buys triggered, ${tgts} targets hit, ${sls} stop-losses.`, "success");
            await refreshAllData();
        } catch (e) {
            showToast(`Market check failed: ${e.message}`, "error");
        } finally {
            el.btnRunCheck.disabled = false;
            el.btnRunCheck.innerHTML = `<span class="btn-icon">⚡</span> Run Market Check`;
        }
    });

    // Sync Gmail
    el.btnSyncEmail.addEventListener("click", async () => {
        try {
            el.btnSyncEmail.disabled = true;
            el.btnSyncEmail.innerHTML = `<span class="btn-icon">⌛</span> Connecting Gmail...`;
            
            const res = await fetch(`${API_BASE}/api/actions/fetch-mail`, { method: "POST" });
            const data = await res.json();
            
            if (data.success) {
                showToast(data.message, "success");
                await refreshAllData();
            } else {
                showToast(data.message, "warning");
            }
        } catch (e) {
            showToast(`Gmail sync failed: ${e.message}`, "error");
        } finally {
            el.btnSyncEmail.disabled = false;
            el.btnSyncEmail.innerHTML = `<span class="btn-icon">📥</span> Sync Gmail`;
        }
    });

    // Send Daily Email Report
    el.btnSendEmailNow.addEventListener("click", async () => {
        try {
            el.btnSendEmailNow.disabled = true;
            el.btnSendEmailNow.textContent = "Sending Email...";
            
            const res = await fetch(`${API_BASE}/api/actions/send-daily-report`, { method: "POST" });
            const data = await res.json();
            
            if (data.success) {
                showToast(data.message, "success");
            } else {
                showToast(data.message, "error");
            }
        } catch (e) {
            showToast(`Failed: ${e.message}`, "error");
        } finally {
            el.btnSendEmailNow.disabled = false;
            el.btnSendEmailNow.textContent = "🚀 Send This Email To My Inbox Now";
        }
    });

    // Reset Portfolio
    el.btnResetPortfolio.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to reset the portfolio back to initial ₹1,00,000 cash balance? This will clear active positions and history.")) {
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

    // Refresh Logs
    el.btnRefreshLogs.addEventListener("click", loadLogs);
}

// Modals Initializer
function initModals() {
    // Open Settings
    el.btnOpenSettings.addEventListener("click", async () => {
        try {
            const res = await fetch(`${API_BASE}/api/settings`);
            const cfg = await res.json();
            
            document.getElementById("input-gmail-user").value = cfg.gmail_user || "";
            document.getElementById("input-gmail-pwd").value = cfg.gmail_app_password || "";
            document.getElementById("input-mail-subject").value = cfg.email_report_subject || "Daily smart money finder report";
            document.getElementById("input-notify-recipient").value = cfg.notification_recipient || "";
            document.getElementById("input-total-capital").value = cfg.total_capital || 100000;
            document.getElementById("input-trade-alloc").value = cfg.trade_allocation || 10000;
            document.getElementById("input-trigger-buf").value = cfg.trigger_buffer_pct || 1.0;
            document.getElementById("input-stop-loss").value = cfg.stop_loss_pct || 2.0;
            document.getElementById("input-target").value = cfg.target_pct || 5.0;
            document.getElementById("check-simulate-market").checked = !!cfg.simulate_market_hours;
            
            el.modalSettings.classList.add("active");
        } catch (e) {
            showToast("Failed to load settings", "error");
        }
    });

    document.getElementById("btn-close-settings").addEventListener("click", () => el.modalSettings.classList.remove("active"));
    document.getElementById("btn-cancel-settings").addEventListener("click", () => el.modalSettings.classList.remove("active"));

    // Save Settings
    document.getElementById("settings-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            gmail_user: document.getElementById("input-gmail-user").value.trim(),
            gmail_app_password: document.getElementById("input-gmail-pwd").value.trim(),
            email_report_subject: document.getElementById("input-mail-subject").value.trim(),
            notification_recipient: document.getElementById("input-notify-recipient").value.trim(),
            total_capital: parseFloat(document.getElementById("input-total-capital").value),
            trade_allocation: parseFloat(document.getElementById("input-trade-alloc").value),
            trigger_buffer_pct: parseFloat(document.getElementById("input-trigger-buf").value),
            stop_loss_pct: parseFloat(document.getElementById("input-stop-loss").value),
            target_pct: parseFloat(document.getElementById("input-target").value),
            simulate_market_hours: document.getElementById("check-simulate-market").checked
        };
        
        try {
            const res = await fetch(`${API_BASE}/api/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.success) {
                showToast("Settings successfully saved!", "success");
                el.modalSettings.classList.remove("active");
                refreshAllData();
            }
        } catch (err) {
            showToast(`Error saving settings: ${err.message}`, "error");
        }
    });

    // Paste Email Report Modal
    el.btnOpenPasteModal.addEventListener("click", () => el.modalPaste.classList.add("active"));
    document.getElementById("btn-close-paste").addEventListener("click", () => el.modalPaste.classList.remove("active"));
    document.getElementById("btn-cancel-paste").addEventListener("click", () => el.modalPaste.classList.remove("active"));

    // Sample Report Template loader
    document.getElementById("btn-load-sample-mail").addEventListener("click", () => {
        const sample = `
<html>
<body>
<h2>Daily smart money finder report</h2>
<p>Here is your daily screening report for 200 DMA:</p>

<h3>Best for buy above 200 dma</h3>
<table border="1" cellpadding="6">
  <tr><th>Stock Name</th><th>CMP</th><th>200 DMA Trigger</th></tr>
  <tr><td>TATAMOTORS</td><td>975.00</td><td>965.00</td></tr>
  <tr><td>RELIANCE</td><td>2950.00</td><td>2910.00</td></tr>
  <tr><td>INFOSYS</td><td>1850.00</td><td>1820.00</td></tr>
</table>

<h3>Best for sell below 200 dma</h3>
<table border="1" cellpadding="6">
  <tr><th>Stock Name</th><th>CMP</th><th>200 DMA Trigger</th></tr>
  <tr><td>HDFCBANK</td><td>1640.00</td><td>1660.00</td></tr>
  <tr><td>WIPRO</td><td>490.00</td><td>510.00</td></tr>
</table>
</body>
</html>
        `.trim();
        document.getElementById("textarea-raw-mail").value = sample;
    });

    // Submit Paste
    document.getElementById("btn-submit-paste").addEventListener("click", async () => {
        const content = document.getElementById("textarea-raw-mail").value.trim();
        if (!content) {
            showToast("Please paste the email content first", "warning");
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/api/actions/parse-raw-mail`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: content, is_html: content.includes("<") })
            });
            const data = await res.json();
            if (data.success) {
                showToast(data.message, "success");
                el.modalPaste.classList.remove("active");
                document.getElementById("textarea-raw-mail").value = "";
                await refreshAllData();
            } else {
                showToast(data.message, "error");
            }
        } catch (e) {
            showToast(`Parsing failed: ${e.message}`, "error");
        }
    });

    // Add Manual Stock Modal
    el.btnAddStockModal.addEventListener("click", () => el.modalManualStock.classList.add("active"));
    document.getElementById("btn-close-manual-stock").addEventListener("click", () => el.modalManualStock.classList.remove("active"));
    document.getElementById("btn-cancel-manual-stock").addEventListener("click", () => el.modalManualStock.classList.remove("active"));

    document.getElementById("manual-stock-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            stock_name: document.getElementById("manual-stock-name").value.trim(),
            section: document.getElementById("manual-stock-section").value,
            cmp_report: parseFloat(document.getElementById("manual-stock-cmp").value),
            dma_200: parseFloat(document.getElementById("manual-stock-dma").value)
        };

        try {
            const res = await fetch(`${API_BASE}/api/watchlist`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.success) {
                showToast(`Added ${data.symbol} (Trigger Buy: ₹${data.trigger_price})`, "success");
                el.modalManualStock.classList.remove("active");
                document.getElementById("manual-stock-form").reset();
                await refreshAllData();
            }
        } catch (err) {
            showToast(`Error adding stock: ${err.message}`, "error");
        }
    });

    // Close Simulate Modal
    document.getElementById("btn-close-sim-price").addEventListener("click", () => el.modalSimulatePrice.classList.remove("active"));
    document.getElementById("btn-cancel-sim-price").addEventListener("click", () => el.modalSimulatePrice.classList.remove("active"));

    // Submit Simulate Price
    document.getElementById("simulate-price-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const symbol = document.getElementById("sim-stock-symbol").value;
        const price = parseFloat(document.getElementById("sim-new-price").value);

        try {
            const res = await fetch(`${API_BASE}/api/actions/simulate-price`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol: symbol, price: price })
            });
            const data = await res.json();
            showToast(data.message, "success");
            el.modalSimulatePrice.classList.remove("active");
            
            // Immediately run a cycle to evaluate the test price
            el.btnRunCheck.click();
        } catch (err) {
            showToast(`Failed: ${err.message}`, "error");
        }
    });
}

// Global actions exposed to table rows
window.closePositionManual = async function(posId) {
    if (!confirm("Are you sure you want to manually close this position at current market price?")) return;
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
    document.getElementById("sim-stock-symbol").value = symbol;
    document.getElementById("sim-new-price").value = defaultPrice.toFixed(2);
    el.modalSimulatePrice.classList.add("active");
};
