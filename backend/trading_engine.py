"""
Core Paper Trading Execution Engine.
Applies:
- 200 DMA + 1% Buy Trigger
- Capital management: ₹1,00,000 total, ₹10,000 per trade, Max 10 positions
- Risk management: 2% Stop Loss, 5% Minimum Target
"""
import math
from datetime import datetime
from typing import Dict, Any, List, Optional
from .config import load_config
from .database import (
    get_db, log_event, get_pending_watchlist, get_open_positions,
    get_portfolio_summary, update_watchlist_price, get_sold_today_symbols,
    get_p2_open_positions, get_p2_portfolio_summary, get_p2_watchlist,
    export_p2_snapshot, export_portfolio_snapshot
)
from .market_data import (
    is_market_open, fetch_current_prices, fetch_market_quotes, fetch_monthly_average_volume
)
from .notifier import (
    notify_trade_buy, notify_trade_sell, notify_p2_buy, notify_p2_sell
)

def execute_stop_loss_exit(pos: Dict[str, Any], cmp: float, exit_reason: str = "STOP_LOSS_HIT", conn: Optional[Any] = None) -> Dict[str, Any]:
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

    own_conn = False
    if conn is None:
        conn = get_db()
        own_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE positions SET 
                status = 'CLOSED', close_price = ?, close_timestamp = CURRENT_TIMESTAMP,
                realized_pnl = ?, exit_reason = ?
            WHERE id = ? AND status = 'OPEN'
        """, (cmp, realized_pnl, exit_reason, pos_id))
        
        if cursor.rowcount == 0:
            return {
                "symbol": sym, "price": cmp, "buy_price": buy_price, "pnl": realized_pnl, "already_closed": True
            }
        
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
    finally:
        if own_conn:
            conn.close()

    try:
        notify_trade_sell({
            "symbol": sym, "stock_name": stock_name, "exit_reason": exit_reason,
            "price": cmp, "buy_price": buy_price, "quantity": qty, "pnl": realized_pnl, "proceeds": proceeds
        })
    except Exception as tg_err:
        log_event("WARNING", f"Telegram alert error on SL exit: {tg_err}", conn=conn if not own_conn else None)

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
            try:
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

                # Evaluate Target and Stop-Loss conditions strictly based on Live CMP
                # (Day Low / High are excluded because Day Low reflects prices from before the position was opened)
                target_reached = (cmp >= target)
                sl_reached = (cmp <= sl)

                # In the rare event both are triggered on the same check:
                if target_reached and sl_reached:
                    if cmp >= buy_price:
                        target_reached, sl_reached = True, False
                    else:
                        target_reached, sl_reached = False, True
                
                # Check Stop-Loss
                if sl_reached:
                    trade_record = execute_stop_loss_exit(pos, cmp, exit_reason="STOP_LOSS_HIT", conn=conn)
                    cycle_summary["stop_losses_hit"].append(trade_record)
                    
                # Check Target
                elif target_reached:
                    exit_price = cmp
                    realized_pnl = round((exit_price - buy_price) * qty, 2)
                    proceeds = round(exit_price * qty, 2)
                    
                    cursor.execute("""
                        UPDATE positions SET 
                            status = 'CLOSED', close_price = ?, close_timestamp = CURRENT_TIMESTAMP,
                            realized_pnl = ?, exit_reason = 'TARGET_HIT'
                        WHERE id = ? AND status = 'OPEN'
                    """, (exit_price, realized_pnl, pos_id))
                    
                    if cursor.rowcount == 0:
                        continue
                    
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
                    
                    msg = f"🎯 TARGET HIT: Sold {qty} {sym} @ ₹{exit_price} (Buy: ₹{buy_price}, P&L: +₹{realized_pnl})"
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
            except Exception as pos_err:
                log_event("ERROR", f"Error evaluating position {pos.get('symbol')}: {pos_err}", conn=conn)
                cycle_summary["errors"].append(str(pos_err))

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


# ============================================================================
# PORTFOLIO 2: WYCKOFF SWING DELIVERY TRADING ENGINE (5–10 DAYS)
# ============================================================================

def execute_p2_buy(candidate: Dict[str, Any], cmp: float, conn: Optional[Any] = None, position_size: float = 20000.0) -> Optional[Dict[str, Any]]:
    """
    Executes a high-conviction delivery buy for Portfolio 2 based on Wyckoff VSA signals.
    - Sizing: ₹20,000 per position (5 max for ₹1,00,000 capital)
    - Stop-Loss: below Spring low / swing support (-3.5% to -5.0%)
    - Target: Phase E markup (+8% to +14%)
    - Trailing stop trigger: +5%
    """
    sym = candidate.get("symbol", "")
    stock_name = candidate.get("stock_name") or sym
    if not sym or cmp <= 0:
        return None

    own_conn = False
    if conn is None:
        conn = get_db()
        own_conn = True

    try:
        cursor = conn.cursor()

        # Check if already open in P2
        open_pos = cursor.execute("SELECT id FROM p2_positions WHERE symbol = ? AND status = 'OPEN'", (sym,)).fetchone()
        if open_pos:
            return None

        # Check total open positions count in P2
        open_count_row = cursor.execute("SELECT COUNT(*) FROM p2_positions WHERE status = 'OPEN'").fetchone()
        open_count = open_count_row[0] if open_count_row else 0
        if open_count >= 5:
            return None

        # Check P2 cash balance
        p2_state = cursor.execute("SELECT * FROM portfolio_state WHERE id = 2").fetchone()
        if not p2_state:
            return None
        cash = float(p2_state["cash_balance"])

        alloc = min(position_size, cash)
        if alloc < 5000 or cmp > alloc:
            return None

        quantity = int(alloc // cmp)
        if quantity <= 0:
            return None

        invested = round(quantity * cmp, 2)
        sl = candidate.get("suggested_stop_loss") or round(cmp * (1 - (candidate.get("sl_pct") or 3.5) / 100), 2)
        tgt = candidate.get("suggested_target") or round(cmp * (1 + (candidate.get("target_pct") or 8.0) / 100), 2)
        sl_pct = candidate.get("sl_pct") or round(((cmp - sl) / cmp) * 100, 1)
        tgt_pct = candidate.get("target_pct") or round(((tgt - cmp) / cmp) * 100, 1)
        score = candidate.get("wyckoff_score", 0.0)
        phase = candidate.get("phase_label", "PHASE_D_MARKUP")
        wl_id = candidate.get("id")

        # Insert position
        cursor.execute("""
            INSERT INTO p2_positions (
                p2_watchlist_id, stock_name, symbol, buy_price, quantity, invested_amount,
                stop_loss, target_price, sl_pct, target_pct, trailing_active, trailing_sl,
                sessions_held, wyckoff_score, phase_label, current_price, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, 'OPEN')
        """, (
            wl_id, stock_name, sym, cmp, quantity, invested,
            sl, tgt, sl_pct, tgt_pct, sl, score, phase, cmp
        ))
        pos_id = cursor.lastrowid

        # Deduct cash & update invested capital
        cursor.execute("""
            UPDATE portfolio_state SET
                cash_balance = cash_balance - ?,
                invested_capital = invested_capital + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 2
        """, (invested, invested))

        # Insert BUY into p2_trades
        cursor.execute("""
            INSERT INTO p2_trades (
                position_id, symbol, stock_name, trade_type, price, quantity, total_value
            ) VALUES (?, ?, ?, 'BUY', ?, ?, ?)
        """, (pos_id, sym, stock_name, cmp, quantity, invested))

        # Update watchlist status
        cursor.execute("UPDATE p2_watchlist SET status = 'TRIGGERED' WHERE symbol = ?", (sym,))

        if own_conn:
            conn.commit()

        trade_info = {
            "position_id": pos_id, "symbol": sym, "stock_name": stock_name,
            "price": cmp, "quantity": quantity, "invested_amount": invested,
            "stop_loss": sl, "target_price": tgt, "sl_pct": sl_pct,
            "target_pct": tgt_pct, "wyckoff_score": score, "phase_label": phase
        }
        log_event("TRADE", f"🌊 [P2 BUY] {sym}: {quantity} shares @ ₹{cmp:.2f} (Total: ₹{invested:.2f}) | Target: ₹{tgt:.2f} (+{tgt_pct}%), SL: ₹{sl:.2f} (-{sl_pct}%)", conn=conn)

        try:
            notify_p2_buy(trade_info)
        except Exception as e:
            print(f"[!] Warning sending P2 buy Telegram notification: {e}")

        return trade_info

    except Exception as e:
        if own_conn:
            conn.rollback()
        log_event("ERROR", f"Failed to execute P2 buy for {sym}: {e}", conn=conn if not own_conn else None)
        return None
    finally:
        if own_conn:
            conn.close()


def execute_p2_sell(pos: Dict[str, Any], cmp: float, exit_reason: str, conn: Optional[Any] = None) -> Dict[str, Any]:
    """
    Exits an open Portfolio 2 position on Target hit, Stop-Loss, Trailing Stop, Time-Stop, or Manual.
    """
    pos_id = pos["id"]
    sym = pos["symbol"]
    stock_name = pos.get("stock_name", sym)
    buy_price = pos["buy_price"]
    qty = pos["quantity"]
    sessions = pos.get("sessions_held", 0)

    realized_pnl = round((cmp - buy_price) * qty, 2)
    proceeds = round(cmp * qty, 2)

    own_conn = False
    if conn is None:
        conn = get_db()
        own_conn = True

    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE p2_positions SET
                status = 'CLOSED', close_price = ?, close_timestamp = CURRENT_TIMESTAMP,
                realized_pnl = ?, exit_reason = ?
            WHERE id = ? AND status = 'OPEN'
        """, (cmp, realized_pnl, exit_reason, pos_id))

        if cursor.rowcount == 0:
            return {"symbol": sym, "already_closed": True}

        # Credit cash and update realized PnL
        cursor.execute("""
            UPDATE portfolio_state SET
                cash_balance = cash_balance + ?,
                realized_pnl = realized_pnl + ?,
                invested_capital = invested_capital - ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 2
        """, (proceeds, realized_pnl, pos["invested_amount"]))

        # Log to p2_trades
        cursor.execute("""
            INSERT INTO p2_trades (
                position_id, symbol, stock_name, trade_type, price,
                quantity, total_value, pnl, exit_reason
            ) VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, ?)
        """, (pos_id, sym, stock_name, cmp, qty, proceeds, realized_pnl, exit_reason))

        if own_conn:
            conn.commit()

        trade_info = {
            "position_id": pos_id, "symbol": sym, "stock_name": stock_name,
            "price": cmp, "buy_price": buy_price, "quantity": qty,
            "pnl": realized_pnl, "proceeds": proceeds, "exit_reason": exit_reason,
            "sessions_held": sessions
        }
        sign = "+" if realized_pnl >= 0 else ""
        log_event("TRADE", f"🌊 [P2 SELL] {sym} exited @ ₹{cmp:.2f} ({exit_reason}): P&L {sign}₹{realized_pnl:.2f}", conn=conn)

        try:
            notify_p2_sell(trade_info)
        except Exception as e:
            print(f"[!] Warning sending P2 sell notification: {e}")

        return trade_info

    except Exception as e:
        if own_conn:
            conn.rollback()
        log_event("ERROR", f"Failed to execute P2 sell for {sym}: {e}")
        return {"symbol": sym, "error": str(e)}
    finally:
        if own_conn:
            conn.close()


def manual_close_p2_position(position_id: int) -> bool:
    """Manually closes an open Portfolio 2 position from dashboard or API."""
    with get_db() as conn:
        pos = conn.execute("SELECT * FROM p2_positions WHERE id = ? AND status = 'OPEN'", (position_id,)).fetchone()
        if not pos:
            return False
        sym = pos["symbol"]
        prices = fetch_current_prices([sym])
        cmp = prices.get(sym, pos["current_price"] or pos["buy_price"])
        res = execute_p2_sell(dict(pos), cmp, exit_reason="MANUAL", conn=conn)
        export_p2_snapshot()
        export_portfolio_snapshot()
        return not res.get("already_closed") and "error" not in res


def run_p2_trading_cycle(force_market_open: bool = False, max_positions: int = 5, position_size: float = 20000.0) -> Dict[str, Any]:
    """
    Executes a complete Portfolio 2 Wyckoff Swing Delivery cycle:
    1. Checks exits on active open positions (Target, Stop-Loss, Trailing Stop, Time-Stop).
    2. Updates Trailing Stop triggers for winning positions (+5% profit activates breakeven/trail).
    3. Fills empty slots (up to 5 positions) with highest-ranked Wyckoff candidates.
    4. Updates database, snapshots, and alerts.
    """
    if not force_market_open and not is_market_open():
        return {
            "status": "MARKET_CLOSED",
            "message": "Market is currently closed (IST 09:15 - 15:30 Mon-Fri). Use force_market_open=True to test.",
            "buys_triggered": [], "targets_hit": [], "stop_losses_hit": []
        }

    with get_db() as conn:
        open_pos_rows = conn.execute("SELECT * FROM p2_positions WHERE status = 'OPEN'").fetchall()
        open_positions = [dict(r) for r in open_pos_rows]
        open_symbols = [p["symbol"] for p in open_positions]

        # Fetch live prices for open positions
        open_quotes = fetch_current_prices(open_symbols) if open_symbols else {}

        buys = []
        targets_hit = []
        stop_losses_hit = []

        # 1. Evaluate open positions for Exits & Trailing Stops
        for pos in open_positions:
            sym = pos["symbol"]
            cmp = open_quotes.get(sym) or pos["current_price"] or pos["buy_price"]
            buy_price = pos["buy_price"]
            target_price = pos["target_price"]
            stop_loss = pos["stop_loss"]
            trailing_active = bool(pos["trailing_active"])
            trailing_sl = pos["trailing_sl"] if pos["trailing_sl"] > 0 else stop_loss
            sessions = pos.get("sessions_held", 0)

            # Update live CMP
            conn.execute(
                "UPDATE p2_positions SET current_price = ?, unrealized_pnl = ? WHERE id = ?",
                (cmp, round((cmp - buy_price) * pos["quantity"], 2), pos["id"])
            )

            # Check Trailing Stop Activation (+5% gain)
            gain_pct = ((cmp - buy_price) / buy_price) * 100 if buy_price > 0 else 0.0
            if gain_pct >= 5.0 and not trailing_active:
                trailing_active = True
                trailing_sl = max(stop_loss, buy_price)  # move to breakeven
                conn.execute(
                    "UPDATE p2_positions SET trailing_active = 1, trailing_sl = ? WHERE id = ?",
                    (trailing_sl, pos["id"])
                )
                log_event("TRADE", f"🌊 [P2 TRAILING ACTIVE] {sym} reached +{gain_pct:.1f}%! Stop-Loss moved to breakeven ₹{trailing_sl:.2f}")

            # Advance Trailing Stop if CMP moves higher (+8% or more)
            if trailing_active and gain_pct >= 8.0:
                trail_candidate = round(cmp * 0.96, 2)  # 4% trailing cushion
                if trail_candidate > trailing_sl:
                    trailing_sl = trail_candidate
                    conn.execute("UPDATE p2_positions SET trailing_sl = ? WHERE id = ?", (trailing_sl, pos["id"]))
                    log_event("TRADE", f"🌊 [P2 TRAIL UPDATED] {sym} trailing SL raised to ₹{trailing_sl:.2f}")

            effective_sl = trailing_sl if trailing_active else stop_loss

            # Check Exits: Target Hit
            if cmp >= target_price:
                res = execute_p2_sell(pos, cmp, exit_reason="TARGET_HIT", conn=conn)
                targets_hit.append(res)
                continue

            # Check Exits: Stop Loss Hit / Trailing Stop Hit
            if cmp <= effective_sl:
                exit_reason = "TRAILING_STOP" if trailing_active else "STOP_LOSS_HIT"
                res = execute_p2_sell(pos, cmp, exit_reason=exit_reason, conn=conn)
                stop_losses_hit.append(res)
                continue

            # Check Exits: Time Stop (10 trading sessions without reaching target or SL)
            if sessions >= 10:
                res = execute_p2_sell(pos, cmp, exit_reason="TIME_STOP", conn=conn)
                stop_losses_hit.append(res)
                continue

        conn.commit()

        # 2. Check for New Buys if slots are available (< max_positions)
        current_open_count = conn.execute("SELECT COUNT(*) FROM p2_positions WHERE status = 'OPEN'").fetchone()[0]
        slots_available = max_positions - current_open_count

        if slots_available > 0:
            # Fetch highest scoring Wyckoff candidates that are still PENDING
            candidates = conn.execute("""
                SELECT * FROM p2_watchlist
                WHERE status = 'PENDING'
                  AND symbol NOT IN (SELECT symbol FROM p2_positions WHERE status = 'OPEN')
                ORDER BY wyckoff_score DESC
                LIMIT 20
            """).fetchall()

            candidate_dicts = [dict(c) for c in candidates]
            candidate_symbols = [c["symbol"] for c in candidate_dicts]
            candidate_quotes = fetch_current_prices(candidate_symbols) if candidate_symbols else {}

            for cand in candidate_dicts:
                if slots_available <= 0:
                    break
                sym = cand["symbol"]
                cmp = candidate_quotes.get(sym) or cand.get("cmp_report") or cand.get("entry_price")
                entry_price = cand.get("entry_price") or cmp

                # Validate entry range: CMP shouldn't be stretched more than +3% above calculated entry
                if cmp <= entry_price * 1.03:
                    trade = execute_p2_buy(cand, cmp, conn=conn, position_size=position_size)
                    if trade:
                        buys.append(trade)
                        slots_available -= 1

        conn.commit()

    export_p2_snapshot()
    export_portfolio_snapshot()

    summary = {
        "status": "SUCCESS",
        "buys_triggered": buys,
        "targets_hit": targets_hit,
        "stop_losses_hit": stop_losses_hit,
        "message": f"Portfolio 2 cycle complete: {len(buys)} buys, {len(targets_hit)} targets, {len(stop_losses_hit)} exits."
    }
    return summary
