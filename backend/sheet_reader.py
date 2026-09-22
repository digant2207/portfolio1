"""
Google Sheets CSV reader module for Smart Money 200 DMA Paper Trading Engine.
Replaces Gmail email parsing with direct Google Sheets CSV export.

Sheet 1 (Smart Money 200 DMA Report):
  Columns: Symbol, Name, CMP, 5 DMA, ..., 200 DMA, Output, Volume, 1 Month Avg Volume, Change %, Change (₹)
  Output signal: "Best for Buy Above 200 DMA", "Best for Sell Below 200 DMA", or "Avoid"

Sheet 2 (DMA Signal Tracker):
  Columns: Symbol, Stock Name, Current Price (₹), Volume, 1 Month Avg Volume, 50 DMA (₹), 200 DMA (₹), ..., DMA Signal
  DMA Signal: "Golden Cross" or "Death Cross"
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

# Default Google Sheet IDs (configurable via config.json)
DEFAULT_SHEET_ID_1 = "1B__Wam6da-nD7ReSg2JlHwu5pH7xDHlkQkBjSzF9YdA"
DEFAULT_SHEET_ID_2 = "1_rWhyap8gO-u8ehP1vDCiad-RwnFjGBCn2R5qiis4_A"

EXPORT_URL_TEMPLATE = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def parse_number(val: Any) -> float:
    """Safely extracts float from string with currencies, commas, etc."""
    if isinstance(val, (int, float)):
        return float(val)
    if not val:
        return 0.0
    text = str(val).replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    match = re.search(r"[-+]?\d*\.?\d+", text)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return 0.0
    return 0.0


def clean_sheet_symbol(raw_symbol: str) -> str:
    """
    Normalizes sheet symbol to NSE ticker format ending with .NS.
    Handles formats like 'NSE:RELIANCE', 'RELIANCE', 'reliance', '512068' (BSE code).
    """
    clean = str(raw_symbol).strip()
    if not clean:
        return ""
    
    # Remove 'NSE:' or 'BSE:' prefix
    if ":" in clean:
        clean = clean.split(":", 1)[1]
    
    clean = clean.strip().upper()
    
    # Skip pure numeric BSE codes — they may not map cleanly to .NS
    # but keep them with .NS suffix anyway for yfinance compatibility
    if not clean:
        return ""
    
    if not clean.endswith(".NS") and not clean.endswith(".BO"):
        return f"{clean}.NS"
    return clean


def fetch_sheet_csv(sheet_id: str, gid: int = 0) -> Tuple[bool, str, str]:
    """
    Downloads public Google Sheet as CSV text.
    Returns (success, message, csv_text).
    """
    url = EXPORT_URL_TEMPLATE.format(sheet_id=sheet_id, gid=gid)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PaperTradingBot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            csv_text = response.read().decode("utf-8", errors="ignore")
            if not csv_text or len(csv_text) < 50:
                return False, f"Empty or too-small response from sheet {sheet_id}", ""
            return True, "OK", csv_text
    except urllib.error.HTTPError as e:
        return False, f"HTTP error fetching sheet {sheet_id}: {e.code} {e.reason}", ""
    except urllib.error.URLError as e:
        return False, f"URL error fetching sheet {sheet_id}: {e.reason}", ""
    except Exception as e:
        return False, f"Error fetching sheet {sheet_id}: {str(e)}", ""


def parse_smart_money_sheet(csv_text: str) -> List[Dict[str, Any]]:
    """
    Parses Sheet 1 (Smart Money 200 DMA Report) CSV.
    Expected columns: Symbol, Name, CMP, ..., 200 DMA, Output, Volume, 1 Month Avg Volume, Change %, Change (₹)
    Returns list of candidate items where Output != 'Avoid'.
    """
    cfg = load_config()
    buffer_pct = cfg.get("trigger_buffer_pct", 1.0)
    min_price = cfg.get("min_stock_price", 20.0)
    min_volume = cfg.get("min_1m_avg_volume", 10000.0)
    today_str = datetime.now().strftime("%Y-%m-%d")
    results = []
    
    reader = csv.DictReader(io.StringIO(csv_text))
    
    for row in reader:
        try:
            # Get the Output/signal column
            output_signal = str(row.get("Output", "")).strip()
            
            # Only keep Buy or Sell candidates — skip "Avoid" and empty
            if not output_signal or output_signal.lower() == "avoid":
                continue
            
            # Determine section from signal
            signal_lower = output_signal.lower()
            if "buy" in signal_lower or "above" in signal_lower:
                section = "above_200_dma"
            elif "sell" in signal_lower or "below" in signal_lower:
                section = "below_200_dma"
            else:
                continue
            
            raw_symbol = str(row.get("Symbol", "")).strip()
            symbol = clean_sheet_symbol(raw_symbol)
            if not symbol:
                continue
            
            stock_name = str(row.get("Name", "")).strip() or raw_symbol
            cmp_val = parse_number(row.get("CMP", 0))
            dma_200 = parse_number(row.get("200 DMA", 0))
            volume = parse_number(row.get("Volume", 0))
            avg_vol_1m = parse_number(row.get("1 Month Avg Volume", 0))
            change_pct_raw = str(row.get("Change %", "")).strip().replace("%", "")
            change_pct = parse_number(change_pct_raw) if change_pct_raw else 0.0
            
            if cmp_val <= 0 or dma_200 <= 0:
                continue

            # Strict Filter 1: Ignore penny stocks (CMP <= 20)
            if cmp_val <= min_price:
                continue

            # Strict Filter 2: Ignore illiquid stocks (1-Month Avg Daily Volume < 10,000)
            if avg_vol_1m > 0 and avg_vol_1m < min_volume:
                continue
            
            trigger_price = round(dma_200 * (1 + (buffer_pct / 100.0)), 2)
            
            results.append({
                "report_date": today_str,
                "stock_name": stock_name,
                "symbol": symbol,
                "section": section,
                "cmp_report": cmp_val,
                "dma_200": dma_200,
                "trigger_price": trigger_price,
                "avg_volume_1m": avg_vol_1m,
                "volume_today": volume,
                "change_pct": change_pct,
                "golden_cross": False  # Updated later from Sheet 2
            })
        except Exception:
            continue
    
    return results


def parse_dma_signal_sheet(csv_text: str) -> Dict[str, str]:
    """
    Parses Sheet 2 (DMA Signal Tracker) CSV.
    Returns dict mapping SYMBOL.NS -> signal ('Golden Cross' or 'Death Cross').
    """
    signals = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    
    for row in reader:
        try:
            raw_symbol = str(row.get("Symbol", "")).strip()
            if not raw_symbol:
                continue
            symbol = clean_sheet_symbol(raw_symbol)
            if not symbol:
                continue
            
            dma_signal = str(row.get("DMA Signal", "")).strip()
            if dma_signal and dma_signal.lower() != "neutral":
                signals[symbol] = dma_signal
        except Exception:
            continue
    
    return signals


def fetch_and_process_sheets() -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Main entry point — replaces fetch_and_parse_gmail_report().
    1. Fetches both Google Sheets as CSV
    2. Parses Sheet 1 for Buy/Sell candidates
    3. Cross-references Sheet 2 for Golden Cross confirmation
    4. Adds to watchlist DB
    5. Dispatches evening watchlist notification (once per day)
    Returns (success, message, items).
    """
    cfg = load_config()
    sheet_id_1 = cfg.get("google_sheet_id_1", DEFAULT_SHEET_ID_1)
    sheet_id_2 = cfg.get("google_sheet_id_2", DEFAULT_SHEET_ID_2)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Fetch Sheet 1 (Smart Money 200 DMA)
    ok1, msg1, csv1 = fetch_sheet_csv(sheet_id_1)
    if not ok1:
        log_event("ERROR", f"Failed to fetch Google Sheet 1: {msg1}")
        return False, f"Google Sheet 1 fetch failed: {msg1}", []
    
    # 2. Parse Sheet 1 candidates
    candidates = parse_smart_money_sheet(csv1)
    if not candidates:
        log_event("INFO", "Sheet 1 fetched successfully but no Buy/Sell candidates found (all 'Avoid').")
        return True, "No Buy/Sell candidates in today's sheet (all marked 'Avoid').", []
    
    # 3. Fetch Sheet 2 (DMA Signal Tracker) — optional, non-fatal
    dma_signals = {}
    ok2, msg2, csv2 = fetch_sheet_csv(sheet_id_2)
    if ok2:
        dma_signals = parse_dma_signal_sheet(csv2)
        log_event("INFO", f"Sheet 2 loaded: {len(dma_signals)} DMA signals parsed.")
    else:
        log_event("WARNING", f"Sheet 2 fetch failed (non-fatal): {msg2}. Proceeding without Golden Cross data.")
    
    # 4. Cross-reference Sheet 2 signals into candidates
    golden_count = 0
    for item in candidates:
        sym = item["symbol"]
        signal = dma_signals.get(sym, "")
        if signal.lower() == "golden cross":
            item["golden_cross"] = True
            golden_count += 1
    
    # 5. Sort candidates: Golden Cross first, then by section (Buy above Sell), then by symbol
    candidates.sort(key=lambda x: (
        not x.get("golden_cross", False),  # Golden Cross first
        0 if x["section"] == "above_200_dma" else 1,  # Buy above Sell
        x["symbol"]
    ))
    
    # 6. Add to watchlist DB
    added = add_watchlist_items(candidates)
    log_event("INFO", f"Google Sheets: Parsed {len(candidates)} candidate stocks ({golden_count} Golden Cross). {added} new added to watchlist.")
    
    # 7. Dispatch evening watchlist notification (email + Telegram) — ONCE PER DAY
    from .database import is_notification_sent, record_notification_sent
    already_sent = is_notification_sent(today_str, "EVENING_WATCHLIST")
    
    if not already_sent:
        try:
            from .notifier import send_evening_watchlist_email, notify_evening_watchlist_telegram
            send_evening_watchlist_email(candidates)
            notify_evening_watchlist_telegram(candidates)
            record_notification_sent(today_str, "EVENING_WATCHLIST", f"Sent for {len(candidates)} candidate stocks ({golden_count} Golden Cross)")
            log_event("INFO", f"Evening candidate watchlist notification dispatched for {today_str}.")
        except Exception as notify_err:
            log_event("WARNING", f"Evening watchlist notification dispatch warning: {notify_err}")
    else:
        log_event("INFO", f"Evening candidate watchlist for {today_str} already dispatched today. Skipping duplicate notifications.")
    
    return True, f"Successfully fetched {len(candidates)} candidate stocks from Google Sheets. {added} added to watchlist. {golden_count} confirmed Golden Cross.", candidates
