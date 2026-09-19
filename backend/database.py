"""
Database layer for Paper Trading using SQLite.
Stores portfolio state, daily watchlists, open positions, trade history, and logs.
"""
import sqlite3
import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from .config import DB_PATH, load_config

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    cfg = load_config()
    with get_db() as conn:
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
        
        # Initialize default portfolio if empty
        cursor.execute("SELECT COUNT(*) FROM portfolio_state")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO portfolio_state (id, total_capital, cash_balance, invested_capital, realized_pnl)
                VALUES (1, ?, ?, 0.0, 0.0)
            """, (cfg["total_capital"], cfg["total_capital"]))
            
        # Watchlist Table (Parsed from 6:00 PM email)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
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
            # Avoid duplicate on same report date for same symbol
            cursor.execute("""
                SELECT id FROM watchlist 
                WHERE report_date = ? AND symbol = ?
            """, (item["report_date"], item["symbol"]))
            if cursor.fetchone():
                continue
                
            cursor.execute("""
                INSERT INTO watchlist (
                    report_date, stock_name, symbol, section,
                    cmp_report, dma_200, trigger_price, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """, (
                item["report_date"], item["stock_name"], item["symbol"],
                item["section"], item["cmp_report"], item["dma_200"],
                item["trigger_price"]
            ))
            added += 1
        conn.commit()
    return added

def get_pending_watchlist() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM watchlist WHERE status = 'PENDING' ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

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
