"""
FastAPI REST API server for the Paper Trading Terminal.
Provides control endpoints and serves the modern dashboard.
"""
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from .config import load_config, save_config, BASE_DIR
from .database import (
    init_db, get_portfolio_summary, get_all_watchlist, get_open_positions,
    get_trades, get_logs, reset_portfolio, add_watchlist_items, log_event,
    update_watchlist_status, get_today_trades, get_upcoming_trades, export_portfolio_snapshot
)
from .market_data import get_market_status, simulate_price_update
from .sheet_reader import fetch_and_process_sheets, clean_sheet_symbol
from .mail_reader import parse_email_html_or_text, clean_symbol
from .trading_engine import run_trading_cycle, manual_close_position
from .notifier import generate_daily_report_html, send_daily_email_report
from .scheduler import start_scheduler, stop_scheduler

FRONTEND_DIR = BASE_DIR / "frontend"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    try:
        start_scheduler()
    except Exception as e:
        print(f"Scheduler startup warning: {e}")
    yield
    # Shutdown
    stop_scheduler()

app = FastAPI(title="Smart Money Paper Trading Terminal", lifespan=lifespan)

# Pydantic Schemas
class SettingsUpdate(BaseModel):
    gmail_user: Optional[str] = None
    gmail_app_password: Optional[str] = None
    notification_recipient: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    google_sheet_id: Optional[str] = None
    google_sheet_id_1: Optional[str] = None
    google_sheet_id_2: Optional[str] = None
    total_capital: Optional[float] = None
    trade_allocation: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    target_pct: Optional[float] = None
    trigger_buffer_pct: Optional[float] = None
    min_stock_price: Optional[float] = None
    min_1m_avg_volume: Optional[int] = None
    simulate_market_hours: Optional[bool] = None

class RawMailInput(BaseModel):
    content: str
    is_html: bool = True

class ManualStockInput(BaseModel):
    stock_name: str
    section: str = "above_200_dma"  # 'above_200_dma' or 'below_200_dma'
    cmp_report: float
    dma_200: float

class StatusUpdateInput(BaseModel):
    status: str  # 'PENDING' or 'REJECTED'

class SimulatePriceInput(BaseModel):
    symbol: str
    price: float

# API Endpoints
@app.get("/api/status")
def get_status():
    cfg = load_config()
    m_status = get_market_status()
    has_credentials = bool(cfg.get("gmail_user") and cfg.get("gmail_app_password"))
    return {
        "market": m_status,
        "gmail_configured": has_credentials,
        "gmail_user": cfg.get("gmail_user", ""),
        "simulate_market_hours": cfg.get("simulate_market_hours", False)
    }

@app.get("/api/portfolio")
def api_get_portfolio():
    return get_portfolio_summary()

@app.get("/api/portfolio/snapshot")
def api_get_snapshot():
    return export_portfolio_snapshot()

@app.get("/api/watchlist")
def api_get_watchlist():
    return get_all_watchlist(limit=100)

@app.get("/api/trades/upcoming")
def api_get_upcoming_trades(limit: int = 100):
    return get_upcoming_trades(limit=limit)

@app.post("/api/watchlist/{watchlist_id}/reject")
def api_reject_watchlist(watchlist_id: int):
    success = update_watchlist_status(watchlist_id, "REJECTED")
    if not success:
        raise HTTPException(status_code=404, detail="Watchlist stock not found.")
    export_portfolio_snapshot()
    return {"success": True, "status": "REJECTED", "message": f"Upcoming trade {watchlist_id} stopped/rejected. Buying skipped."}

@app.post("/api/watchlist/{watchlist_id}/restore")
def api_restore_watchlist(watchlist_id: int):
    success = update_watchlist_status(watchlist_id, "PENDING")
    if not success:
        raise HTTPException(status_code=404, detail="Watchlist stock not found.")
    export_portfolio_snapshot()
    return {"success": True, "status": "PENDING", "message": f"Upcoming trade {watchlist_id} restored to pending."}

@app.post("/api/watchlist/{watchlist_id}/status")
def api_update_watchlist_status(watchlist_id: int, payload: StatusUpdateInput):
    st = payload.status.upper()
    if st not in ("PENDING", "REJECTED", "SKIPPED"):
        raise HTTPException(status_code=400, detail="Invalid status. Must be PENDING or REJECTED.")
    success = update_watchlist_status(watchlist_id, st)
    if not success:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    export_portfolio_snapshot()
    return {"success": True, "status": st, "message": f"Stock status updated to {st}."}

@app.post("/api/watchlist")
def api_add_manual_watchlist(item: ManualStockInput):
    cfg = load_config()
    buffer_pct = cfg.get("trigger_buffer_pct", 1.0)
    sym = clean_symbol(item.stock_name)
    trigger = round(item.dma_200 * (1 + (buffer_pct / 100.0)), 2)
    from datetime import datetime
    new_item = [{
        "report_date": datetime.now().strftime("%Y-%m-%d"),
        "stock_name": item.stock_name,
        "symbol": sym,
        "section": item.section,
        "cmp_report": item.cmp_report,
        "dma_200": item.dma_200,
        "trigger_price": trigger
    }]
    count = add_watchlist_items(new_item)
    log_event("INFO", f"Manually added {sym} to watchlist (Trigger: ₹{trigger})")
    export_portfolio_snapshot()
    return {"success": True, "added": count, "symbol": sym, "trigger_price": trigger}

@app.get("/api/positions")
def api_get_positions():
    return get_open_positions()

@app.post("/api/positions/{position_id}/close")
def api_close_position(position_id: int):
    success = manual_close_position(position_id)
    if not success:
        raise HTTPException(status_code=404, detail="Open position not found or already closed.")
    export_portfolio_snapshot()
    return {"success": True, "message": f"Position {position_id} successfully closed."}

@app.get("/api/trades")
def api_get_trades():
    return get_trades(limit=100)

@app.get("/api/trades/today")
def api_get_today_trades():
    trades = get_today_trades()
    realized = sum(t.get("pnl", 0.0) for t in trades if t.get("trade_type") == "SELL")
    return {"trades": trades, "count": len(trades), "realized_pnl": round(realized, 2)}

@app.get("/api/logs")
def api_get_logs():
    return get_logs(limit=50)

@app.get("/api/settings")
def api_get_settings():
    cfg = load_config()
    # Mask secrets
    masked = cfg.copy()
    if masked.get("gmail_app_password"):
        masked["gmail_app_password"] = "••••••••••••••••"
    if masked.get("telegram_bot_token"):
        masked["telegram_bot_token"] = "••••••••••••••••"
    return masked

@app.post("/api/settings")
def api_save_settings(settings: SettingsUpdate):
    data = {k: v for k, v in settings.model_dump().items() if v is not None}
    if data.get("gmail_app_password") == "••••••••••••••••":
        del data["gmail_app_password"]
    if data.get("telegram_bot_token") == "••••••••••••••••":
        del data["telegram_bot_token"]
    saved = save_config(data)
    log_event("INFO", "Settings updated successfully.")
    return {"success": True, "settings": saved}

@app.post("/api/actions/test-telegram")
def api_test_telegram():
    from .notifier import send_telegram_message
    from datetime import datetime
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    test_msg = (
        "🤖 <b>Paper Trading Terminal - Telegram Test</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>Telegram connection verified successfully!</b>\n"
        f"⏰ <b>Time:</b> {time_str}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>You will receive instant alerts for every Buy order, Target (+5%), and Stop-Loss (-2%) exit.</i>"
    )
    success, msg = send_telegram_message(test_msg)
    return {"success": success, "message": msg}

@app.post("/api/actions/fetch-mail")
def api_action_fetch_sheets():
    """Fetches watchlist data from Google Sheets (replaces Gmail IMAP)."""
    success, msg, items = fetch_and_process_sheets()
    export_portfolio_snapshot()
    return {"success": success, "message": msg, "count": len(items), "items": items}

@app.post("/api/actions/parse-raw-mail")
def api_action_parse_raw_mail(payload: RawMailInput):
    content = payload.content
    parsed = parse_email_html_or_text(content if payload.is_html else "", content if not payload.is_html else "")
    if not parsed:
        return {"success": False, "message": "Could not identify stock records in the provided text/HTML.", "count": 0}
    added = add_watchlist_items(parsed)
    log_event("INFO", f"Parsed {len(parsed)} stocks from manual report input. {added} added to watchlist.")
    export_portfolio_snapshot()
    return {"success": True, "message": f"Successfully parsed {len(parsed)} stocks ({added} added).", "count": len(parsed), "items": parsed}

@app.post("/api/actions/run-cycle")
def api_action_run_cycle(force_market_open: bool = Body(False, embed=True)):
    res = run_trading_cycle(force_market_open=force_market_open)
    export_portfolio_snapshot()
    return {"success": True, "summary": res}

@app.post("/api/actions/simulate-price")
def api_simulate_price(data: SimulatePriceInput):
    simulate_price_update(data.symbol, data.price)
    return {"success": True, "message": f"Simulated price of {data.symbol} set to ₹{data.price}"}

@app.get("/api/actions/preview-daily-report", response_class=HTMLResponse)
def api_preview_daily_report():
    subject, html, _ = generate_daily_report_html()
    return HTMLResponse(content=html)

@app.post("/api/actions/send-daily-report")
def api_send_daily_report():
    success, msg = send_daily_email_report()
    return {"success": success, "message": msg}

@app.get("/api/actions/preview-watchlist-report", response_class=HTMLResponse)
def api_preview_watchlist_report():
    from .notifier import generate_evening_watchlist_html
    from .database import get_pending_watchlist
    items = get_pending_watchlist()
    subject, html = generate_evening_watchlist_html(items)
    return HTMLResponse(content=html)

@app.post("/api/actions/send-watchlist-report")
def api_send_watchlist_report():
    from .notifier import send_evening_watchlist_email, notify_evening_watchlist_telegram
    from .database import get_pending_watchlist
    items = get_pending_watchlist()
    success, msg = send_evening_watchlist_email(items)
    if items:
        notify_evening_watchlist_telegram(items)
    return {"success": success, "message": msg}

@app.post("/api/actions/reset-portfolio")
def api_reset_portfolio():
    reset_portfolio()
    export_portfolio_snapshot()
    return {"success": True, "message": "Portfolio has been reset to ₹1,00,000 baseline."}

# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/styles.css")
def serve_styles():
    p = FRONTEND_DIR / "styles.css"
    if p.exists():
        return FileResponse(p, media_type="text/css")
    raise HTTPException(status_code=404)

@app.get("/app.js")
def serve_app_js():
    p = FRONTEND_DIR / "app.js"
    if p.exists():
        return FileResponse(p, media_type="application/javascript")
    raise HTTPException(status_code=404)

@app.get("/portfolio_snapshot.json")
@app.get("/data/portfolio_snapshot.json")
def serve_snapshot():
    p = BASE_DIR / "data" / "portfolio_snapshot.json"
    if p.exists():
        return FileResponse(p, media_type="application/json")
    return export_portfolio_snapshot()

@app.get("/")
def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Paper Trading API active. Frontend index.html not found."}
