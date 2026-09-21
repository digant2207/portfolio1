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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.database import init_db, reset_portfolio, get_portfolio_summary, get_open_positions, get_trades, get_all_watchlist
from backend.mail_reader import parse_email_html_or_text, add_watchlist_items
from backend.trading_engine import run_trading_cycle
from backend.market_data import simulate_price_update, simulate_volume_update
from backend.notifier import generate_daily_report_html

def test_full_pipeline():
    print("--- 1. Initializing DB & Resetting Portfolio ---")
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
    
    assert len(items) == 5, f"Expected 5 parsed items, got {len(items)}"
    tatamotors = next(i for i in items if "TATAMOTORS" in i["symbol"])
    assert tatamotors["trigger_price"] == 969.60, f"Expected 969.60, got {tatamotors['trigger_price']}"
    
    added = add_watchlist_items(items)
    assert added == 5, f"Expected 5 added to DB, got {added}"
    print(f"[OK] Watchlist successfully populated with {added} stocks.")

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

    print("\n--- 5. Testing Stop Loss Exit (-2%) ---")
    # Trigger buy for HDFCBANK: trigger is 1650 * 1.01 = 1666.50 -> set price to Rs. 1670.00
    simulate_price_update("HDFCBANK.NS", 1670.00)
    cycle3 = run_trading_cycle(force_market_open=True)
    assert len(cycle3["buys_triggered"]) == 1
    
    pos_hdb = get_open_positions()[0]
    print(f"  * Bought {pos_hdb['symbol']} @ Rs. {pos_hdb['buy_price']}, SL is Rs. {pos_hdb['stop_loss']}")
    
    # Simulate drop below Stop Loss (1670 * 0.98 = 1636.60) -> drop to Rs. 1630.00
    simulate_price_update("HDFCBANK.NS", 1630.00)
    cycle4 = run_trading_cycle(force_market_open=True)
    assert len(cycle4["stop_losses_hit"]) == 1, "Expected stop loss exit"
    print(f"[OK] Stop Loss Hit properly handled! Exit details: {cycle4['stop_losses_hit'][0]}")

    print("\n--- 6. Testing Daily Summary Email Generation ---")
    subject, html_report, summ = generate_daily_report_html()
    assert "Smart Money Paper Trading Report" in html_report
    assert "Active Open Holdings" in html_report
    assert "Today's Executed Trades" in html_report
    print(f"[OK] Generated Email Subject: '{subject}'")
    print(f"[OK] Email HTML Body generated ({len(html_report)} bytes)")

    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_full_pipeline()
