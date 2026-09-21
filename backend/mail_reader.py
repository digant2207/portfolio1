"""
Email fetching and parsing module for 'Daily smart money finder report'.
Reads emails from Gmail IMAP and extracts stock screening tables:
1. 'best for buy above 200 dma'
2. 'best for sell below 200 dma'
"""
import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple
from .config import load_config
from .database import log_event, add_watchlist_items

# Common Indian Equities name to symbol cleaner & mapping
COMMON_NAME_MAP = {
    "RELIANCE INDUSTRIES": "RELIANCE",
    "RELIANCE": "RELIANCE",
    "TATA CONSULTANCY SERVICES": "TCS",
    "TCS": "TCS",
    "INFOSYS": "INFY",
    "INFY": "INFY",
    "HDFC BANK": "HDFCBANK",
    "ICICI BANK": "ICICIBANK",
    "STATE BANK OF INDIA": "SBIN",
    "SBI": "SBIN",
    "TATA MOTORS": "TATAMOTORS",
    "BHARTI AIRTEL": "BHARTIARTL",
    "LARSEN & TOUBRO": "LT",
    "L&T": "LT",
    "ITC": "ITC",
    "KOTAK MAHINDRA BANK": "KOTAKBANK",
    "HINDUSTAN UNILEVER": "HINDUNILVR",
    "HUL": "HINDUNILVR",
    "AXIS BANK": "AXISBANK",
    "MARUTI SUZUKI": "MARUTI",
    "ASIAN PAINTS": "ASIANPAINT",
    "BAJAJ FINANCE": "BAJFINANCE",
    "SUN PHARMA": "SUNPHARMA",
    "TATA STEEL": "TATASTEEL",
    "TITAN": "TITAN",
    "WIPRO": "WIPRO",
    "ADANI ENTERPRISES": "ADANIENT",
    "ADANI PORTS": "ADANIPORTS",
    "POWER GRID": "POWERGRID",
    "NTPC": "NTPC",
    "COAL INDIA": "COALINDIA",
    "ONGC": "ONGC",
    "JSW STEEL": "JSWSTEEL",
    "TECH MAHINDRA": "TECHM"
}

def clean_symbol(stock_name: str) -> str:
    """Normalizes raw stock name to an NSE ticker symbol ending with .NS"""
    clean = re.sub(r'[^a-zA-Z0-9\s&]', '', stock_name).strip().upper()
    
    if clean in COMMON_NAME_MAP:
        sym = COMMON_NAME_MAP[clean]
    else:
        # Check if first word or token matches common tickers
        first_token = clean.split()[0] if clean else "UNKNOWN"
        sym = COMMON_NAME_MAP.get(first_token, first_token)
        
    if not sym.endswith(".NS") and not sym.endswith(".BO"):
        return f"{sym}.NS"
    return sym

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

def parse_email_html_or_text(html_content: str, text_content: str = "") -> List[Dict[str, Any]]:
    """
    Parses email body into watchlist items for:
    1. 'best for buy above 200 dma'
    2. 'best for sell below 200 dma'
    """
    cfg = load_config()
    buffer_pct = cfg.get("trigger_buffer_pct", 1.0)
    today_str = datetime.now().strftime("%Y-%m-%d")
    results = []

    soup = BeautifulSoup(html_content, "html.parser")
    
    # Try finding tables or section headers
    # Approach: inspect text or headers
    body_text = soup.get_text("\n") if soup else text_content
    
    # Look for table structures first
    tables = soup.find_all("table")
    
    found_in_tables = False
    for table in tables:
        # Check heading immediately preceding or inside table
        prev_heading = ""
        prev = table.find_previous(["h1", "h2", "h3", "h4", "p", "div", "b", "strong"])
        if prev:
            prev_heading = prev.get_text().strip().lower()
            
        table_text = table.get_text().lower()
        
        section = "above_200_dma"
        if "below" in prev_heading or "below 200" in table_text or "sell" in prev_heading:
            section = "below_200_dma"
        elif "above" in prev_heading or "above 200" in table_text or "buy" in prev_heading:
            section = "above_200_dma"
        else:
            # check parent elements
            parent_text = table.parent.get_text().lower() if table.parent else ""
            if "below 200" in parent_text:
                section = "below_200_dma"

        rows = table.find_all("tr")
        if len(rows) > 1:
            header_cells = [th.get_text().strip().lower() for th in rows[0].find_all(["th", "td"])]
            name_idx = -1
            cmp_idx = -1
            dma_idx = -1
            
            for idx, h in enumerate(header_cells):
                if any(k in h for k in ["stock", "symbol", "company", "name"]):
                    name_idx = idx
                elif any(k in h for k in ["cmp", "price", "current", "ltp"]):
                    cmp_idx = idx
                elif any(k in h for k in ["200", "dma", "trigger", "buying"]):
                    dma_idx = idx
            
            if name_idx == -1 and len(header_cells) >= 3:
                name_idx, cmp_idx, dma_idx = 0, 1, 2
                
            if name_idx != -1 and (cmp_idx != -1 or dma_idx != -1):
                found_in_tables = True
                for row in rows[1:]:
                    cells = [td.get_text().strip() for td in row.find_all(["td", "th"])]
                    if len(cells) <= max(name_idx, cmp_idx, dma_idx):
                        continue
                    stock_name = cells[name_idx]
                    if not stock_name or any(k in stock_name.lower() for k in ["stock", "company", "total"]):
                        continue
                    cmp_val = parse_number(cells[cmp_idx]) if cmp_idx != -1 and cmp_idx < len(cells) else 0.0
                    dma_val = parse_number(cells[dma_idx]) if dma_idx != -1 and dma_idx < len(cells) else cmp_val
                    
                    if dma_val <= 0 and cmp_val > 0:
                        dma_val = cmp_val
                    if cmp_val <= 0 and dma_val > 0:
                        cmp_val = dma_val
                        
                    if cmp_val > 0 and dma_val > 0:
                        trigger_price = round(dma_val * (1 + (buffer_pct / 100.0)), 2)
                        symbol = clean_symbol(stock_name)
                        results.append({
                            "report_date": today_str,
                            "stock_name": stock_name,
                            "symbol": symbol,
                            "section": section,
                            "cmp_report": cmp_val,
                            "dma_200": dma_val,
                            "trigger_price": trigger_price
                        })

    # If tables were not structured or empty, fallback to regex / line-based extraction
    if not results:
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        current_section = "above_200_dma"
        
        for line in lines:
            line_lower = line.lower()
            if "above 200" in line_lower or "best for buy" in line_lower:
                current_section = "above_200_dma"
                continue
            elif "below 200" in line_lower or "best for sell" in line_lower:
                current_section = "below_200_dma"
                continue
                
            # Regex match patterns like:
            # "TATAMOTORS CMP: 980.50 200DMA: 950.00" or "RELIANCE, 2900, 2850" or "1. TCS | 3800 | 3750"
            numbers = re.findall(r"\b\d+(?:\.\d+)?\b", line)
            if len(numbers) >= 2:
                # Find letters for stock name
                name_match = re.search(r"^[0-9\.\s\-\*]*([A-Za-z\s&]+)", line)
                if name_match:
                    raw_name = name_match.group(1).strip()
                    if len(raw_name) > 1 and raw_name.lower() not in ["cmp", "dma", "stock", "price", "buy", "sell", "target"]:
                        cmp_val = float(numbers[0])
                        dma_val = float(numbers[1])
                        trigger_price = round(dma_val * (1 + (buffer_pct / 100.0)), 2)
                        symbol = clean_symbol(raw_name)
                        results.append({
                            "report_date": today_str,
                            "stock_name": raw_name,
                            "symbol": symbol,
                            "section": current_section,
                            "cmp_report": cmp_val,
                            "dma_200": dma_val,
                            "trigger_price": trigger_price
                        })
                        
    return results

def decode_mime_words(raw_header: str) -> str:
    """Properly decodes multi-part RFC 2047 MIME encoded headers."""
    if not raw_header:
        return ""
    try:
        decoded_parts = decode_header(raw_header)
        res = []
        for text, enc in decoded_parts:
            if isinstance(text, bytes):
                res.append(text.decode(enc or "utf-8", errors="ignore"))
            else:
                res.append(str(text))
        return "".join(res)
    except Exception:
        return str(raw_header)

def fetch_and_parse_gmail_report() -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Connects to Gmail via IMAP SSL, searches for 'Daily smart money finder report',
    parses stock lists and populates watchlist.
    """
    cfg = load_config()
    user = cfg.get("gmail_user", "").strip()
    pwd = cfg.get("gmail_app_password", "").strip()
    imap_server = cfg.get("gmail_imap_server", "imap.gmail.com")
    subject_query = cfg.get("email_report_subject", "Daily smart money finder report")
    
    if not user or not pwd:
        msg = "Gmail credentials not configured. Please enter your Gmail and Google App Password in Settings."
        log_event("WARNING", msg)
        return False, msg, []
        
    try:
        log_event("INFO", f"Connecting to Gmail IMAP ({imap_server}) for {user}...")
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(user, pwd)
        mail.select("INBOX")
        
        # Search query for subject
        # Note: Gmail search syntax supports SUBJECT "..."
        status, messages = mail.search(None, f'(SUBJECT "{subject_query}")')
        msg_ids = messages[0].split() if status == "OK" and messages[0] else []
        
        # If no direct match, try broader smart money query
        if not msg_ids:
            status, messages = mail.search(None, '(SUBJECT "smart money")')
            msg_ids = messages[0].split() if status == "OK" and messages[0] else []
            
        if not msg_ids:
            # Fallback to search recent messages
            status, messages = mail.search(None, "ALL")
            msg_ids = messages[0].split() if status == "OK" and messages[0] else []
            msg_ids = msg_ids[-50:]  # Inspect up to 50 latest emails
            
        if not msg_ids:
            msg = f"No emails found matching subject '{subject_query}'."
            log_event("INFO", msg)
            mail.close()
            mail.logout()
            return True, msg, []
            
        # Inspect latest matching email
        latest_items = []
        found_target = False
        
        for msg_id in reversed(msg_ids):
            res, data = mail.fetch(msg_id, "(RFC822)")
            if res != "OK":
                continue
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Decode subject cleanly across all MIME chunks
            subject = decode_mime_words(msg.get("Subject", ""))
                
            if "smart money" in subject.lower() or subject_query.lower() in subject.lower():
                found_target = True
                html_body = ""
                text_body = ""
                
                if msg.is_multipart():
                    for part in msg.walk():
                        ctype = part.get_content_type()
                        cdispo = str(part.get("Content-Disposition"))
                        if ctype == "text/html" and "attachment" not in cdispo:
                            payload = part.get_payload(decode=True)
                            if payload:
                                html_body = payload.decode("utf-8", errors="ignore")
                        elif ctype == "text/plain" and "attachment" not in cdispo:
                            payload = part.get_payload(decode=True)
                            if payload:
                                text_body = payload.decode("utf-8", errors="ignore")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        html_body = payload.decode("utf-8", errors="ignore")
                        text_body = html_body

                parsed = parse_email_html_or_text(html_body, text_body)
                if parsed:
                    latest_items = parsed
                    break
                    
        mail.close()
        mail.logout()
        
        if not found_target:
            return False, f"Could not find an email matching subject '{subject_query}' among recent messages.", []
            
        if not latest_items:
            return True, "Email found, but could not parse any stocks. Check if report format matches table or section structure.", []
            
        added = add_watchlist_items(latest_items)
        log_event("INFO", f"Successfully parsed {len(latest_items)} stocks from email report. Added {added} new to tomorrow's watchlist.")
        
        # Dispatch evening candidate watchlist email & Telegram notification (Top 10)
        try:
            from .notifier import send_evening_watchlist_email, notify_evening_watchlist_telegram
            send_evening_watchlist_email(latest_items)
            notify_evening_watchlist_telegram(latest_items)
        except Exception as notify_err:
            log_event("WARNING", f"Evening watchlist notification dispatch warning: {notify_err}")

        return True, f"Successfully parsed {len(latest_items)} stocks. {added} added to watchlist. Evening candidate report dispatched.", latest_items
        
    except Exception as e:
        err = f"Gmail IMAP connection failed: {str(e)}"
        log_event("ERROR", err)
        return False, err, []
