"""
Database layer for Paper Trading using SQLite.
Stores portfolio state, daily watchlists, open positions, trade history, and logs.
"""
import sqlite3
import json
import math
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from .config import get_db_path, load_config

_DB_INITIALIZED = False

def _setup_tables(conn):
    cursor = conn.cursor()
    # Portfolio Summary Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_state (
            id INTEGER PRIMARY KEY,
            total_capital REAL NOT NULL,
            cash_balance REAL NOT NULL,
            invested_capital REAL NOT NULL,
            realized_pnl REAL NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Watchlist Table (Parsed from Google Sheets or manual entry)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            section TEXT NOT NULL,          -- 'above_200_dma' or 'below_200_dma'
            cmp_report REAL NOT NULL,
            dma_200 REAL NOT NULL,
            trigger_price REAL NOT NULL,    -- 200 DMA + 1%
            status TEXT DEFAULT 'PENDING',  -- 'PENDING', 'TRIGGERED', 'EXPIRED', 'SKIPPED'
            current_price REAL,
            last_checked TIMESTAMP,
            golden_cross INTEGER DEFAULT 0, -- 1 if confirmed Golden Cross from Sheet 2
            avg_volume_1m REAL DEFAULT 0,   -- 1-month avg volume from Google Sheet
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Migration: add golden_cross and avg_volume_1m columns if missing (existing DBs)
    try:
        cursor.execute("ALTER TABLE watchlist ADD COLUMN golden_cross INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE watchlist ADD COLUMN avg_volume_1m REAL DEFAULT 0")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE watchlist ADD COLUMN sheet_trigger REAL DEFAULT NULL")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE watchlist ADD COLUMN sheet_stop_loss REAL DEFAULT NULL")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE watchlist ADD COLUMN sheet_stop_loss_raw TEXT DEFAULT NULL")
    except Exception:
        pass
    
    # Open / Closed Positions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watchlist_id INTEGER,
            stock_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            section TEXT NOT NULL,
            buy_price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            invested_amount REAL NOT NULL,
            stop_loss REAL NOT NULL,        -- buy_price * 0.98 (-2%)
            target_price REAL NOT NULL,     -- buy_price * 1.05 (+5%)
            buy_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            current_price REAL,
            unrealized_pnl REAL DEFAULT 0.0,
            status TEXT DEFAULT 'OPEN',     -- 'OPEN', 'CLOSED'
            close_price REAL,
            close_timestamp TIMESTAMP,
            realized_pnl REAL DEFAULT 0.0,
            exit_reason TEXT                -- 'TARGET_HIT', 'STOP_LOSS_HIT', 'MANUAL'
        )
    """)
    
    # Trades execution log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER,
            symbol TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            trade_type TEXT NOT NULL,       -- 'BUY', 'SELL'
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            total_value REAL NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pnl REAL DEFAULT 0.0,
            exit_reason TEXT
        )
    """)
    
    # System activity & audit logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,            -- 'INFO', 'WARNING', 'ERROR', 'TRADE'
            message TEXT NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Notification deduplication tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            notification_type TEXT NOT NULL,  -- 'EVENING_WATCHLIST', 'DAILY_SUMMARY'
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details TEXT
        )
    """)
    conn.commit()

def get_db():
    global _DB_INITIALIZED
    conn = sqlite3.connect(get_db_path(), timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.row_factory = sqlite3.Row
    if not _DB_INITIALIZED:
        _DB_INITIALIZED = True
        _setup_tables(conn)
    return conn

def init_db():
    cfg = load_config()
    with get_db() as conn:
        cursor = conn.cursor()
        # Initialize default portfolio if empty
        cursor.execute("SELECT COUNT(*) FROM portfolio_state")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO portfolio_state (id, total_capital, cash_balance, invested_capital, realized_pnl)
                VALUES (1, ?, ?, 0.0, 0.0)
            """, (cfg["total_capital"], cfg["total_capital"]))
            conn.commit()

def is_notification_sent(report_date: str, notification_type: str) -> bool:
    """Checks if a specific notification has already been dispatched on the given date."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT id FROM sent_notifications 
            WHERE report_date = ? AND notification_type = ?
        """, (report_date, notification_type)).fetchone()
        return row is not None

def record_notification_sent(report_date: str, notification_type: str, details: str = ""):
    """Records that a notification has been dispatched for the date to prevent duplicates."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO sent_notifications (report_date, notification_type, details)
            VALUES (?, ?, ?)
        """, (report_date, notification_type, details))
        conn.commit()

def log_event(level: str, message: str, details: Any = None, conn: Optional[sqlite3.Connection] = None):
    try:
        dtls = json.dumps(details) if isinstance(details, (dict, list)) else (str(details) if details else None)
        if conn:
            conn.execute("INSERT INTO logs (level, message, details) VALUES (?, ?, ?)", (level, message, dtls))
        else:
            with get_db() as c:
                c.execute("INSERT INTO logs (level, message, details) VALUES (?, ?, ?)", (level, message, dtls))
                c.commit()
    except Exception as e:
        print(f"Failed to write log: {e}")

def get_portfolio_summary() -> Dict[str, Any]:
    with get_db() as conn:
        state = conn.execute("SELECT * FROM portfolio_state WHERE id = 1").fetchone()
        if not state:
            return {}
            
        # Get active positions to compute live invested capital & unrealized P&L
        positions = conn.execute("SELECT * FROM positions WHERE status = 'OPEN'").fetchall()
        
        total_invested = sum(p["invested_amount"] for p in positions)
        current_market_val_positions = sum((p["current_price"] or p["buy_price"]) * p["quantity"] for p in positions)
        unrealized_pnl = sum((((p["current_price"] or p["buy_price"]) - p["buy_price"]) * p["quantity"]) for p in positions)
        
        cash = state["cash_balance"]
        total_val = cash + current_market_val_positions
        realized_pnl = state["realized_pnl"]
        
        # Update state row with live total_invested
        conn.execute("UPDATE portfolio_state SET invested_capital = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (total_invested,))
        conn.commit()
        
        return {
            "initial_capital": state["total_capital"],
            "cash_balance": round(cash, 2),
            "invested_capital": round(total_invested, 2),
            "positions_market_value": round(current_market_val_positions, 2),
            "total_portfolio_value": round(total_val, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_pnl": round(realized_pnl + unrealized_pnl, 2),
            "total_return_pct": round(((total_val - state["total_capital"]) / state["total_capital"]) * 100, 2),
            "open_positions_count": len(positions)
        }

def reset_portfolio():
    cfg = load_config()
    with get_db() as conn:
        conn.execute("UPDATE portfolio_state SET cash_balance = ?, invested_capital = 0, realized_pnl = 0 WHERE id = 1", (cfg["total_capital"],))
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM trades")
        conn.execute("DELETE FROM watchlist")
        conn.commit()
    log_event("WARNING", "Portfolio has been reset to initial capital ₹1,00,000")

def add_watchlist_items(items: List[Dict[str, Any]]) -> int:
    added = 0
    with get_db() as conn:
        cursor = conn.cursor()
        for item in items:
            avg_vol = float(item.get("avg_volume_1m") or 0.0)

            sheet_trig = item.get("sheet_trigger")
            sheet_sl = item.get("sheet_stop_loss")
            sheet_sl_raw = item.get("sheet_stop_loss_raw")

            # Update existing or insert new
            cursor.execute("""
                SELECT id FROM watchlist 
                WHERE report_date = ? AND symbol = ?
            """, (item["report_date"], item["symbol"]))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE watchlist SET
                        avg_volume_1m = CASE WHEN ? > 0 THEN ? ELSE avg_volume_1m END,
                        golden_cross = CASE WHEN ? = 1 THEN 1 ELSE golden_cross END,
                        cmp_report = ?,
                        dma_200 = ?,
                        trigger_price = ?,
                        sheet_trigger = ?,
                        sheet_stop_loss = ?,
                        sheet_stop_loss_raw = ?
                    WHERE id = ?
                """, (
                    avg_vol, avg_vol,
                    1 if item.get("golden_cross") else 0,
                    item["cmp_report"], item["dma_200"], item["trigger_price"],
                    sheet_trig, sheet_sl, sheet_sl_raw,
                    row["id"]
                ))
                continue
                
            cursor.execute("""
                INSERT INTO watchlist (
                    report_date, stock_name, symbol, section,
                    cmp_report, dma_200, trigger_price, status,
                    golden_cross, avg_volume_1m,
                    sheet_trigger, sheet_stop_loss, sheet_stop_loss_raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?)
            """, (
                item["report_date"], item["stock_name"], item["symbol"],
                item["section"], item["cmp_report"], item["dma_200"],
                item["trigger_price"],
                1 if item.get("golden_cross") else 0,
                avg_vol,
                sheet_trig, sheet_sl, sheet_sl_raw
            ))
            added += 1
        conn.commit()
    return added

def update_position_stop_loss(position_id: int, stop_loss: float):
    with get_db() as conn:
        conn.execute("UPDATE positions SET stop_loss = ? WHERE id = ?", (round(stop_loss, 2), position_id))
        conn.commit()

def get_pending_watchlist() -> List[Dict[str, Any]]:
    cfg = load_config()
    min_price = cfg.get("min_stock_price", 20.0)
    min_volume = cfg.get("min_1m_avg_volume", 10000.0)
    only_above = cfg.get("only_above_200_dma", True)
    with get_db() as conn:
        section_clause = "AND section = 'above_200_dma'" if only_above else ""
        query = f"""
            SELECT * FROM watchlist 
            WHERE status = 'PENDING' 
              {section_clause}
              AND cmp_report > ?
              AND (avg_volume_1m >= ? OR avg_volume_1m = 0)
            ORDER BY id ASC
        """
        rows = conn.execute(query, (min_price, min_volume)).fetchall()
        return [dict(r) for r in rows]

def get_nearest_breakout_candidates(limit: int = 10, min_price: float = None, min_volume: float = None) -> List[Dict[str, Any]]:
    """
    Returns candidate stocks sorted by proximity to their 200 DMA + 1% breakout trigger.
    Strictly filters out penny stocks (CMP <= min_price) and illiquid stocks (1-month avg volume < min_volume).
    Filters only 'above_200_dma' when only_above_200_dma is active.
    """
    cfg = load_config()
    if min_price is None:
        min_price = cfg.get("min_stock_price", 20.0)
    if min_volume is None:
        min_volume = cfg.get("min_1m_avg_volume", 10000.0)
    only_above = cfg.get("only_above_200_dma", True)

    with get_db() as conn:
        section_clause = "AND section = 'above_200_dma'" if only_above else ""
        rows = conn.execute(f"SELECT * FROM watchlist WHERE status = 'PENDING' {section_clause}").fetchall()
        candidates = []
        for r in rows:
            item = dict(r)
            cmp = item.get("current_price") or item.get("cmp_report", 0.0)
            item["current_price"] = cmp
            trig = item.get("trigger_price", 0.0)
            avg_vol = float(item.get("avg_volume_1m") or 0.0)
            
            # 1. Filter penny stocks & invalid trigger prices
            if cmp <= min_price or trig <= 0:
                continue
                
            # 2. Filter low volume stocks (< 10,000 shares 1-month avg volume)
            if avg_vol > 0 and avg_vol < min_volume:
                continue
            elif avg_vol <= 0:
                # Check simulated/cached market_data table
                sim_vol = None
                try:
                    md_row = conn.execute("SELECT volume FROM market_data WHERE symbol = ?", (item["symbol"],)).fetchone()
                    if md_row and md_row["volume"]:
                        sim_vol = float(md_row["volume"])
                except Exception:
                    pass
                    
                if sim_vol is not None:
                    if sim_vol < min_volume:
                        continue
                    avg_vol = sim_vol
                    item["avg_volume_1m"] = avg_vol
                else:
                    # In live mode without volume data, skip unverified stock
                    continue
                
            diff_pct = round(((trig - cmp) / trig) * 100, 2)
            abs_dist = round(abs(trig - cmp) / trig * 100, 2)
            prox_pct = round((cmp / trig) * 100, 1)
            is_crossed = cmp >= trig
            
            item["distance_pct"] = diff_pct
            item["abs_distance_pct"] = abs_dist
            item["proximity_pct"] = prox_pct
            item["is_crossed"] = is_crossed
            item["proximity_status"] = f"CROSSING (+{abs(diff_pct):.2f}% Above Trigger)" if is_crossed else f"APPROACHING ({diff_pct:.2f}% to Trigger)"
            candidates.append(item)
            
        # Sort by nearest to breakout trigger (smallest absolute distance)
        candidates.sort(key=lambda x: x["abs_distance_pct"])
        return candidates[:limit]

def get_all_watchlist(limit: int = 50) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM watchlist ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def update_watchlist_price(watchlist_id: int, current_price: float):
    with get_db() as conn:
        conn.execute("""
            UPDATE watchlist 
            SET current_price = ?, last_checked = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (current_price, watchlist_id))
        conn.commit()

def get_open_positions() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM positions WHERE status = 'OPEN' ORDER BY id DESC").fetchall()
        result = []
        for r in rows:
            pos = dict(r)
            cmp = pos["current_price"] or pos["buy_price"]
            pos["current_pnl"] = round((cmp - pos["buy_price"]) * pos["quantity"], 2)
            pos["current_pnl_pct"] = round(((cmp - pos["buy_price"]) / pos["buy_price"]) * 100, 2)
            pos["current_value"] = round(cmp * pos["quantity"], 2)
            result.append(pos)
        return result

def get_trades(limit: int = 50) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_logs(limit: int = 60) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def update_watchlist_status(watchlist_id: int, status: str) -> bool:
    """Updates the status of a watchlist stock (e.g. 'REJECTED', 'PENDING')."""
    with get_db() as conn:
        row = conn.execute("SELECT symbol, stock_name, status FROM watchlist WHERE id = ?", (watchlist_id,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE watchlist SET status = ? WHERE id = ?", (status, watchlist_id))
        conn.commit()
        log_event("INFO", f"Watchlist stock {row['symbol']} status changed from {row['status']} to {status}", conn=conn)
        return True

def get_today_trades() -> List[Dict[str, Any]]:
    """Returns trades executed on the current date."""
    today_prefix = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM trades 
            WHERE timestamp LIKE ? OR date(timestamp) = date('now', 'localtime')
            ORDER BY id DESC
        """, (f"{today_prefix}%",)).fetchall()
        return [dict(r) for r in rows]

def get_upcoming_trades(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Returns screened watchlist items that are candidates for upcoming buy triggers.
    Includes both PENDING and REJECTED items so the user can see and toggle their status.
    Calculates proximity percentage and distance to trigger price.
    """
    cfg = load_config()
    trade_alloc = cfg.get("trade_allocation", 10000.0)
    only_above = cfg.get("only_above_200_dma", True)
    with get_db() as conn:
        section_clause = "AND section = 'above_200_dma'" if only_above else ""
        query = f"""
            SELECT * FROM watchlist 
            WHERE status IN ('PENDING', 'REJECTED')
              {section_clause}
            ORDER BY id DESC
        """
        rows = conn.execute(query).fetchall()
        items = []
        for r in rows:
            it = dict(r)
            cmp = it.get("current_price") or it.get("cmp_report") or 0.0
            trig = it.get("trigger_price") or 0.0
            
            diff_pct = round(((trig - cmp) / trig) * 100, 2) if trig > 0 else 0.0
            abs_dist = round(abs(trig - cmp) / trig * 100, 2) if trig > 0 else 0.0
            prox_pct = round((cmp / trig) * 100, 1) if trig > 0 else 0.0
            is_crossed = cmp >= trig if trig > 0 else False
            
            est_qty = int(math.floor(trade_alloc / cmp)) if cmp > 0 else 0
            
            it["distance_pct"] = diff_pct
            it["abs_distance_pct"] = abs_dist
            it["proximity_pct"] = prox_pct
            it["is_crossed"] = is_crossed
            it["est_quantity"] = est_qty
            it["est_allocation"] = trade_alloc
            items.append(it)
            
        # Sort so ready stocks come first, sorted by nearest to breakout trigger
        items.sort(key=lambda x: (x["status"] == "REJECTED", x["abs_distance_pct"]))
        return items[:limit]

def export_portfolio_snapshot(export_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Exports a comprehensive JSON snapshot of the portfolio state.
    Used for GitHub Pages and static mobile dashboards.
    """
    from pathlib import Path
    from .config import BASE_DIR
    summary = get_portfolio_summary()
    positions = get_open_positions()
    today_trades = get_today_trades()
    all_trades = get_trades(limit=100)
    upcoming = get_upcoming_trades(limit=100)
    
    today_realized_pnl = sum(t.get("pnl", 0.0) for t in today_trades if t.get("trade_type") == "SELL")
    
    snapshot = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "portfolio": {
            **summary,
            "today_realized_pnl": round(today_realized_pnl, 2),
            "today_trades_count": len(today_trades)
        },
        "positions": positions,
        "today_trades": today_trades,
        "all_trades": all_trades,
        "upcoming_trades": upcoming
    }
    
    target_paths = [
        BASE_DIR / "data" / "portfolio_snapshot.json",
        BASE_DIR / "frontend" / "portfolio_snapshot.json",
        BASE_DIR / "portfolio_snapshot.json"
    ]
    if export_path:
        target_paths.append(Path(export_path))
        
    for p in target_paths:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
        except Exception as e:
            print(f"Warning writing snapshot to {p}: {e}")
            
    return snapshot

