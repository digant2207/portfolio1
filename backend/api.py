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
    get_trades, get_logs, reset_portfolio, add_watchlist_items, log_event
)
from .market_data import get_market_status, simulate_price_update
from .mail_reader import fetch_and_parse_gmail_report, parse_email_html_or_text, clean_symbol
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
    email_report_subject: Optional[str] = None
    notification_recipient: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
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

@app.get("/api/watchlist")
def api_get_watchlist():
    return get_all_watchlist(limit=100)

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
    return {"success": True, "added": count, "symbol": sym, "trigger_price": trigger}

@app.get("/api/positions")
def api_get_positions():
    return get_open_positions()

@app.post("/api/positions/{position_id}/close")
def api_close_position(position_id: int):
    success = manual_close_position(position_id)
    if not success:
        raise HTTPException(status_code=404, detail="Open position not found or already closed.")
    return {"success": True, "message": f"Position {position_id} successfully closed."}

@app.get("/api/trades")
def api_get_trades():
    return get_trades(limit=100)

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
def api_action_fetch_mail():
    success, msg, items = fetch_and_parse_gmail_report()
    return {"success": success, "message": msg, "count": len(items), "items": items}

@app.post("/api/actions/parse-raw-mail")
def api_action_parse_raw_mail(payload: RawMailInput):
    content = payload.content
    parsed = parse_email_html_or_text(content if payload.is_html else "", content if not payload.is_html else "")
    if not parsed:
        return {"success": False, "message": "Could not identify stock records in the provided text/HTML.", "count": 0}
    added = add_watchlist_items(parsed)
    log_event("INFO", f"Parsed {len(parsed)} stocks from manual report input. {added} added to watchlist.")
    return {"success": True, "message": f"Successfully parsed {len(parsed)} stocks ({added} added).", "count": len(parsed), "items": parsed}

@app.post("/api/actions/run-cycle")
def api_action_run_cycle(force_market_open: bool = Body(False, embed=True)):
    res = run_trading_cycle(force_market_open=force_market_open)
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

@app.post("/api/actions/reset-portfolio")
def api_reset_portfolio():
    reset_portfolio()
    return {"success": True, "message": "Portfolio has been reset to ₹1,00,000 baseline."}

# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Paper Trading API active. Frontend index.html not found."}
