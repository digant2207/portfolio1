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
    get_portfolio_summary, update_watchlist_price, get_sold_today_symbols
)
from .market_data import (
    is_market_open, fetch_current_prices, fetch_market_quotes, fetch_monthly_average_volume
)
from .notifier import notify_trade_buy, notify_trade_sell

def execute_stop_loss_exit(pos: Dict[str, Any], cmp: float, exit_reason: str = "STOP_LOSS_HIT") -> Dict[str, Any]:
    """
    Closes an open position upon hitting Stop Loss or receiving an explicit exit signal from the sheet.
    Updates position status, portfolio cash balance & realized P&L, records trade,
    and dispatches instant Telegram alert.
    """
    pos_id = pos["id"]
    sym = pos["symbol"]
    stock_name = pos["stock_name"]
    buy_price = pos["buy_price"]
    qty = pos["quantity"]
    realized_pnl = round((cmp - buy_price) * qty, 2)
    proceeds = round(cmp * qty, 2)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE positions SET 
                status = 'CLOSED', close_price = ?, close_timestamp = CURRENT_TIMESTAMP,
                realized_pnl = ?, exit_reason = ?
            WHERE id = ?
        """, (cmp, realized_pnl, exit_reason, pos_id))
        
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
            ) VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, ?)
        """, (pos_id, sym, stock_name, cmp, qty, proceeds, realized_pnl, exit_reason))

        # Mark watchlist item as TRIGGERED so it does not remain PENDING
        cursor.execute("UPDATE watchlist SET status = 'TRIGGERED' WHERE symbol = ?", (sym,))
        
        msg = f"🛑 STOP-LOSS HIT: Sold {qty} {sym} @ ₹{cmp} (Buy: ₹{buy_price}, P&L: ₹{realized_pnl})"
        log_event("TRADE", msg, conn=conn)
        conn.commit()

    try:
        notify_trade_sell({
            "symbol": sym, "stock_name": stock_name, "exit_reason": exit_reason,
            "price": cmp, "buy_price": buy_price, "quantity": qty, "pnl": realized_pnl, "proceeds": proceeds
        })
    except Exception as tg_err:
        log_event("WARNING", f"Telegram alert error on SL exit: {tg_err}")

    return {
        "symbol": sym, "price": cmp, "buy_price": buy_price, "pnl": realized_pnl
    }

def run_trading_cycle(force_market_open: bool = False) -> Dict[str, Any]:
    """
    Executes one trading evaluation cycle:
    1. Checks if market is open (or overridden for testing).
    2. Fetches live CMP for watchlist items and open positions.
    3. Evaluates 200 DMA + 1% buy triggers for mail watchlist items (both above and below 200 DMA sections).
    4. Evaluates SL (2%) and Target (5%) exits for open positions.
    5. Sends instant Telegram alerts whenever any trade occurs.
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
        
    quotes = fetch_market_quotes(symbols_to_fetch)
    prices = {s: q["price"] for s, q in quotes.items()}
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Evaluate Open Positions for Exit (Stop-Loss or Target) using High, Low, and CMP
        for pos in open_positions:
            sym = pos["symbol"]
            q = quotes.get(sym)
            if not q:
                continue

            cmp = q["price"]
            day_high = q.get("high") or cmp
            day_low = q.get("low") or cmp
            day_open = q.get("open") or cmp
                
            qty = pos["quantity"]
            buy_price = pos["buy_price"]
            sl = pos["stop_loss"]
            target = pos["target_price"]
            pos_id = pos["id"]

            # Evaluate Target and Stop-Loss conditions using CMP, Day High, and Day Low
            # (Accounts for 15-minute polling intervals where price touched target/SL intraday)
            target_reached = (cmp >= target or day_high >= target)
            sl_reached = (cmp <= sl or day_low <= sl)

            # In the rare event both are triggered on the same day:
            if target_reached and sl_reached:
                if day_open >= target:
                    target_reached, sl_reached = True, False
                elif day_open <= sl:
                    target_reached, sl_reached = False, True
                elif cmp >= buy_price:
                    target_reached, sl_reached = True, False
                else:
                    target_reached, sl_reached = False, True
            
            # Check Stop-Loss
            if sl_reached:
                exit_price = round(day_open, 2) if day_open <= sl else round(min(sl, cmp), 2)
                trade_record = execute_stop_loss_exit(pos, exit_price, exit_reason="STOP_LOSS_HIT")
                cycle_summary["stop_losses_hit"].append(trade_record)
                
            # Check Target
            elif target_reached:
                exit_price = round(day_open, 2) if day_open >= target else round(max(target, cmp), 2)
                realized_pnl = round((exit_price - buy_price) * qty, 2)
                proceeds = round(exit_price * qty, 2)
                
                cursor.execute("""
                    UPDATE positions SET 
                        status = 'CLOSED', close_price = ?, close_timestamp = CURRENT_TIMESTAMP,
                        realized_pnl = ?, exit_reason = 'TARGET_HIT'
                    WHERE id = ?
                """, (exit_price, realized_pnl, pos_id))
                
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
                """, (pos_id, sym, pos["stock_name"], exit_price, qty, proceeds, realized_pnl))

                # Mark watchlist item as TRIGGERED so it does not remain PENDING
                cursor.execute("UPDATE watchlist SET status = 'TRIGGERED' WHERE symbol = ?", (sym,))
                
                msg = f"🎯 TARGET HIT: Sold {qty} {sym} @ ₹{exit_price} (Buy: ₹{buy_price}, High: ₹{day_high}, P&L: +₹{realized_pnl})"
                log_event("TRADE", msg, conn=conn)
                
                # Instant Telegram Notification
                try:
                    notify_trade_sell({
                        "symbol": sym, "stock_name": pos["stock_name"], "exit_reason": "TARGET_HIT",
                        "price": exit_price, "buy_price": buy_price, "quantity": qty, "pnl": realized_pnl, "proceeds": proceeds
                    })
                except Exception as tg_err:
                    log_event("WARNING", f"Telegram alert error on Target exit: {tg_err}")
                    
                cycle_summary["targets_hit"].append({
                    "symbol": sym, "price": exit_price, "buy_price": buy_price, "pnl": realized_pnl
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
    min_stock_price = cfg.get("min_stock_price", 20.0)
    min_1m_avg_vol = cfg.get("min_1m_avg_volume", 10000)
    min_vol_pct = cfg.get("min_volume_pct", 50.0)
    max_buffer_pct = cfg.get("max_breakout_buffer_pct", 5.0)
    require_50_dma = cfg.get("require_above_50_dma", True)

    # 2. Evaluate Pending Watchlist for Buy Triggers (200 DMA + 1%)
    open_positions = get_open_positions()
    open_symbols = {p["symbol"] for p in open_positions}
    sold_today_symbols = get_sold_today_symbols()

    # Rule: If more than one candidate in upcoming trades, prioritize the one nearest to trigger
    def _trigger_distance(it):
        c = prices.get(it["symbol"]) or it.get("current_price") or it.get("cmp_report") or 0.0
        t = it.get("trigger_price") or 0.0
        if t > 0 and c > 0:
            return abs(c - t) / t
        return 999999.0

    pending_items.sort(key=_trigger_distance)

    with get_db() as conn:
        cursor = conn.cursor()
        
        for item in pending_items:
            # Condition 0: Only buy stocks in 'above_200_dma' section (below 200 DMA strictly excluded)
            if cfg.get("only_above_200_dma", True) and item.get("section") != "above_200_dma":
                continue

            sym = item["symbol"]
            if sym in open_symbols:
                continue

            # CRITICAL RULE: If stock was sold today, do NOT consider or buy again today!
            if sym in sold_today_symbols:
                continue

            cmp = prices.get(sym)
            if not cmp:
                continue
                
            cursor.execute("UPDATE watchlist SET current_price = ?, last_checked = CURRENT_TIMESTAMP WHERE id = ?", (cmp, item["id"]))
            
            trigger_price = item["trigger_price"]
            
            # Condition 1: CMP >= 200 DMA + 1% Breakout Trigger (or Custom Sheet Trigger)
            if cmp >= trigger_price:
                # If standard breakout (not custom sheet trigger), apply Option 4 & Option 1 filters
                if not item.get("sheet_trigger"):
                    dma_200 = float(item.get("dma_200") or 0.0)
                    dma_50 = float(item.get("dma_50") or 0.0)

                    # Option 4: Short-term trend alignment (CMP >= 50 DMA)
                    if require_50_dma and dma_50 > 0 and cmp < dma_50:
                        log_event("WARNING", f"Trigger reached for {sym} @ ₹{cmp}, but skipped: CMP is below 50 DMA (₹{dma_50}).", conn=conn)
                        continue

                    # Option 1: Fresh breakout zone (CMP <= 200 DMA + max_buffer_pct)
                    if max_buffer_pct > 0 and dma_200 > 0 and cmp > round(dma_200 * (1 + (max_buffer_pct / 100.0)), 2):
                        log_event("WARNING", f"Trigger reached for {sym} @ ₹{cmp}, but skipped: CMP (₹{cmp}) is overextended >{max_buffer_pct}% above 200 DMA (₹{dma_200}).", conn=conn)
                        continue

                # Condition 2: Filter out penny stocks / stocks with CMP <= min_stock_price (e.g. <= 20)
                if cmp <= min_stock_price:
                    log_event("WARNING", f"Trigger reached for {sym} @ ₹{cmp}, but ignored: CMP (₹{cmp}) is not greater than minimum required price ₹{min_stock_price}.", conn=conn)
                    continue
                    
                # Condition 3: Filter out illiquid stocks where 1-month avg daily volume < min_1m_avg_vol (e.g. < 10,000)
                # Use pre-stored volume from Google Sheet if available; fallback to Yahoo Finance API
                avg_vol = item.get("avg_volume_1m", 0)
                if avg_vol <= 0:
                    avg_vol = fetch_monthly_average_volume(sym)
                if avg_vol < min_1m_avg_vol:
                    log_event("WARNING", f"Trigger reached for {sym} @ ₹{cmp}, but ignored: 1-month avg volume ({int(avg_vol):,}) is below required minimum of {int(min_1m_avg_vol):,} shares.", conn=conn)
                    continue

                # Condition 3b: Filter out low volume % stocks (Today's Volume vs 1-Month Avg Volume < 50%)
                vol_pct = float(item.get("vol_pct") or 0.0)
                if min_vol_pct > 0 and vol_pct > 0 and vol_pct < min_vol_pct:
                    log_event("WARNING", f"Trigger reached for {sym} @ ₹{cmp}, but avoided: Volume % ({vol_pct}%) is below minimum required {min_vol_pct}%.", conn=conn)
                    continue
                
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
                # Stop Loss: use custom sheet_stop_loss if specified in sheet, else default 2%
                sheet_sl = item.get("sheet_stop_loss")
                if sheet_sl and float(sheet_sl) > 0:
                    sl_price = round(float(sheet_sl), 2)
                else:
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
                open_symbols.add(sym)
                
                msg = f"🚀 BUY TRIGGERED: Bought {qty} shares of {sym} @ ₹{cmp} (Inv: ₹{invested}, SL: ₹{sl_price} [-2%], Tgt: ₹{target_price} [+5%])"
                log_event("TRADE", msg, conn=conn)
                
                # Instant Telegram Notification
                try:
                    notify_trade_buy({
                        "symbol": sym, "stock_name": item["stock_name"], "section": item.get("section", "above_200_dma"),
                        "price": cmp, "quantity": qty, "invested_amount": invested,
                        "stop_loss": sl_price, "target_price": target_price
                    })
                except Exception as tg_err:
                    log_event("WARNING", f"Telegram alert error on Buy trigger: {tg_err}")
                    
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

        conn.execute("UPDATE watchlist SET status = 'TRIGGERED' WHERE symbol = ?", (sym,))
        conn.commit()
        log_event("TRADE", f"✋ MANUAL EXIT: Closed {sym} @ ₹{cmp} (P&L: ₹{realized_pnl})")
        
        # Instant Telegram Notification
        try:
            notify_trade_sell({
                "symbol": sym, "stock_name": pos["stock_name"], "exit_reason": "MANUAL",
                "price": cmp, "buy_price": buy_price, "quantity": qty,
                "pnl": realized_pnl, "proceeds": proceeds
            })
        except Exception as tg_err:
            log_event("WARNING", f"Telegram alert error on manual close: {tg_err}")
            
        return True
