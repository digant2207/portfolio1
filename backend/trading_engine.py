"""
Core Paper Trading Execution Engine.
Applies:
- 200 DMA + 1% Buy Trigger
- Capital management: ₹1,00,000 total, ₹10,000 per trade, Max 10 positions
- Risk management: 2% Stop Loss, 5% Minimum Target
"""
import math
from datetime import datetime
from typing import Dict, Any, List
from .config import load_config
from .database import (
    get_db, log_event, get_pending_watchlist, get_open_positions,
    get_portfolio_summary, update_watchlist_price
)
from .market_data import is_market_open, fetch_current_prices

def run_trading_cycle(force_market_open: bool = False) -> Dict[str, Any]:
    """
    Executes one trading evaluation cycle:
    1. Checks if market is open (or overridden for testing).
    2. Fetches live CMP for watchlist items and open positions.
    3. Evaluates 200 DMA + 1% buy triggers.
    4. Evaluates SL (2%) and Target (5%) exits for open positions.
    """
    cfg = load_config()
    market_open = force_market_open or is_market_open()
    
    cycle_summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market_open": market_open,
        "buys_triggered": [],
        "targets_hit": [],
        "stop_losses_hit": [],
        "errors": []
    }
    
    if not market_open:
        log_event("INFO", "Market is currently closed. Trading cycle skipped (prices not updated).")
        return cycle_summary

    # Gather all symbols we need quotes for
    pending_items = get_pending_watchlist()
    open_positions = get_open_positions()
    
    symbols_to_fetch = list(set([item["symbol"] for item in pending_items] + [pos["symbol"] for pos in open_positions]))
    if not symbols_to_fetch:
        return cycle_summary
        
    prices = fetch_current_prices(symbols_to_fetch)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Evaluate Open Positions for Exit (Stop-Loss or Target)
        for pos in open_positions:
            sym = pos["symbol"]
            cmp = prices.get(sym)
            if not cmp:
                continue
                
            qty = pos["quantity"]
            buy_price = pos["buy_price"]
            sl = pos["stop_loss"]
            target = pos["target_price"]
            pos_id = pos["id"]
            
            # Check Stop-Loss
            if cmp <= sl:
                realized_pnl = round((cmp - buy_price) * qty, 2)
                proceeds = round(cmp * qty, 2)
                
                # Close position
                cursor.execute("""
                    UPDATE positions SET 
                        status = 'CLOSED', close_price = ?, close_timestamp = CURRENT_TIMESTAMP,
                        realized_pnl = ?, exit_reason = 'STOP_LOSS_HIT'
                    WHERE id = ?
                """, (cmp, realized_pnl, pos_id))
                
                # Update portfolio cash & realized P&L
                cursor.execute("""
                    UPDATE portfolio_state SET 
                        cash_balance = cash_balance + ?,
                        realized_pnl = realized_pnl + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (proceeds, realized_pnl))
                
                # Log trade
                cursor.execute("""
                    INSERT INTO trades (
                        position_id, symbol, stock_name, trade_type, price,
                        quantity, total_value, pnl, exit_reason
                    ) VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, 'STOP_LOSS_HIT')
                """, (pos_id, sym, pos["stock_name"], cmp, qty, proceeds, realized_pnl))
                
                msg = f"🛑 STOP-LOSS HIT: Sold {qty} {sym} @ ₹{cmp} (Buy: ₹{buy_price}, P&L: ₹{realized_pnl})"
                log_event("TRADE", msg, conn=conn)
                cycle_summary["stop_losses_hit"].append({
                    "symbol": sym, "price": cmp, "buy_price": buy_price, "pnl": realized_pnl
                })
                
            # Check Target
            elif cmp >= target:
                realized_pnl = round((cmp - buy_price) * qty, 2)
                proceeds = round(cmp * qty, 2)
                
                cursor.execute("""
                    UPDATE positions SET 
                        status = 'CLOSED', close_price = ?, close_timestamp = CURRENT_TIMESTAMP,
                        realized_pnl = ?, exit_reason = 'TARGET_HIT'
                    WHERE id = ?
                """, (cmp, realized_pnl, pos_id))
                
                cursor.execute("""
                    UPDATE portfolio_state SET 
                        cash_balance = cash_balance + ?,
                        realized_pnl = realized_pnl + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (proceeds, realized_pnl))
                
                cursor.execute("""
                    INSERT INTO trades (
                        position_id, symbol, stock_name, trade_type, price,
                        quantity, total_value, pnl, exit_reason
                    ) VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, 'TARGET_HIT')
                """, (pos_id, sym, pos["stock_name"], cmp, qty, proceeds, realized_pnl))
                
                msg = f"🎯 TARGET HIT: Sold {qty} {sym} @ ₹{cmp} (Buy: ₹{buy_price}, P&L: +₹{realized_pnl})"
                log_event("TRADE", msg, conn=conn)
                cycle_summary["targets_hit"].append({
                    "symbol": sym, "price": cmp, "buy_price": buy_price, "pnl": realized_pnl
                })
            else:
                # Update current price & unrealized P&L in DB
                unrealized = round((cmp - buy_price) * qty, 2)
                cursor.execute("""
                    UPDATE positions SET current_price = ?, unrealized_pnl = ? WHERE id = ?
                """, (cmp, unrealized, pos_id))

        conn.commit()

    # Refresh portfolio state after exits
    summary = get_portfolio_summary()
    cash_avail = summary.get("cash_balance", 0.0)
    current_pos_count = summary.get("open_positions_count", 0)
    
    trade_allocation = cfg.get("trade_allocation", 10000.0)
    max_active = cfg.get("max_active_trades", 10)
    sl_pct = cfg.get("stop_loss_pct", 2.0)
    target_pct = cfg.get("target_pct", 5.0)

    # 2. Evaluate Pending Watchlist for Buy Triggers (200 DMA + 1%)
    with get_db() as conn:
        cursor = conn.cursor()
        
        for item in pending_items:
            sym = item["symbol"]
            cmp = prices.get(sym)
            if not cmp:
                continue
                
            cursor.execute("UPDATE watchlist SET current_price = ?, last_checked = CURRENT_TIMESTAMP WHERE id = ?", (cmp, item["id"]))
            trigger_price = item["trigger_price"]
            
            # Condition: CMP >= 200 DMA + 1%
            if cmp >= trigger_price:
                # Check capital & slot limit
                if current_pos_count >= max_active:
                    log_event("WARNING", f"Trigger reached for {sym} @ ₹{cmp}, but maximum {max_active} active positions already reached.", conn=conn)
                    continue
                    
                if cash_avail < trade_allocation:
                    log_event("WARNING", f"Trigger reached for {sym} @ ₹{cmp}, but insufficient cash balance (₹{cash_avail:.2f} < ₹{trade_allocation:.2f}).", conn=conn)
                    continue
                    
                qty = int(math.floor(trade_allocation / cmp))
                if qty < 1:
                    log_event("WARNING", f"Cannot buy {sym} @ ₹{cmp}: Share price exceeds allocation ₹{trade_allocation}.", conn=conn)
                    continue
                    
                invested = round(qty * cmp, 2)
                sl_price = round(cmp * (1 - (sl_pct / 100.0)), 2)
                target_price = round(cmp * (1 + (target_pct / 100.0)), 2)
                
                # Deduct cash
                cursor.execute("""
                    UPDATE portfolio_state SET 
                        cash_balance = cash_balance - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (invested,))
                
                # Mark watchlist as TRIGGERED
                cursor.execute("UPDATE watchlist SET status = 'TRIGGERED' WHERE id = ?", (item["id"],))
                
                # Insert Position
                cursor.execute("""
                    INSERT INTO positions (
                        watchlist_id, stock_name, symbol, section, buy_price,
                        quantity, invested_amount, stop_loss, target_price,
                        current_price, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
                """, (
                    item["id"], item["stock_name"], sym, item["section"], cmp,
                    qty, invested, sl_price, target_price, cmp
                ))
                pos_id = cursor.lastrowid
                
                # Insert Trade
                cursor.execute("""
                    INSERT INTO trades (
                        position_id, symbol, stock_name, trade_type, price,
                        quantity, total_value
                    ) VALUES (?, ?, ?, 'BUY', ?, ?, ?)
                """, (pos_id, sym, item["stock_name"], cmp, qty, invested))
                
                cash_avail -= invested
                current_pos_count += 1
                
                msg = f"🚀 BUY TRIGGERED: Bought {qty} shares of {sym} @ ₹{cmp} (Inv: ₹{invested}, SL: ₹{sl_price} [-2%], Tgt: ₹{target_price} [+5%])"
                log_event("TRADE", msg, conn=conn)
                cycle_summary["buys_triggered"].append({
                    "symbol": sym, "stock_name": item["stock_name"], "price": cmp, "quantity": qty, "invested": invested
                })

        conn.commit()
        
    return cycle_summary

def manual_close_position(position_id: int) -> bool:
    """Manually closes an open position at current market price."""
    with get_db() as conn:
        pos = conn.execute("SELECT * FROM positions WHERE id = ? AND status = 'OPEN'", (position_id,)).fetchone()
        if not pos:
            return False
            
        sym = pos["symbol"]
        prices = fetch_current_prices([sym])
        cmp = prices.get(sym, pos["current_price"] or pos["buy_price"])
        qty = pos["quantity"]
        buy_price = pos["buy_price"]
        
        realized_pnl = round((cmp - buy_price) * qty, 2)
        proceeds = round(cmp * qty, 2)
        
        conn.execute("""
            UPDATE positions SET 
                status = 'CLOSED', close_price = ?, close_timestamp = CURRENT_TIMESTAMP,
                realized_pnl = ?, exit_reason = 'MANUAL'
            WHERE id = ?
        """, (cmp, realized_pnl, position_id))
        
        conn.execute("""
            UPDATE portfolio_state SET 
                cash_balance = cash_balance + ?,
                realized_pnl = realized_pnl + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (proceeds, realized_pnl))
        
        conn.execute("""
            INSERT INTO trades (
                position_id, symbol, stock_name, trade_type, price,
                quantity, total_value, pnl, exit_reason
            ) VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, 'MANUAL')
        """, (position_id, sym, pos["stock_name"], cmp, qty, proceeds, realized_pnl))
        
        conn.commit()
        log_event("TRADE", f"✋ MANUAL EXIT: Closed {sym} @ ₹{cmp} (P&L: ₹{realized_pnl})")
        return True
