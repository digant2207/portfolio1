"""
Automated validation script for Smart Money 200 DMA Paper Trading Engine.
"""
import os
import sys
from pathlib import Path

# Fix Windows console encoding for UTF-8
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# CRITICAL: Isolate test database so test runs never overwrite data/portfolio.db
TEST_DB_PATH = BASE_DIR / "data" / "test_portfolio.db"
if TEST_DB_PATH.exists():
    try:
        TEST_DB_PATH.unlink()
    except Exception:
        pass
os.environ["PORTFOLIO_DB_PATH"] = str(TEST_DB_PATH)
# CRITICAL: Disable live external notifications so test trades (TATAMOTORS, HDFCBANK) never spam user's Telegram/Email
os.environ["MOCK_NOTIFICATIONS"] = "1"

from backend.database import init_db, reset_portfolio, get_portfolio_summary, get_open_positions, get_trades, get_all_watchlist
from backend.mail_reader import parse_email_html_or_text, add_watchlist_items
from backend.trading_engine import run_trading_cycle
from backend.market_data import simulate_price_update, simulate_volume_update
from backend.notifier import generate_daily_report_html

def test_full_pipeline():
    print("--- 1. Initializing DB & Resetting Portfolio (Isolated Test DB) ---")
    init_db()
    reset_portfolio()
    p0 = get_portfolio_summary()
    assert p0["cash_balance"] == 100000.0, f"Expected 100k cash, got {p0['cash_balance']}"
    assert p0["open_positions_count"] == 0
    print(f"[OK] Initial Portfolio: Rs. {p0['total_portfolio_value']:,.2f} Cash: Rs. {p0['cash_balance']:,.2f}")

    print("\n--- 2. Testing Email Report Parsing ---")
    sample_email = """
    <html>
    <body>
        <h2>Daily smart money finder report</h2>
        <h3>Best for buy above 200 dma</h3>
        <table>
            <tr><th>Stock Name</th><th>CMP</th><th>200 DMA</th></tr>
            <tr><td>TATAMOTORS</td><td>970.00</td><td>960.00</td></tr>
            <tr><td>RELIANCE</td><td>2950.00</td><td>2900.00</td></tr>
            <tr><td>INFOSYS</td><td>1850.00</td><td>1800.00</td></tr>
            <tr><td>PENNYCORP</td><td>15.00</td><td>14.00</td></tr>
            <tr><td>LOWVOLCORP</td><td>150.00</td><td>140.00</td></tr>
        </table>

        <h3>Best for sell below 200 dma</h3>
        <table>
            <tr><th>Stock Name</th><th>CMP</th><th>200 DMA</th></tr>
            <tr><td>HDFCBANK</td><td>1640.00</td><td>1650.00</td></tr>
        </table>
    </body>
    </html>
    """
    items = parse_email_html_or_text(sample_email)
    print(f"Extracted {len(items)} items from sample email:")
    for it in items:
        print(f"  * {it['symbol']} | Section: {it['section']} | CMP: Rs. {it['cmp_report']} | 200 DMA: Rs. {it['dma_200']} | Buy Trigger: Rs. {it['trigger_price']}")
    
    assert len(items) == 5, f"Expected 5 parsed above_200_dma items (below_200_dma filtered out), got {len(items)}"
    tatamotors = next(i for i in items if "TATAMOTORS" in i["symbol"])
    assert tatamotors["trigger_price"] == 969.60, f"Expected 969.60, got {tatamotors['trigger_price']}"
    
    added = add_watchlist_items(items)
    assert added == 5, f"Expected 5 added to DB, got {added}"
    print(f"[OK] Watchlist successfully populated with {added} stocks (all above 200 DMA).")

    print("\n--- 3. Testing CMP > 20 and Volume > 10,000 Filter Execution ---")
    # Simulate prices & volumes
    simulate_price_update("TATAMOTORS.NS", 975.00)  # > 969.60 trigger, > 20 CMP, volume 50,000 -> Should BUY
    simulate_volume_update("TATAMOTORS.NS", 50000)

    simulate_price_update("RELIANCE.NS", 2910.00)    # < 2929.00 trigger -> Should NOT buy
    simulate_volume_update("RELIANCE.NS", 200000)

    simulate_price_update("PENNYCORP.NS", 16.00)   # > 14.14 trigger BUT CMP <= 20 -> Should IGNORE
    simulate_volume_update("PENNYCORP.NS", 100000)

    simulate_price_update("LOWVOLCORP.NS", 145.00) # > 141.40 trigger, CMP > 20 BUT volume < 10000 (5000) -> Should IGNORE
    simulate_volume_update("LOWVOLCORP.NS", 5000)

    simulate_price_update("HDFCBANK.NS", 1645.00)   # < 1666.50 trigger -> Should NOT buy
    simulate_volume_update("HDFCBANK.NS", 80000)
    
    cycle1 = run_trading_cycle(force_market_open=True)
    print(f"Cycle 1 Result: {len(cycle1['buys_triggered'])} buys triggered.")
    assert len(cycle1['buys_triggered']) == 1, f"Expected exactly 1 buy (TATAMOTORS), got {len(cycle1['buys_triggered'])}"
    assert cycle1['buys_triggered'][0]['symbol'] == 'TATAMOTORS.NS'
    print("[OK] Penny stock (CMP <= 20) and Low Volume (< 10,000) properly ignored!")
    
    positions1 = get_open_positions()
    assert len(positions1) == 1, f"Expected 1 position, got {len(positions1)}"
    pos = positions1[0]
    print(f"  * Open Position: {pos['symbol']} | Qty: {pos['quantity']} | Buy Price: Rs. {pos['buy_price']} | Invested: Rs. {pos['invested_amount']} | SL: Rs. {pos['stop_loss']} | Target: Rs. {pos['target_price']}")
    
    assert pos["invested_amount"] <= 10000.0
    assert pos["stop_loss"] == 955.50
    assert pos["target_price"] == 1023.75
    print("[OK] Position sizing (Rs. 10,000 allocation), 2% Stop Loss, and 5% Target validated!")

    print("\n--- 4. Testing Target Exit (+5%) ---")
    # Simulate TATAMOTORS price surging to Rs. 1025.00 (exceeds target 1023.75)
    simulate_price_update("TATAMOTORS.NS", 1025.00)
    cycle2 = run_trading_cycle(force_market_open=True)
    assert len(cycle2["targets_hit"]) == 1, f"Expected 1 target hit, got {len(cycle2['targets_hit'])}"
    
    positions2 = get_open_positions()
    assert len(positions2) == 0, "Expected position to be closed after target hit"
    
    p2 = get_portfolio_summary()
    assert p2["realized_pnl"] > 0, f"Expected positive realized P&L, got {p2['realized_pnl']}"
    print(f"[OK] Target Hit! Realized Profit: Rs. {p2['realized_pnl']:,.2f} | Total Capital: Rs. {p2['total_portfolio_value']:,.2f}")

    print("\n--- 5. Testing 'Below 200 DMA' Exclusion & Stop-Loss (-2%) Exit ---")
    # 5a. Verify that a below_200_dma item is strictly ignored and NOT bought even if price crosses trigger
    add_watchlist_items([{
        "report_date": "2026-09-23",
        "stock_name": "HDFCBANK",
        "symbol": "HDFCBANK.NS",
        "section": "below_200_dma",
        "cmp_report": 1640.0,
        "dma_200": 1650.0,
        "trigger_price": 1666.50
    }])
    simulate_price_update("HDFCBANK.NS", 1675.00) # Crossed trigger!
    simulate_volume_update("HDFCBANK.NS", 80000)
    cycle_below = run_trading_cycle(force_market_open=True)
    assert len(cycle_below["buys_triggered"]) == 0, "below_200_dma stock must NOT be bought!"
    print("[OK] Below 200 DMA stocks are strictly excluded from buying!")

    # 5b. Buy an eligible above_200_dma stock (INFY.NS) to test Stop-Loss (-2%)
    simulate_price_update("INFY.NS", 1825.00) # > 1818.00 trigger
    simulate_volume_update("INFY.NS", 100000)
    cycle3 = run_trading_cycle(force_market_open=True)
    assert len(cycle3["buys_triggered"]) == 1, f"Expected 1 buy for INFY.NS, got {len(cycle3['buys_triggered'])}"
    assert cycle3["buys_triggered"][0]["symbol"] == "INFY.NS"
    
    pos_infy = get_open_positions()[0]
    print(f"  * Bought {pos_infy['symbol']} (above 200 DMA) @ Rs. {pos_infy['buy_price']}, SL is Rs. {pos_infy['stop_loss']}")
    assert pos_infy["section"] == "above_200_dma"
    
    # Simulate drop below Stop Loss (1825 * 0.98 = 1788.50) -> drop to Rs. 1780.00
    simulate_price_update("INFY.NS", 1780.00)
    cycle4 = run_trading_cycle(force_market_open=True)
    assert len(cycle4["stop_losses_hit"]) == 1, "Expected stop loss exit"
    print(f"[OK] Stop Loss Exit properly handled! Details: {cycle4['stop_losses_hit'][0]}")

    print("\n--- 6. Testing Telegram Alert Formatter ---")
    from backend.notifier import send_telegram_message
    # Test telegram message formatting (returns False gracefully if credentials not configured, no crash)
    ok, msg = send_telegram_message("🤖 Test message from automated test suite")
    print(f"[OK] Telegram notifier executed safely (Status: {ok}, Message: '{msg}')")

    print("\n--- 7. Testing Daily Summary Email Generation ---")
    subject, html_report, summ = generate_daily_report_html()
    assert "Smart Money Paper Trading Report" in html_report
    assert "Active Open Holdings" in html_report
    assert "Today's Executed Trades" in html_report
    print(f"[OK] Generated Email Subject: '{subject}'")
    print(f"[OK] Email HTML Body generated ({len(html_report)} bytes)")

    print("\n--- 8. Testing Tomorrow's Candidate List (Top 10) Report ---")
    from backend.notifier import generate_evening_watchlist_html, notify_evening_watchlist_telegram
    w_subject, w_html = generate_evening_watchlist_html(items)
    assert "Tomorrow's Candidate Watchlist" in w_subject
    assert "Top 6" in w_subject or "Top" in w_subject
    assert "TATAMOTORS" in w_html
    assert "RELIANCE" in w_html
    print(f"[OK] Candidate List Email Subject: '{w_subject}'")
    print(f"[OK] Candidate List HTML Body generated ({len(w_html)} bytes)")

    print("\n--- 9. Testing Option 1 (Max 5% Breakout Cap) and Option 4 (CMP >= 50 DMA) Filters ---")
    from backend.sheet_reader import parse_combined_sheet
    test_csv = (
        "Symbol,Stock Name,Current Price (₹),200 DMA (₹),50 DMA (₹),1 Month Avg Volume,Trigger,Stop Loss\n"
        "OVEREXT.NS,Overextended Corp,112.00,100.00,98.00,50000,,\n"        # +12% over 200 DMA (>5%) -> Reject (Option 1)
        "BELOW50.NS,Below 50 DMA Corp,102.00,100.00,106.00,50000,,\n"        # Below 50 DMA (102 < 106) -> Reject (Option 4)
        "FRESH.NS,Fresh Breakout Corp,103.00,100.00,101.00,50000,,\n"        # <=105 & >=101 -> ACCEPT!
        "CUSTOM.NS,Custom Trigger Corp,120.00,100.00,95.00,50000,122.00,\n"   # Explicit trigger overrides -> ACCEPT!
    )
    parsed = parse_combined_sheet(test_csv)
    parsed_symbols = {p["symbol"] for p in parsed}
    print(f"Parsed candidates count: {len(parsed)}: {parsed_symbols}")
    assert "FRESH.NS" in parsed_symbols, "FRESH.NS should pass both Option 1 and Option 4"
    assert "CUSTOM.NS" in parsed_symbols, "CUSTOM.NS with explicit Trigger should bypass 5% cap"
    assert "OVEREXT.NS" not in parsed_symbols, "OVEREXT.NS (>5% above 200 DMA) must be filtered out by Option 1"
    assert "BELOW50.NS" not in parsed_symbols, "BELOW50.NS (< 50 DMA) must be filtered out by Option 4"
    print("[OK] parse_combined_sheet successfully applies Option 1 and Option 4 screening!")

    # Verify live engine behavior with Option 1 & 4
    add_watchlist_items(parsed)
    simulate_price_update("FRESH.NS", 103.50)  # > 101.00 trigger, <= 105.00 (within 5% cap), >= 101 50 DMA
    simulate_volume_update("FRESH.NS", 50000)
    cycle5 = run_trading_cycle(force_market_open=True)
    fresh_buys = [b for b in cycle5["buys_triggered"] if b["symbol"] == "FRESH.NS"]
    assert len(fresh_buys) == 1, "FRESH.NS should trigger buy"
    print(f"[OK] Live engine successfully bought fresh breakout stock {fresh_buys[0]['symbol']} @ Rs. {fresh_buys[0]['price']}!")

    print("\n--- 10. Testing Live CMP Target Exit & Sold-Today Exclusion Rule ---")
    from backend.database import get_sold_today_symbols, get_upcoming_trades, get_pending_watchlist
    # 10a. Simulate price reaching 109.00 (exceeds target ~108.68)
    simulate_price_update("FRESH.NS", target_price=109.00)
    cycle6 = run_trading_cycle(force_market_open=True)
    assert len(cycle6["targets_hit"]) == 1, "Expected FRESH.NS to exit via Live CMP >= target"
    assert cycle6["targets_hit"][0]["symbol"] == "FRESH.NS"
    print(f"[OK] Position successfully exited via Live CMP check: {cycle6['targets_hit'][0]}")

    # 10b. Verify Sold-Today Exclusion: FRESH.NS was sold today and must NOT be considered for the rest of today
    sold_today = get_sold_today_symbols()
    assert "FRESH.NS" in sold_today, "FRESH.NS must be registered in sold_today_symbols"
    assert not any(u["symbol"] == "FRESH.NS" for u in get_upcoming_trades()), "FRESH.NS must not appear in upcoming trades today"
    assert not any(p["symbol"] == "FRESH.NS" for p in get_pending_watchlist()), "FRESH.NS must not appear in pending watchlist today"

    # 10c. Simulate cycle again — FRESH.NS must NOT be re-bought today even if CMP > trigger
    simulate_price_update("FRESH.NS", target_price=103.50)
    cycle7 = run_trading_cycle(force_market_open=True)
    rebuys = [b for b in cycle7["buys_triggered"] if b["symbol"] == "FRESH.NS"]
    assert len(rebuys) == 0, "FRESH.NS must NOT be re-bought on the same day it was sold!"
    print("[OK] Sold-Today Exclusion strictly verified: sold stock is never re-bought on the same day!")

    print("\n--- 11. Testing Volume % Filter (>= 50%) & Choosing Nearest-to-Trigger First ---")
    vol_test_csv = (
        "Symbol,Stock Name,Current Price (₹),200 DMA (₹),50 DMA (₹),1 Month Avg Volume,Vol. %,Trigger,Stop Loss\n"
        "LOWVOLPCT.NS,Low Vol Pct Corp,102.00,100.00,101.00,50000,25.0%,,\n"   # Vol % = 25% (< 50%) -> AVOID!
        "NEAR.NS,Near Trigger Corp,101.20,100.00,100.50,50000,75.0%,,\n"        # Vol % = 75%, Trig = 101.0, Dist = 0.20%
        "FAR.NS,Far Trigger Corp,104.80,100.00,100.50,50000,80.0%,,\n"          # Vol % = 80%, Trig = 101.0, Dist = 3.76%
    )
    vol_parsed = parse_combined_sheet(vol_test_csv)
    vol_parsed_symbols = {p["symbol"] for p in vol_parsed}
    print(f"Parsed Volume % test candidates: {vol_parsed_symbols}")
    assert "LOWVOLPCT.NS" not in vol_parsed_symbols, "LOWVOLPCT.NS (<50% Vol. %) must be avoided/rejected!"
    assert "NEAR.NS" in vol_parsed_symbols, "NEAR.NS (>= 50% Vol. %) must be accepted!"
    assert "FAR.NS" in vol_parsed_symbols, "FAR.NS (>= 50% Vol. %) must be accepted!"
    print("[OK] Volume % Filter strictly verified: stocks with Vol. % < 50% are avoided!")

    add_watchlist_items(vol_parsed)
    upcoming_list = get_upcoming_trades()
    upcoming_syms = [u["symbol"] for u in upcoming_list if u["symbol"] in ("NEAR.NS", "FAR.NS")]
    assert len(upcoming_syms) == 2, f"Expected 2 upcoming stocks, got {len(upcoming_syms)}"
    assert upcoming_syms[0] == "NEAR.NS" and upcoming_syms[1] == "FAR.NS", f"Expected NEAR.NS first (nearest to trigger), got {upcoming_syms}"
    print(f"[OK] Upcoming trades ranking strictly verified: {upcoming_syms[0]} (nearer to trigger) appears first!")

    # Verify execution priority: set prices so both NEAR.NS and FAR.NS trigger
    simulate_price_update("NEAR.NS", 101.20)
    simulate_price_update("FAR.NS", 104.80)
    # Temporarily restrict cash so only 1 stock can be bought
    from backend.database import get_db
    with get_db() as conn:
        conn.execute("UPDATE portfolio_state SET cash_balance = 12000.0 WHERE id = 1")
        conn.commit()

    cycle8 = run_trading_cycle(force_market_open=True)
    assert len(cycle8["buys_triggered"]) == 1, f"Expected exactly 1 buy due to cash constraint, got {len(cycle8['buys_triggered'])}"
    assert cycle8["buys_triggered"][0]["symbol"] == "NEAR.NS", f"Expected NEAR.NS to be chosen first, got {cycle8['buys_triggered'][0]['symbol']}"
    print(f"[OK] Buy execution priority strictly verified: {cycle8['buys_triggered'][0]['symbol']} (nearest to trigger) was chosen first!")

    # Clean up test DB
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass

    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_full_pipeline()
