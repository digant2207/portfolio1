# 📋 Portfolio 2: Wyckoff Swing Delivery Trading Plan (5–10 Days)
> **Saved on:** September 24, 2026 | **Status:** Planned & Ready to Implement Tomorrow Morning

---

## 📌 Summary of Today's Achievements & Fixes (Portfolio 1)
1. **SQLite Database Lock Resolved:**
   - Modified `execute_stop_loss_exit` to accept the caller's database connection (`conn=conn`), eliminating concurrent connection deadlocks on GitHub Actions.
2. **Fixed Premature Exits (Day's Low Bug):**
   - Removed `day_low` and `day_high` exit triggers. 
   - Exits now evaluate **strictly on Live CMP** (`cmp <= sl` and `cmp >= target`), preventing morning pre-trade wicks from falsely closing positions like VRAJ.
3. **Cleaned Up Trade History & Reconciled Capital:**
   - Removed false test trades (IDs 18–25) and duplicate KUANTUM trade (ID 13).
   - Reopened authentic positions (`VRAJ.NS`, `DCW.NS`, `AGI.NS`, `ALKYLAMINE.NS`).
   - Restored total portfolio capital to exact starting baseline of **₹1,00,000** (Current Value: **₹99,596.49** across 10 active holdings + ₹7,725.62 cash).
4. **Resilient GitHub Actions:**
   - Added `if: always()` to the commit & push step in the workflow so database updates and snapshots are never dropped.

---

## 🎯 Architecture for Portfolio 2: Wyckoff Swing Trading

### 1. Strategy Concept
- **Purpose:** Multi-day swing delivery (5 to 10 trading sessions) targeting larger institutional markup moves (**+8% to +14%**), complementing Portfolio 1's quick breakout strategy.
- **Methodology:** **Wyckoff Method & Volume Spread Analysis (VSA)** applied to candidate stocks from the Google Sheet.

### 2. Wyckoff Quantitative Screening Rules
For each candidate stock loaded from the Google Sheet, Python analyzes daily OHLCV (last 30–60 days):
1. **Accumulation Range Detection (Phase A/B):**
   - Identifies the 20–30 day support floor and resistance ceiling.
   - Verifies consolidation / base building.
2. **Volume Spread Analysis (VSA - Absorption):**
   - Down/red candles must show **declining/below-average volume** (supply exhaustion).
   - Up/green candles must show **expanding volume** (institutional demand).
3. **Phase C: Spring / Shakeout Check:**
   - Checks if price briefly dipped below range support and immediately recovered/closed back inside the range on light volume (liquidity grab).
4. **Phase D: Sign of Strength (SOS) & Breakout:**
   - Wide-range green candle closing near the high with volume $\ge 1.5\times$ 20-day average.

---

### 3. Risk & Money Management (5–10 Day Delivery)
| Parameter | Rule |
| :--- | :--- |
| **Capital Allocation** | ₹1,00,000 total capital |
| **Position Sizing** | 5 high-conviction positions @ **₹20,000 each** (or 10 @ ₹10,000) |
| **Stop-Loss** | **-3.5% to -5%** (placed below the Wyckoff Spring low or swing support) |
| **Profit Target** | **+8% to +14%** (Phase E markup) |
| **Trailing Stop** | Once gain hits **+5%**, move Stop-Loss to **Breakeven (Cost)**; trail using 10 EMA |
| **Time Stop** | If neither Target nor SL is hit after **10 trading sessions**, exit at market close |

---

### 4. Implementation Steps for Tomorrow Morning
1. **Backend:**
   - Create `backend/wyckoff_analyzer.py` to calculate Wyckoff metrics (Range, Volume Absorption score, Spring, SOS).
   - Add Portfolio 2 support in database tables (`portfolio_id = 2`).
2. **Dashboard UI:**
   - Add a clean toggle switch in `index.html` header:
     `[ Portfolio 1: 200 DMA Breakout ]`  |  `[ Portfolio 2: Wyckoff Swing Delivery ]`
   - Instantly switches metrics, open holdings, charts, and trade logs.
3. **Alerts & Reports:**
   - Tag Telegram alerts with `[PORTFOLIO 2 - WYCKOFF SWING]`.
   - Include Portfolio 2 breakdown in the daily 6:30 PM report.

---
*Ready to pick up right here tomorrow morning! Have a great evening.*
