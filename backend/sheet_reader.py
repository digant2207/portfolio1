"""
Google Sheets CSV reader module for Smart Money 200 DMA Paper Trading Engine.
Reads unified single Google Sheet containing 757+ stocks with technical indicators,
moving averages (50 DMA, 200 DMA), liquidity metrics, and DMA cross signals.
"""
import csv
import io
import re
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from .config import load_config
from .database import log_event, add_watchlist_items

# Default Unified Google Sheet ID (configurable via config.json)
DEFAULT_SHEET_ID = "1EKaY7YGSgQWnPrs57naHhJCSHp7VJ_PvXdFhzBfow1w"

GVIZ_URL_TEMPLATE = "https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}"
EXPORT_URL_TEMPLATE = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def parse_number(val: Any) -> float:
    """Safely extracts float from string with currencies, commas, percentages, etc."""
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0.0
    text = str(val).replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").replace("%", "").strip()
    match = re.search(r"[-+]?\d*\.?\d+", text)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return 0.0
    return 0.0


# Known ticker aliases mapping shorthand sheet names or numeric codes to valid NSE/BSE tickers
SYMBOL_ALIASES = {
    "SUPREME": "SUPREMEIND.NS",
    "SUPREME.NS": "SUPREMEIND.NS",
    "SUNDARAM": "SUNDARMFIN.NS",
    "SUNDARAM.NS": "SUNDARMFIN.NS",
    "RAJOO": "RAJOOENG.NS",
    "RAJOO.NS": "RAJOOENG.NS",
    "522257": "RAJOOENG.NS",
    "522257.NS": "RAJOOENG.NS",
    "522257.BO": "RAJOOENG.NS",
    "JINDAL": "JINDALPHOT.NS",
    "JINDAL.NS": "JINDALPHOT.NS",
    "AJANTA": "519216.BO",
    "AJANTA.NS": "519216.BO",
    "ANSAL": "ANSALBUIL.BO",
    "ANSAL.NS": "ANSALBUIL.BO",
}

def clean_sheet_symbol(raw_symbol: str) -> str:
    """
    Normalizes sheet symbol to NSE/BSE ticker format.
    Resolves known aliases and formats numeric BSE codes properly.
    """
    clean = str(raw_symbol).strip()
    if not clean:
        return ""
    
    # Remove 'NSE:' or 'BSE:' prefix
    if ":" in clean:
        clean = clean.split(":", 1)[1]
    
    clean = clean.strip().upper()
    if not clean:
        return ""
    
    # Check alias map
    if clean in SYMBOL_ALIASES:
        return SYMBOL_ALIASES[clean]
    clean_ns = f"{clean}.NS"
    if clean_ns in SYMBOL_ALIASES:
        return SYMBOL_ALIASES[clean_ns]

    # Numeric symbols are standard BSE scrip codes
    if clean.isdigit():
        return f"{clean}.BO"
        
    if not clean.endswith(".NS") and not clean.endswith(".BO"):
        return f"{clean}.NS"
    return clean


def fetch_sheet_csv(sheet_id: str, gid: int = 0) -> Tuple[bool, str, str]:
    """
    Downloads public Google Sheet as CSV text.
    First tries Google Visualization CSV endpoint (which evaluates all formulas),
    with fallback to standard /export?format=csv.
    Returns (success, message, csv_text).
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PaperTradingBot/2.0"}

    # 1. Try GViz CSV endpoint (guarantees dynamic formula columns are evaluated)
    gviz_url = GVIZ_URL_TEMPLATE.format(sheet_id=sheet_id, gid=gid)
    try:
        req = urllib.request.Request(gviz_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            csv_text = response.read().decode("utf-8", errors="ignore")
            if csv_text and len(csv_text) >= 100:
                return True, "OK (GViz)", csv_text
    except Exception as gviz_err:
        log_event("DEBUG", f"GViz CSV fetch failed ({gviz_err}), attempting standard export URL...")

    # 2. Fallback to standard export URL
    export_url = EXPORT_URL_TEMPLATE.format(sheet_id=sheet_id, gid=gid)
    try:
        req = urllib.request.Request(export_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            csv_text = response.read().decode("utf-8", errors="ignore")
            if not csv_text or len(csv_text) < 50:
                return False, f"Empty or too-small response from sheet {sheet_id}", ""
            return True, "OK (Standard Export)", csv_text
    except urllib.error.HTTPError as e:
        return False, f"HTTP error fetching sheet {sheet_id}: {e.code} {e.reason}", ""
    except urllib.error.URLError as e:
        return False, f"URL error fetching sheet {sheet_id}: {e.reason}", ""
    except Exception as e:
        return False, f"Error fetching sheet {sheet_id}: {str(e)}", ""


def parse_combined_sheet(csv_text: str) -> List[Dict[str, Any]]:
    """
    Parses single unified Google Sheet CSV.
    Expected columns: Symbol, Stock Name, Current Price (₹), Volume, 1 Month Avg Volume,
                     Vol. %, 5 DMA, 10 DMA, 20 DMA, 50 DMA (₹), 100 DMA, 200 DMA (₹),
                     52W High (₹), 52W Low (₹), DMA Signal, Transetion Day, Trigger, Stop Loss

    Applies trading logic:
    - Filters: CMP > min_stock_price (₹20), 1M Avg Volume >= min_1m_avg_volume (10,000)
    - Trend Section: 'above_200_dma' when CMP >= 200 DMA (only_above_200_dma = True)
    - Trigger Price: Custom Trigger from sheet if specified, else 200 DMA + 1% (200 DMA * 1.01)
    - Golden Cross: Trigger removed as requested; apply only 200 DMA + 1% and custom trigger price.
    """
    cfg = load_config()
    buffer_pct = cfg.get("trigger_buffer_pct", 1.0)
    max_buffer_pct = cfg.get("max_breakout_buffer_pct", 5.0)
    require_50_dma = cfg.get("require_above_50_dma", True)
    min_price = cfg.get("min_stock_price", 20.0)
    min_volume = cfg.get("min_1m_avg_volume", 10000.0)
    only_above_200 = cfg.get("only_above_200_dma", True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    results = []

    reader = csv.DictReader(io.StringIO(csv_text))

    for raw_row in reader:
        try:
            # Clean keys by stripping spaces
            row = {k.strip(): v.strip() for k, v in raw_row.items() if k}

            raw_symbol = row.get("Symbol", "")
            if not raw_symbol:
                continue

            symbol = clean_sheet_symbol(raw_symbol)
            if not symbol:
                continue

            stock_name = row.get("Stock Name", "") or raw_symbol

            # Current market price & moving averages
            cmp_val = parse_number(row.get("Current Price (₹)") or row.get("Current Price") or row.get("CMP"))
            dma_200 = parse_number(row.get("200 DMA (₹)") or row.get("200 DMA"))
            dma_50 = parse_number(row.get("50 DMA (₹)") or row.get("50 DMA"))
            volume = parse_number(row.get("Volume"))
            avg_vol_1m = parse_number(row.get("1 Month Avg Volume"))
            vol_pct = parse_number(row.get("Vol. %"))
            dma_signal = str(row.get("DMA Signal", "")).strip()

            # Custom Trigger and Stop Loss from Google Sheet
            raw_trig_str = str(row.get("Trigger", "")).strip()
            sheet_trig_val = parse_number(raw_trig_str) if raw_trig_str else 0.0

            raw_sl_str = str(row.get("Stop Loss", "")).strip()
            sheet_sl_val = parse_number(raw_sl_str) if raw_sl_str else 0.0

            # If user explicitly specifies a trigger price in the sheet, prioritize it
            if sheet_trig_val > 0:
                trigger_price = round(sheet_trig_val, 2)
                section = "above_200_dma"
            else:
                if cmp_val <= 0 or dma_200 <= 0:
                    continue

                # Trend condition: Above 200 DMA
                is_above_200 = (cmp_val >= dma_200)
                section = "above_200_dma" if is_above_200 else "below_200_dma"

                if only_above_200 and section == "below_200_dma":
                    continue

                # Option 4: Trend Alignment — CMP must be >= 50 DMA
                if require_50_dma and dma_50 > 0 and cmp_val < dma_50:
                    continue

                # Option 1: Fresh Breakout Zone — CMP must NOT be overextended above 200 DMA (default max 5%)
                if max_buffer_pct > 0 and cmp_val > round(dma_200 * (1 + (max_buffer_pct / 100.0)), 2):
                    continue

                # Breakout trigger price: 200 DMA + 1% buffer
                trigger_price = round(dma_200 * (1 + (buffer_pct / 100.0)), 2)

            # Strict Filter 1: Ignore penny stocks (CMP <= 20)
            if cmp_val <= min_price:
                continue

            # Strict Filter 2: Ignore illiquid stocks (1-Month Avg Daily Volume < 10,000)
            if avg_vol_1m > 0 and avg_vol_1m < min_volume:
                continue

            # Golden cross trigger removed as of now: apply only 200 DMA + 1% and custom sheet triggers
            is_golden = False

            results.append({
                "report_date": today_str,
                "stock_name": stock_name,
                "symbol": symbol,
                "section": section,
                "cmp_report": cmp_val,
                "dma_200": dma_200,
                "dma_50": dma_50,
                "trigger_price": trigger_price,
                "sheet_trigger": round(sheet_trig_val, 2) if sheet_trig_val > 0 else None,
                "sheet_stop_loss": round(sheet_sl_val, 2) if sheet_sl_val > 0 else None,
                "sheet_stop_loss_raw": raw_sl_str if raw_sl_str else None,
                "avg_volume_1m": avg_vol_1m,
                "volume_today": volume,
                "vol_pct": vol_pct,
                "golden_cross": 0,
                "dma_signal": dma_signal
            })
        except Exception:
            continue

    return results


def fetch_and_process_sheets() -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Main entry point for Google Sheets ingestion.
    1. Fetches unified single Google Sheet as CSV.
    2. Parses candidate stocks (incorporating custom Trigger and Stop Loss column values).
    3. Adds qualified candidates to watchlist DB.
    4. Checks open holdings against sheet Stop Loss — triggers immediate exit & Telegram alert if hit!
    5. Dispatches evening watchlist notification (email + Telegram) once per day.
    Returns (success, message, candidates).
    """
    cfg = load_config()
    sheet_id = cfg.get("google_sheet_id") or cfg.get("google_sheet_id_1") or DEFAULT_SHEET_ID
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Fetch Google Sheet CSV
    ok, msg, csv_text = fetch_sheet_csv(sheet_id)
    if not ok:
        log_event("ERROR", f"Failed to fetch Google Sheet ({sheet_id}): {msg}")
        return False, f"Google Sheet fetch failed: {msg}", []

    # 2. Parse candidates
    candidates = parse_combined_sheet(csv_text)
    if not candidates:
        log_event("INFO", "Google Sheet fetched successfully, but no stocks matched current screening filters.")
        return True, "No candidate stocks matched current screening filters.", []

    # 3. Sort candidates: Custom Triggers first, then 200 DMA + 1% triggers (by symbol)
    custom_trig_count = sum(1 for c in candidates if c.get("sheet_trigger"))
    dma_trig_count = len(candidates) - custom_trig_count
    candidates.sort(key=lambda x: (
        not bool(x.get("sheet_trigger")),   # Explicit custom triggers highest priority
        0 if x["section"] == "above_200_dma" else 1,
        x["symbol"]
    ))

    # 4. Add to watchlist DB & expire non-qualifying PENDING items
    from .database import expire_unlisted_watchlist_items
    added = add_watchlist_items(candidates)
    active_symbols = [c["symbol"] for c in candidates]
    expired_count = expire_unlisted_watchlist_items(active_symbols)
    if expired_count > 0:
        log_event("INFO", f"Watchlist cleanup: Expired {expired_count} stocks no longer meeting screening rules.")
    log_event("INFO", f"Google Sheets: Parsed {len(candidates)} candidate stocks ({custom_trig_count} custom triggers, {dma_trig_count} 200 DMA + 1% triggers). {added} new added to watchlist.")

    # 5. Check if any currently open position has an indicated Stop Loss in the sheet
    try:
        from .database import get_open_positions, update_position_stop_loss
        from .trading_engine import execute_stop_loss_exit
        from .market_data import fetch_market_quotes

        open_positions = get_open_positions()
        if open_positions:
            candidate_map = {c["symbol"]: c for c in candidates}
            symbols_to_check = [p["symbol"] for p in open_positions if p["symbol"] in candidate_map]
            live_quotes = fetch_market_quotes(symbols_to_check) if symbols_to_check else {}

            for pos in open_positions:
                pos_sym = pos["symbol"]
                sheet_item = candidate_map.get(pos_sym)
                if not sheet_item:
                    continue

                raw_sl = sheet_item.get("sheet_stop_loss_raw")
                sl_num = sheet_item.get("sheet_stop_loss")
                if not raw_sl and not sl_num:
                    continue

                q = live_quotes.get(pos_sym, {})
                cmp_val = q.get("price") or pos.get("current_price") or pos.get("buy_price")
                day_low = q.get("low") or cmp_val
                is_exit_signal = str(raw_sl).strip().upper() in ["EXIT", "SL", "SELL", "CLOSE", "HIT", "STOP LOSS", "STOPLOSS"]

                if is_exit_signal or (sl_num and sl_num > 0 and (cmp_val <= sl_num or day_low <= sl_num)):
                    exit_price = sl_num if (sl_num and day_low <= sl_num and cmp_val > sl_num) else cmp_val
                    execute_stop_loss_exit(pos, exit_price, exit_reason="STOP_LOSS_HIT")
                    log_event("TRADE", f"🛑 Position {pos_sym} closed due to Google Sheet Stop-Loss indicator: {raw_sl or sl_num}")
                elif sl_num and sl_num > 0 and sl_num != pos.get("stop_loss"):
                    update_position_stop_loss(pos["id"], sl_num)
                    log_event("INFO", f"Updated Stop-Loss on holding {pos_sym} to ₹{sl_num:.2f} based on Google Sheet.")
    except Exception as sl_check_err:
        log_event("WARNING", f"Error checking holdings against sheet stop loss: {sl_check_err}")

    # 5. Dispatch evening watchlist notification (email + Telegram) — ONCE PER DAY
    from .database import is_notification_sent, record_notification_sent
    already_sent = is_notification_sent(today_str, "EVENING_WATCHLIST")

    if not already_sent:
        try:
            from .notifier import send_evening_watchlist_email, notify_evening_watchlist_telegram
            send_evening_watchlist_email(candidates)
            notify_evening_watchlist_telegram(candidates)
            record_notification_sent(today_str, "EVENING_WATCHLIST", f"Sent for {len(candidates)} candidate stocks ({custom_trig_count} custom triggers, {dma_trig_count} 200 DMA + 1% triggers)")
            log_event("INFO", f"Evening candidate watchlist notification dispatched for {today_str}.")
        except Exception as notify_err:
            log_event("WARNING", f"Evening watchlist notification dispatch warning: {notify_err}")
    else:
        log_event("INFO", f"Evening candidate watchlist for {today_str} already dispatched today. Skipping duplicate notifications.")

    return True, f"Successfully fetched {len(candidates)} candidate stocks from Google Sheets. {added} added to watchlist ({custom_trig_count} custom triggers, {dma_trig_count} 200 DMA + 1% triggers).", candidates
