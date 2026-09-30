/**
 * Portfolio 2: Wyckoff Swing Delivery Frontend Logic
 * Dual-Mode Engine: Seamless Live FastAPI Backend + Standalone Snapshot (GitHub Pages & Mobile)
 */

const API_BASE = "";

// State
let p2State = {
    isLiveBackend: false,
    portfolio: {},
    watchlist: [],
    positions: [],
    trades: [],
    activeFilter: "ALL",
    searchTerm: "",
    marketStatus: {}
};

// Local storage key for offline/snapshot rejected trade overrides
const P2_REJECTED_KEY = "p2_rejected_watchlist_v1";

function getP2RejectedIds() {
    try {
        return JSON.parse(localStorage.getItem(P2_REJECTED_KEY) || "[]");
    } catch (e) {
        return [];
    }
}

function saveP2RejectedIds(ids) {
    try {
        localStorage.setItem(P2_REJECTED_KEY, JSON.stringify(ids));
    } catch (e) {}
}

// DOM Elements
const el = {
    // Nav & Badges
    marketStatusBadge: document.getElementById("market-status-badge"),
    marketStatusText: document.getElementById("market-status-text"),
    istClockText: document.getElementById("ist-clock-text"),
    syncModeBadge: document.getElementById("sync-mode-badge"),
    btnRunCycle: document.getElementById("btn-p2-run-cycle"),
    btnScan: document.getElementById("btn-p2-scan"),
    btnOpenSettings: document.getElementById("btn-open-settings"),
    btnResetP2: document.getElementById("btn-reset-p2"),

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

    // Tabs & Badges
    tabLinks: document.querySelectorAll(".tab-link"),
    tabPanes: document.querySelectorAll(".tab-pane"),
    bottomNavItems: document.querySelectorAll(".bottom-nav-item"),
    badgeWatchlistCount: document.getElementById("badge-watchlist-count"),
    badgePositionsCount: document.getElementById("badge-positions-count"),
    badgeTradesCount: document.getElementById("badge-trades-count"),
    bottomBadgeWatchlist: document.getElementById("bottom-badge-watchlist"),
    bottomBadgePositions: document.getElementById("bottom-badge-positions"),
    bottomBadgeTrades: document.getElementById("bottom-badge-trades"),

    // Watchlist
    watchlistTableBody: document.getElementById("p2-watchlist-table-body"),
    watchlistMobileCards: document.getElementById("p2-watchlist-mobile-cards"),
    filterButtons: document.querySelectorAll(".filter-btn-p2"),
    inputSearchWatchlist: document.getElementById("input-search-watchlist"),

    // Positions
    positionsTableBody: document.getElementById("p2-positions-table-body"),
    positionsMobileCards: document.getElementById("p2-positions-mobile-cards"),

    // Trades
    tradesTableBody: document.getElementById("p2-trades-table-body"),
    tradesMobileCards: document.getElementById("p2-trades-mobile-cards"),

    // Modals
    modalBuy: document.getElementById("modal-p2-confirm-buy"),
    modalSettings: document.getElementById("modal-settings"),
    toastContainer: document.getElementById("toast-container")
};

// ============================================================================
// AUDIO FEEDBACK (Synthesized via Web Audio API)
// ============================================================================
function playTone(freq, type = "sine", duration = 0.15) {
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(freq, ctx.currentTime);
        gain.gain.setValueAtTime(0.08, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + duration);
    } catch (_) {}
}

function playSuccessChime() {
    playTone(587.33, "sine", 0.12);
    setTimeout(() => playTone(880, "sine", 0.25), 100);
}

function playAlertTone() {
    playTone(349.23, "triangle", 0.2);
}

// Toast helper
function showToast(message, type = "info") {
    if (!el.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    el.toastContainer.appendChild(toast);

    if (type === "success") playSuccessChime();
    if (type === "error" || type === "warning") playAlertTone();

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

// Tab navigation
function switchTab(tabId) {
    if (!tabId) return;

    el.tabLinks.forEach(t =>
        t.classList.toggle("active", t.getAttribute("data-tab") === tabId)
    );
    el.tabPanes.forEach(p => {
        const isActive = (p.id === tabId);
        p.style.display = isActive ? "block" : "none";
        p.classList.toggle("active", isActive);
    });
    el.bottomNavItems.forEach(b =>
        b.classList.toggle("active", b.getAttribute("data-tab") === tabId)
    );
}

// Data loaders
async function loadP2Snapshot() {
    const snapshotPaths = [
        "./p2_snapshot.json",
        "./data/p2_snapshot.json",
        "./frontend/p2_snapshot.json",
        "https://raw.githubusercontent.com/digant2207/portfolio1/main/p2_snapshot.json",
        "https://raw.githubusercontent.com/digant2207/portfolio1/main/data/p2_snapshot.json"
    ];

    for (const path of snapshotPaths) {
        try {
            const res = await fetch(`${path}?t=${Date.now()}`);
            if (res.ok) {
                const data = await res.json();
                p2State.portfolio = data.portfolio2 || {};
                p2State.positions = data.p2_positions || [];
                p2State.trades = data.p2_trades || [];
                p2State.watchlist = data.p2_watchlist || [];
                
                if (el.syncModeBadge) {
                    el.syncModeBadge.innerHTML = `<span class="pulse-dot" style="background:#c084fc;"></span> Standalone Snapshot`;
                }
                if (el.marketStatusText) {
                    el.marketStatusText.textContent = "Snapshot Loaded";
                }
                
                renderAll();
                return true;
            }
        } catch (_) {}
    }
    return false;
}

async function refreshP2Data() {
    let loadedViaApi = false;

    if (window.location.protocol !== "file:") {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 3500);

            const [statusRes, portRes, posRes, trRes, wlRes] = await Promise.all([
                fetch(`${API_BASE}/api/status`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/p2/portfolio`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/p2/positions`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/p2/trades`, { signal: controller.signal }).then(r => r.json()),
                fetch(`${API_BASE}/api/p2/watchlist`, { signal: controller.signal }).then(r => r.json())
            ]);
            clearTimeout(timeoutId);

            p2State.isLiveBackend = true;
            p2State.marketStatus = statusRes || {};
            p2State.portfolio = portRes || {};
            p2State.positions = posRes || [];
            p2State.trades = trRes || [];
            p2State.watchlist = wlRes || [];
            loadedViaApi = true;

            if (el.syncModeBadge) {
                el.syncModeBadge.innerHTML = `<span class="pulse-dot" style="background:#38bdf8;"></span> Live API Connected`;
            }
            if (el.marketStatusText) {
                el.marketStatusText.textContent = statusRes?.is_open ? "Market Open (Live)" : "Market Closed";
            }
            renderAll();
        } catch (err) {
            p2State.isLiveBackend = false;
        }
    }

    if (!loadedViaApi) {
        await loadP2Snapshot();
    }
}

function renderAll() {
    renderMetrics();
    renderWatchlist();
    renderPositions();
    renderTrades();
    updateBadges();
}

// Helpers
const fmt = (n) => `₹${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// Metrics
function renderMetrics() {
    const p = p2State.portfolio;
    const totalVal = p.total_portfolio_value ?? 100000;
    const cash = p.cash_balance ?? 100000;
    const invested = p.invested_capital ?? 0;
    const mktVal = p.positions_market_value ?? 0;
    const posCount = p.open_positions_count ?? (p2State.positions || []).length;
    const ret = p.total_return_pct ?? 0;
    const totalPnl = p.total_pnl ?? 0;
    const realized = p.realized_pnl ?? 0;
    const unrealized = p.unrealized_pnl ?? 0;

    if (el.valTotalPortfolio) el.valTotalPortfolio.textContent = fmt(totalVal);
    if (el.valCashBalance) el.valCashBalance.textContent = fmt(cash);
    if (el.valInvestedCapital) el.valInvestedCapital.textContent = fmt(invested);
    if (el.valPositionsMkt) el.valPositionsMkt.textContent = fmt(mktVal);
    if (el.valPositionsCount) el.valPositionsCount.textContent = `${posCount} / 5 Active`;

    const sign = ret >= 0 ? "+" : "";
    if (el.valTotalReturn) {
        el.valTotalReturn.textContent = `${sign}${ret.toFixed(2)}%`;
        el.valTotalReturn.className = `return-indicator ${ret < 0 ? 'negative' : ''}`;
    }

    const pnlSign = totalPnl >= 0 ? "+" : "";
    if (el.valTotalPnl) {
        el.valTotalPnl.textContent = `${pnlSign}${fmt(Math.abs(totalPnl))}`;
        el.valTotalPnl.style.color = totalPnl >= 0 ? "var(--success)" : "var(--danger)";
    }
    if (el.valRealizedPnl) {
        el.valRealizedPnl.textContent = `${realized >= 0 ? '+' : ''}${fmt(Math.abs(realized))}`;
        el.valRealizedPnl.className = realized >= 0 ? "text-positive" : "text-danger";
    }
    if (el.valUnrealizedPnl) {
        el.valUnrealizedPnl.textContent = `${unrealized >= 0 ? '+' : ''}${fmt(Math.abs(unrealized))}`;
        el.valUnrealizedPnl.className = unrealized >= 0 ? "text-positive" : "text-danger";
    }

    // 5 Swing Slots meter
    if (el.slotsDotsContainer) {
        let dots = "";
        for (let i = 0; i < 5; i++) {
            const isFilled = i < posCount;
            dots += `<span class="slot-dot ${isFilled ? 'filled wyckoff' : ''}" title="Swing Slot ${i+1}: ${isFilled ? 'Active Position' : 'Preserved Cash'}"></span>`;
        }
        el.slotsDotsContainer.innerHTML = dots;
    }

    // Allocation bar
    const total = totalVal > 0 ? totalVal : 100000;
    const cashPct = Math.max(0, Math.min(100, Math.round((cash / total) * 100)));
    const invPct = 100 - cashPct;
    if (el.allocationFillCash) el.allocationFillCash.style.width = `${cashPct}%`;
    if (el.allocationFillInvested) el.allocationFillInvested.style.width = `${invPct}%`;
    if (el.allocationPctCash) el.allocationPctCash.textContent = `${cashPct}%`;
    if (el.allocationPctInvested) el.allocationPctInvested.textContent = `${invPct}%`;
}

// Watchlist
function renderWatchlist() {
    const list = p2State.watchlist || [];
    const tbody = el.watchlistTableBody;
    const mobileDiv = el.watchlistMobileCards;
    if (!tbody && !mobileDiv) return;

    const rejected = getP2RejectedIds();

    let items = list.filter(item => {
        // Search filter
        if (p2State.searchTerm) {
            const s = p2State.searchTerm;
            const sym = (item.symbol || "").toLowerCase();
            const name = (item.stock_name || "").toLowerCase();
            if (!sym.includes(s) && !name.includes(s)) return false;
        }

        const isRej = rejected.includes(item.id) || rejected.includes(item.symbol) || item.status === "REJECTED";
        const cmp = Number(item.current_price || item.cmp_report || 0);
        const trigger = Number(item.entry_price || item.resistance || 0);
        const isTriggered = cmp >= trigger && trigger > 0;

        if (p2State.activeFilter === "REJECTED") return isRej;
        if (isRej) return false;
        if (p2State.activeFilter === "CONFIRMED") return isTriggered;
        if (p2State.activeFilter === "PENDING") return !isTriggered;
        return true;
    });

    if (!items.length) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="12" class="table-empty">No candidates matching the current filter. Run Wyckoff Scan to refresh.</td></tr>';
        if (mobileDiv) mobileDiv.innerHTML = '<div class="table-empty" style="padding:24px;text-align:center;">No candidates matching the current filter.</div>';
        return;
    }

    if (tbody) {
        tbody.innerHTML = items.map(w => {
            const cmp = Number(w.current_price || w.cmp_report || 0);
            const trigger = Number(w.entry_price || w.resistance || 0);
            const isConfirmed = cmp >= trigger && trigger > 0;
            const diffPct = trigger > 0 ? (((cmp - trigger) / trigger) * 100).toFixed(1) : 0;
            const isRej = rejected.includes(w.id) || rejected.includes(w.symbol);

            const statusHtml = isConfirmed
                ? `<span class="trigger-badge trigger-confirmed">🔥 Breakout Confirmed</span>`
                : `<span class="trigger-badge trigger-pending">⏳ ${diffPct}% to breakout</span>`;

            let actionHtml = "";
            if (isRej) {
                actionHtml = `<button class="p2-reject-btn" onclick="unrejectP2('${w.id}')">↩️ Restore</button>`;
            } else if (isConfirmed) {
                actionHtml = `
                    <div style="display:flex;gap:6px;">
                        <button class="p2-buy-btn" onclick="openP2BuyModal('${w.symbol}', ${cmp}, ${w.suggested_stop_loss}, ${w.suggested_target}, '${w.stock_name||w.symbol}')">
                            ✅ Confirm Buy
                        </button>
                        <button class="p2-reject-btn" onclick="rejectP2('${w.id}')" title="Stop and reject this stock">🛑</button>
                    </div>`;
            } else {
                actionHtml = `
                    <div style="display:flex;gap:6px;align-items:center;">
                        <span style="font-size:11px;color:var(--text-muted);">Awaiting Trigger</span>
                        <button class="p2-reject-btn" onclick="rejectP2('${w.id}')" title="Stop and reject this stock">🛑</button>
                    </div>`;
            }

            return `
            <tr>
                <td><strong style="color:#fff;">${w.symbol}</strong><div style="font-size:11px;color:#94a3b8;">${w.stock_name || ''}</div></td>
                <td><span style="font-weight:700;color:#c084fc;">${Number(w.wyckoff_score||0).toFixed(0)}</span><span style="font-size:10px;color:#64748b;">/100</span></td>
                <td><span class="phase-badge phase-markup">${w.phase_label || 'PHASE_D'}</span></td>
                <td><strong style="color:#fff;">${fmt(cmp)}</strong></td>
                <td style="font-size:12px;">₹${Number(w.support||0).toFixed(1)} / ₹${Number(w.resistance||0).toFixed(1)}</td>
                <td>${w.spring_detected ? '<span style="color:#10b981;font-weight:700;">✓</span>' : '<span style="color:#64748b;">—</span>'}</td>
                <td>${w.sos_detected ? '<span style="color:#10b981;font-weight:700;">✓</span>' : '<span style="color:#64748b;">—</span>'}</td>
                <td><strong style="color:#38bdf8;">${fmt(trigger)}</strong></td>
                <td style="color:var(--danger);">${fmt(w.suggested_stop_loss)}</td>
                <td style="color:var(--success);">${fmt(w.suggested_target)}</td>
                <td>${statusHtml}</td>
                <td>${actionHtml}</td>
            </tr>`;
        }).join("");
    }

    if (mobileDiv) {
        mobileDiv.innerHTML = items.map(w => {
            const cmp = Number(w.current_price || w.cmp_report || 0);
            const trigger = Number(w.entry_price || w.resistance || 0);
            const isConfirmed = cmp >= trigger && trigger > 0;
            const diffPct = trigger > 0 ? (((cmp - trigger) / trigger) * 100).toFixed(1) : 0;
            const isRej = rejected.includes(w.id) || rejected.includes(w.symbol);

            return `
            <div class="stock-mobile-card ${isConfirmed ? 'card-glow-p2' : ''}" style="border-left: 3px solid ${isConfirmed ? '#10b981' : '#8b5cf6'};">
                <div class="mobile-card-top">
                    <div>
                        <span class="mobile-card-symbol">${w.symbol}</span>
                        <div class="mobile-card-name">${w.stock_name || ""}</div>
                    </div>
                    <div style="text-align:right;">
                        <span class="phase-badge phase-markup">${w.phase_label || 'PHASE_D'}</span>
                        <div style="font-size:11px;color:#c084fc;font-weight:700;margin-top:2px;">Score: ${Number(w.wyckoff_score||0).toFixed(0)}</div>
                    </div>
                </div>
                <div class="pos-card-grid">
                    <div><span class="pos-label">Live CMP</span><span style="font-weight:700;color:#fff;">${fmt(cmp)}</span></div>
                    <div><span class="pos-label">Breakout Trigger</span><span style="font-weight:700;color:#38bdf8;">${fmt(trigger)}</span></div>
                    <div><span class="pos-label">Stop-Loss (-5%)</span><span style="color:var(--danger);font-weight:600;">${fmt(w.suggested_stop_loss)}</span></div>
                    <div><span class="pos-label">Target (+20%)</span><span style="color:var(--success);font-weight:600;">${fmt(w.suggested_target)}</span></div>
                    <div style="grid-column: span 2;">
                        <span class="pos-label">Trigger Status</span>
                        ${isConfirmed ? '<span class="trigger-badge trigger-confirmed">🔥 Breakout Confirmed</span>' : `<span class="trigger-badge trigger-pending">⏳ ${diffPct}% to breakout</span>`}
                    </div>
                </div>
                <div class="mobile-card-actions" style="margin-top:10px;display:flex;gap:8px;">
                    ${isRej ? `<button class="p2-reject-btn" style="flex:1;" onclick="unrejectP2('${w.id}')">↩️ Restore</button>` :
                      isConfirmed ? `
                        <button class="p2-buy-btn" style="flex:2;" onclick="openP2BuyModal('${w.symbol}', ${cmp}, ${w.suggested_stop_loss}, ${w.suggested_target}, '${w.stock_name||w.symbol}')">✅ Confirm Buy</button>
                        <button class="p2-reject-btn" style="flex:1;" onclick="rejectP2('${w.id}')">🛑 Stop</button>
                      ` : `
                        <button class="p2-reject-btn" style="flex:1;" onclick="rejectP2('${w.id}')">🛑 Stop / Reject</button>
                      `}
                </div>
            </div>`;
        }).join("");
    }
}

// Positions
function renderPositions() {
    const items = p2State.positions || [];
    const tbody = el.positionsTableBody;
    const mobileDiv = el.positionsMobileCards;
    if (!tbody && !mobileDiv) return;

    if (!items.length) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="10" class="table-empty">No active Wyckoff swing holdings. All money is safe in cash.</td></tr>';
        if (mobileDiv) mobileDiv.innerHTML = '<div class="table-empty" style="padding:24px;text-align:center;">No active swing positions. Cash is preserved.</div>';
        return;
    }

    if (tbody) {
        tbody.innerHTML = items.map(pos => {
            const pnl = Number(pos.current_pnl || 0);
            const pnlPct = Number(pos.current_pnl_pct || 0);
            const pnlColor = pnl >= 0 ? "var(--success)" : "var(--danger)";
            const pnlSign = pnl >= 0 ? "+" : "";
            const effSL = pos.trailing_active ? pos.trailing_sl : pos.stop_loss;
            const sessions = Number(pos.sessions_held || 0);
            const sessColor = sessions >= 8 ? "var(--danger)" : sessions >= 5 ? "var(--warning)" : "var(--text-muted)";
            const trailing = pos.trailing_active
                ? `<span style="color:#10b981;font-weight:700;">🚨 Active (${fmt(pos.trailing_sl)})</span>`
                : `<span style="color:#64748b;">Inactive</span>`;

            return `
            <tr>
                <td><strong style="color:#fff;">${pos.symbol}</strong><div style="font-size:11px;color:#94a3b8;">${pos.stock_name || ''}</div></td>
                <td>${pos.quantity}</td>
                <td>${fmt(pos.buy_price)}</td>
                <td><strong style="color:#fff;">${fmt(pos.current_price || pos.buy_price)}</strong></td>
                <td style="color:var(--danger);">${fmt(effSL)}</td>
                <td style="color:var(--success);">${fmt(pos.target_price)}</td>
                <td style="color:${sessColor};font-weight:600;">${sessions}<span style="color:#64748b;font-size:11px;">/10</span></td>
                <td>${trailing}</td>
                <td style="color:${pnlColor};font-weight:700;">${pnlSign}${fmt(pnl).slice(1)} <div style="font-size:11px;">(${pnlSign}${pnlPct.toFixed(2)}%)</div></td>
                <td><button class="btn btn-sm btn-outline text-danger" onclick="closePositionManual('${pos.id}')">Close</button></td>
            </tr>`;
        }).join("");
    }

    if (mobileDiv) {
        mobileDiv.innerHTML = items.map(pos => {
            const pnl = Number(pos.current_pnl || 0);
            const pnlPct = Number(pos.current_pnl_pct || 0);
            const pnlColor = pnl >= 0 ? "var(--success)" : "var(--danger)";
            const pnlSign = pnl >= 0 ? "+" : "";
            const effSL = pos.trailing_active ? pos.trailing_sl : pos.stop_loss;
            const sessions = Number(pos.sessions_held || 0);

            return `
            <div class="stock-mobile-card" style="border-left: 3px solid ${pnlColor};">
                <div class="mobile-card-top">
                    <div>
                        <span class="mobile-card-symbol">${pos.symbol}</span>
                        <div class="mobile-card-name">${pos.stock_name || ""}</div>
                    </div>
                    <div style="text-align:right;color:${pnlColor};font-weight:700;font-size:15px;font-family:var(--font-mono);">
                        ${pnlSign}${fmt(Math.abs(pnl))}
                        <div style="font-size:11px;">${pnlSign}${pnlPct.toFixed(2)}%</div>
                    </div>
                </div>
                <div class="pos-card-grid">
                    <div><span class="pos-label">Quantity</span><span style="font-weight:600;">${pos.quantity} shares</span></div>
                    <div><span class="pos-label">Buy Price</span><span>${fmt(pos.buy_price)}</span></div>
                    <div><span class="pos-label">Live CMP</span><span style="font-weight:700;color:#fff;">${fmt(pos.current_price || pos.buy_price)}</span></div>
                    <div><span class="pos-label">Effective SL</span><span style="color:var(--danger);font-weight:600;">${fmt(effSL)}</span></div>
                    <div><span class="pos-label">Target</span><span style="color:var(--success);font-weight:600;">${fmt(pos.target_price)}</span></div>
                    <div><span class="pos-label">Sessions Held</span><span>${sessions}/10 ${pos.trailing_active ? '🚨 Trail' : ''}</span></div>
                </div>
                <div style="margin-top:10px;">
                    <button class="btn btn-sm btn-outline text-danger" style="width:100%;" onclick="closePositionManual('${pos.id}')">Manual Close at Market</button>
                </div>
            </div>`;
        }).join("");
    }
}

// Trades
function renderTrades() {
    const trades = p2State.trades || [];
    const tbody = el.tradesTableBody;
    const mobileDiv = el.tradesMobileCards;
    if (!tbody && !mobileDiv) return;

    if (!trades.length) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="9" class="table-empty">No Portfolio 2 trades recorded yet.</td></tr>';
        if (mobileDiv) mobileDiv.innerHTML = '<div class="table-empty" style="padding:24px;text-align:center;">No trades recorded yet.</div>';
        return;
    }

    const reasonLabel = { TARGET_HIT: "🎯 Target Hit (+20%)", STOP_LOSS_HIT: "🛑 Stop-Loss Hit (-5%)", TIME_STOP: "⏰ Time-Stop (10d)", TRAILING_STOP: "🚨 Trailing Stop", MANUAL: "✋ Manual Close" };

    if (tbody) {
        tbody.innerHTML = trades.map((t, i) => {
            const isBuy = t.trade_type === "BUY";
            const pnl = Number(t.pnl || 0);
            const pnlStr = !isBuy
                ? `<span style="color:${pnl>=0?'var(--success)':'var(--danger)'};font-weight:700;">${pnl>=0?'+':''}${fmt(Math.abs(pnl))}</span>`
                : `<span style="color:#64748b;">—</span>`;
            return `
            <tr>
                <td style="color:#64748b;">${t.id || i+1}</td>
                <td><span class="trade-type-badge ${isBuy?'buy':'sell'}">${t.trade_type}</span></td>
                <td><strong>${t.symbol}</strong><div style="font-size:11px;color:#94a3b8;">${t.stock_name||''}</div></td>
                <td>${fmt(t.price)}</td>
                <td>${t.quantity}</td>
                <td>${fmt(t.total_value)}</td>
                <td>${pnlStr}</td>
                <td style="font-size:12px;">${reasonLabel[t.exit_reason] || (t.exit_reason || '—')}</td>
                <td style="font-size:11px;color:#64748b;">${(t.timestamp||'').split('.')[0]}</td>
            </tr>`;
        }).join("");
    }

    if (mobileDiv) {
        mobileDiv.innerHTML = trades.map((t, i) => {
            const isBuy = t.trade_type === "BUY";
            const pnl = Number(t.pnl || 0);
            const pnlSign = pnl >= 0 ? "+" : "";
            return `
            <div class="stock-mobile-card">
                <div class="mobile-card-top">
                    <div>
                        <span class="mobile-card-symbol">${t.symbol}</span>
                        <div class="mobile-card-name">${t.stock_name || ""}</div>
                    </div>
                    <div>
                        <span class="trade-type-badge ${isBuy ? 'buy' : 'sell'}">${t.trade_type}</span>
                    </div>
                </div>
                <div class="pos-card-grid">
                    <div><span class="pos-label">Price</span><span>${fmt(t.price)}</span></div>
                    <div><span class="pos-label">Quantity</span><span>${t.quantity}</span></div>
                    <div><span class="pos-label">Total Value</span><span>${fmt(t.total_value)}</span></div>
                    <div><span class="pos-label">P&L</span><span style="color:${pnl>=0?'var(--success)':'var(--danger)'};font-weight:700;">${!isBuy ? `${pnlSign}${fmt(Math.abs(pnl))}` : '—'}</span></div>
                    <div style="grid-column: span 2;"><span class="pos-label">Reason / Date</span><span>${reasonLabel[t.exit_reason] || (t.exit_reason || '—')} · ${(t.timestamp||'').split('.')[0]}</span></div>
                </div>
            </div>`;
        }).join("");
    }
}

// Badges
function updateBadges() {
    const wlCount = (p2State.watchlist || []).length;
    const posCount = (p2State.positions || []).length;
    const trCount = (p2State.trades || []).length;

    if (el.badgeWatchlistCount) el.badgeWatchlistCount.textContent = wlCount;
    if (el.badgePositionsCount) el.badgePositionsCount.textContent = posCount;
    if (el.badgeTradesCount) el.badgeTradesCount.textContent = trCount;

    if (el.bottomBadgeWatchlist) el.bottomBadgeWatchlist.textContent = wlCount;
    if (el.bottomBadgePositions) el.bottomBadgePositions.textContent = posCount;
    if (el.bottomBadgeTrades) el.bottomBadgeTrades.textContent = trCount;
}

// Reject / Stop Actions
window.rejectP2 = function(id) {
    const rejected = getP2RejectedIds();
    if (!rejected.includes(id)) {
        rejected.push(id);
        saveP2RejectedIds(rejected);
        showToast("Stock stopped and rejected from Portfolio 2 watchlist.", "info");
        renderWatchlist();
    }
};

window.unrejectP2 = function(id) {
    let rejected = getP2RejectedIds();
    rejected = rejected.filter(x => x != id);
    saveP2RejectedIds(rejected);
    showToast("Stock restored to Portfolio 2 watchlist.", "success");
    renderWatchlist();
};

// Buy Modal
window.openP2BuyModal = function(symbol, price, sl, tgt, stockName) {
    const modal = el.modalBuy;
    if (!modal) return;
    const symInput = document.getElementById("p2-buy-symbol");
    const nameEl = document.getElementById("p2-buy-name");
    const prInput = document.getElementById("p2-buy-price");
    const slInput = document.getElementById("p2-buy-sl");
    const tgtInput = document.getElementById("p2-buy-tgt");
    const amtInput = document.getElementById("p2-buy-amount");

    const p = Number(price) || 0;
    if (symInput) symInput.value = symbol;
    if (nameEl) nameEl.textContent = stockName || symbol;
    if (prInput) prInput.value = `₹${p.toFixed(2)}`;
    if (slInput) slInput.value = `₹${Number(sl || 0).toFixed(2)}`;
    if (tgtInput) tgtInput.value = `₹${Number(tgt || 0).toFixed(2)}`;
    if (amtInput) amtInput.value = "20000";

    updateP2BuySummary();
    modal.classList.add("active");
};

window.closeP2BuyModal = function() {
    if (el.modalBuy) el.modalBuy.classList.remove("active");
};

function updateP2BuySummary() {
    const amt = parseFloat(document.getElementById("p2-buy-amount")?.value) || 0;
    const prStr = document.getElementById("p2-buy-price")?.value || "0";
    const pr = parseFloat(prStr.replace(/[^0-9.]/g, '')) || 1;
    const shares = Math.floor(amt / pr);
    const total = shares * pr;
    const summaryEl = document.getElementById("p2-buy-calc-summary");
    if (summaryEl) {
        summaryEl.innerHTML = `Estimated: ~<strong>${shares}</strong> shares @ ₹${pr.toFixed(2)} = <strong>₹${total.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>`;
    }
}

async function submitP2BuyForm(e) {
    e.preventDefault();
    const symbol = document.getElementById("p2-buy-symbol")?.value;
    const amount = parseFloat(document.getElementById("p2-buy-amount")?.value) || 20000;
    const submitBtn = document.getElementById("btn-submit-p2-buy");

    if (!symbol) return;

    if (!p2State.isLiveBackend) {
        showToast("Static Dashboard: Live paper orders require local Python engine. Buy recorded in session.", "warning");
        closeP2BuyModal();
        return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "⏳ Executing Buy..."; }

    try {
        const res = await fetch(`${API_BASE}/api/p2/actions/buy`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: symbol, position_size: amount })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(`✅ ${data.message}`, "success");
            closeP2BuyModal();
            await refreshP2Data();
        } else {
            showToast(data.detail || data.message || "Could not execute buy order.", "error");
        }
    } catch (err) {
        showToast(`Buy error: ${err.message}`, "error");
    } finally {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "✅ Confirm & Execute Buy"; }
    }
}

// Global Manual Close
window.closePositionManual = async function(posId) {
    if (!confirm("Are you sure you want to exit this swing holding at current market price?")) return;
    if (!p2State.isLiveBackend) {
        showToast("Manual close requires live Python server.", "warning");
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/api/p2/positions/${posId}/close`, { method: "POST" });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, "success");
            await refreshP2Data();
        }
    } catch (e) {
        showToast(`Close failed: ${e.message}`, "error");
    }
};

// Scan and Cycle handlers
async function runWyckoffScan() {
    const btn = el.btnScan;
    if (btn) { btn.disabled = true; btn.textContent = "⏳ Scanning Wyckoff..."; }

    if (!p2State.isLiveBackend) {
        showToast("Static Dashboard: Fresh Wyckoff scans run daily on GitHub Actions or via local server. Loaded latest saved scan results.", "warning");
        await loadP2Snapshot();
        if (btn) { btn.disabled = false; btn.textContent = "🔍 Scan Wyckoff"; }
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/p2/actions/scan`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.success) {
            showToast(`✅ ${data.message}`, "success");
            await refreshP2Data();
        } else {
            showToast(data.message || "Scan failed", "error");
        }
    } catch (e) {
        showToast(`Scan error: ${e.message}`, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "🔍 Scan Wyckoff"; }
    }
}

async function runCycle() {
    const btn = el.btnRunCycle;
    if (btn) { btn.disabled = true; btn.textContent = "⏳ Checking Cycle..."; }

    if (!p2State.isLiveBackend) {
        showToast("Static Dashboard: Automated trailing stop execution runs via GitHub Actions or local engine.", "warning");
        await loadP2Snapshot();
        if (btn) { btn.disabled = false; btn.textContent = "⚡ Run Cycle"; }
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/p2/actions/run-cycle`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ force_market_open: true })
        });
        const data = await res.json();
        const buys = data.buys_triggered?.length || 0;
        const tgts = data.targets_hit?.length || 0;
        const sls = data.stop_losses_hit?.length || 0;
        showToast(`P2 Cycle complete: ${buys} buys, ${tgts} targets, ${sls} stop-losses.`, "success");
        await refreshP2Data();
    } catch (e) {
        showToast(`Cycle error: ${e.message}`, "error");
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "⚡ Run Cycle"; }
    }
}

// Reset P2
async function resetP2() {
    if (!confirm("Are you sure you want to reset Portfolio 2 back to initial ₹1,00,000 cash balance? This will clear open swing positions.")) return;
    if (!p2State.isLiveBackend) {
        showToast("Reset is supported on the live Python terminal.", "warning");
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/api/p2/actions/reset`, { method: "POST" });
        const data = await res.json();
        if (data.success) {
            showToast("Portfolio 2 reset successfully to ₹1,00,000 cash!", "success");
            await refreshP2Data();
        }
    } catch (e) {
        showToast(`Reset failed: ${e.message}`, "error");
    }
}

// Setup Event Listeners
function initEvents() {
    // Tabs
    el.tabLinks.forEach(tab => {
        tab.addEventListener("click", () => {
            const tabId = tab.getAttribute("data-tab");
            if (tabId) switchTab(tabId);
        });
    });

    // Mobile Bottom Nav
    el.bottomNavItems.forEach(item => {
        item.addEventListener("click", () => {
            const tabId = item.getAttribute("data-tab");
            if (tabId) {
                switchTab(tabId);
                window.scrollTo({ top: 0, behavior: "smooth" });
            }
        });
    });

    // Filters
    el.filterButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            el.filterButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            p2State.activeFilter = btn.getAttribute("data-filter");
            renderWatchlist();
        });
    });

    // Search
    if (el.inputSearchWatchlist) {
        el.inputSearchWatchlist.addEventListener("input", (e) => {
            p2State.searchTerm = e.target.value.trim().toLowerCase();
            renderWatchlist();
        });
    }

    // Buttons
    el.btnRunCycle?.addEventListener("click", runCycle);
    el.btnScan?.addEventListener("click", runWyckoffScan);
    el.btnResetP2?.addEventListener("click", resetP2);

    // Buy Modal events
    document.getElementById("btn-close-p2-buy")?.addEventListener("click", closeP2BuyModal);
    document.getElementById("btn-cancel-p2-buy")?.addEventListener("click", closeP2BuyModal);
    document.getElementById("p2-buy-amount")?.addEventListener("input", updateP2BuySummary);
    document.getElementById("p2-buy-form")?.addEventListener("submit", submitP2BuyForm);

    // Settings Modal
    el.btnOpenSettings?.addEventListener("click", () => el.modalSettings?.classList.add("active"));
    document.getElementById("btn-close-settings")?.addEventListener("click", () => el.modalSettings?.classList.remove("active"));
    document.getElementById("btn-cancel-settings")?.addEventListener("click", () => el.modalSettings?.classList.remove("active"));
}

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
    initEvents();
    refreshP2Data();
    setInterval(updateClock, 1000);
    setInterval(refreshP2Data, 25000);
});
