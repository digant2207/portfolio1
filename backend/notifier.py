"""
Notification module for daily paper trading summary reports.
Sends comprehensive HTML report via Gmail SMTP at market close (or on demand).
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
from typing import Dict, Any, Tuple
from .config import load_config
from .database import (
    get_portfolio_summary, get_open_positions, get_trades,
    get_pending_watchlist, log_event, get_db
)

def generate_daily_report_html() -> Tuple[str, str, Dict[str, Any]]:
    """
    Generates subject and HTML content for the daily summary email.
    """
    summary = get_portfolio_summary()
    open_positions = get_open_positions()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    # Fetch today's trades
    with get_db() as conn:
        trades_rows = conn.execute("""
            SELECT * FROM trades 
            WHERE date(timestamp) = date('now') 
            ORDER BY id DESC
        """).fetchall()
        todays_trades = [dict(r) for r in trades_rows]
        
    watchlist_items = get_pending_watchlist()
    
    total_val = summary.get("total_portfolio_value", 100000.0)
    cash = summary.get("cash_balance", 100000.0)
    invested = summary.get("invested_capital", 0.0)
    ret_pct = summary.get("total_return_pct", 0.0)
    pnl_today = sum(t.get("pnl", 0.0) for t in todays_trades if t.get("trade_type") == "SELL")
    
    color_ret = "#10b981" if ret_pct >= 0 else "#ef4444"
    sign_ret = "+" if ret_pct >= 0 else ""
    
    subject = f"📊 Paper Trading Daily Report [{today_str}] - Value: ₹{total_val:,.2f} ({sign_ret}{ret_pct}%)"
    
    # Render Open Positions rows
    positions_html = ""
    if open_positions:
        for p in open_positions:
            pnl = p.get("current_pnl", 0.0)
            pnl_pct = p.get("current_pnl_pct", 0.0)
            pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
            pnl_sign = "+" if pnl >= 0 else ""
            positions_html += f"""
            <tr style="border-bottom: 1px solid #232936;">
                <td style="padding: 10px 12px; font-weight: 600; color: #f8fafc;">{p['symbol']}</td>
                <td style="padding: 10px 12px; color: #94a3b8;">{p['quantity']}</td>
                <td style="padding: 10px 12px; color: #cbd5e1;">₹{p['buy_price']:,.2f}</td>
                <td style="padding: 10px 12px; color: #f8fafc; font-weight: 600;">₹{p.get('current_price', p['buy_price']):,.2f}</td>
                <td style="padding: 10px 12px; color: #ef4444;">₹{p['stop_loss']:,.2f} (-2%)</td>
                <td style="padding: 10px 12px; color: #10b981;">₹{p['target_price']:,.2f} (+5%)</td>
                <td style="padding: 10px 12px; color: {pnl_color}; font-weight: 700;">{pnl_sign}₹{pnl:,.2f} ({pnl_sign}{pnl_pct}%)</td>
            </tr>
            """
    else:
        positions_html = '<tr><td colspan="7" style="padding: 15px; text-align: center; color: #64748b;">No active open positions currently.</td></tr>'

    # Render Today's Trades rows
    trades_html = ""
    if todays_trades:
        for t in todays_trades:
            is_buy = t['trade_type'] == 'BUY'
            type_color = "#3b82f6" if is_buy else "#f59e0b"
            trade_pnl_str = f"₹{t.get('pnl', 0.0):,.2f}" if not is_buy else "-"
            trades_html += f"""
            <tr style="border-bottom: 1px solid #232936;">
                <td style="padding: 8px 12px; color: #94a3b8; font-size: 12px;">{t['timestamp'].split()[1] if ' ' in t['timestamp'] else t['timestamp']}</td>
                <td style="padding: 8px 12px; font-weight: 600; color: #f8fafc;">{t['symbol']}</td>
                <td style="padding: 8px 12px;"><span style="background: {type_color}22; color: {type_color}; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">{t['trade_type']}</span></td>
                <td style="padding: 8px 12px; color: #cbd5e1;">₹{t['price']:,.2f}</td>
                <td style="padding: 8px 12px; color: #cbd5e1;">{t['quantity']}</td>
                <td style="padding: 8px 12px; color: #f8fafc;">₹{t['total_value']:,.2f}</td>
                <td style="padding: 8px 12px; color: #10b981 if t.get('pnl',0) >= 0 else #ef4444;">{trade_pnl_str}</td>
                <td style="padding: 8px 12px; color: #94a3b8; font-size: 12px;">{t.get('exit_reason') or 'ENTRY'}</td>
            </tr>
            """
    else:
        trades_html = '<tr><td colspan="8" style="padding: 15px; text-align: center; color: #64748b;">No trades executed today.</td></tr>'

    # Render Watchlist preview
    watchlist_html = ""
    if watchlist_items:
        for w in watchlist_items[:10]:
            sec_badge = "Above 200 DMA" if w["section"] == "above_200_dma" else "Below 200 DMA"
            watchlist_html += f"""
            <tr style="border-bottom: 1px solid #232936;">
                <td style="padding: 8px 12px; font-weight: 600; color: #f8fafc;">{w['symbol']}</td>
                <td style="padding: 8px 12px; color: #94a3b8;">{sec_badge}</td>
                <td style="padding: 8px 12px; color: #cbd5e1;">₹{w['dma_200']:,.2f}</td>
                <td style="padding: 8px 12px; color: #38bdf8; font-weight: 600;">₹{w['trigger_price']:,.2f}</td>
            </tr>
            """
    else:
        watchlist_html = '<tr><td colspan="4" style="padding: 15px; text-align: center; color: #64748b;">No pending triggers in watchlist.</td></tr>'

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #e2e8f0; margin: 0; padding: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; background: #131b2e; border: 1px solid #202b42; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            .header {{ background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 24px; border-bottom: 1px solid #243049; }}
            .metric-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 20px; background: #0d1322; }}
            .card {{ background: #162035; border: 1px solid #23304b; border-radius: 8px; padding: 14px; text-align: center; }}
            .card-label {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
            .card-val {{ font-size: 18px; font-weight: 700; color: #f8fafc; }}
            .section {{ padding: 20px; border-bottom: 1px solid #1c263c; }}
            .section-title {{ font-size: 15px; font-weight: 600; color: #38bdf8; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
            th {{ background: #0d1322; color: #64748b; font-weight: 600; text-align: left; padding: 10px 12px; border-bottom: 1px solid #232936; }}
            .footer {{ padding: 16px 20px; background: #0d1322; color: #64748b; font-size: 11px; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin: 0 0 6px 0; font-size: 22px; color: #f8fafc;">Smart Money Paper Trading Report</h1>
                <p style="margin: 0; color: #94a3b8; font-size: 13px;">Date: {today_str} | Strategy: 200 DMA + 1% Breakout</p>
            </div>
            
            <div class="metric-grid">
                <div class="card">
                    <div class="card-label">Total Portfolio</div>
                    <div class="card-val">₹{total_val:,.2f}</div>
                </div>
                <div class="card">
                    <div class="card-label">Cash Balance</div>
                    <div class="card-val">₹{cash:,.2f}</div>
                </div>
                <div class="card">
                    <div class="card-label">Invested Amount</div>
                    <div class="card-val">₹{invested:,.2f}</div>
                </div>
                <div class="card">
                    <div class="card-label">Overall Return</div>
                    <div class="card-val" style="color: {color_ret};">{sign_ret}{ret_pct}%</div>
                </div>
            </div>

            <div class="section">
                <h3 class="section-title">Active Open Holdings ({len(open_positions)})</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Stock</th>
                            <th>Qty</th>
                            <th>Buy Price</th>
                            <th>CMP</th>
                            <th>Stop Loss</th>
                            <th>Target</th>
                            <th>Unrealized P&L</th>
                        </tr>
                    </thead>
                    <tbody>
                        {positions_html}
                    </tbody>
                </table>
            </div>

            <div class="section">
                <h3 class="section-title">Today's Executed Trades ({len(todays_trades)})</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Stock</th>
                            <th>Action</th>
                            <th>Price</th>
                            <th>Qty</th>
                            <th>Total</th>
                            <th>Realized P&L</th>
                            <th>Reason</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trades_html}
                    </tbody>
                </table>
            </div>

            <div class="section">
                <h3 class="section-title">Tomorrow's Trigger Watchlist ({len(watchlist_items)})</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>List Type</th>
                            <th>200 DMA</th>
                            <th>Trigger Buy (+1%)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {watchlist_html}
                    </tbody>
                </table>
            </div>

            <div class="footer">
                Automated notification from your Paper Trading Terminal. Allocation: ₹10,000 / trade (Max 10). SL: 2% | Target: 5%.
            </div>
        </div>
    </body>
    </html>
    """
    
    return subject, html_body, summary

def send_daily_email_report() -> Tuple[bool, str]:
    """
    Sends the generated daily report email via Gmail SMTP.
    """
    cfg = load_config()
    user = cfg.get("gmail_user", "").strip()
    pwd = cfg.get("gmail_app_password", "").strip()
    recipient = cfg.get("notification_recipient", "").strip() or user
    smtp_server = cfg.get("gmail_smtp_server", "smtp.gmail.com")
    smtp_port = cfg.get("gmail_smtp_port", 587)
    
    if not user or not pwd:
        msg = "Cannot send email: Gmail credentials not configured in settings."
        log_event("WARNING", msg)
        return False, msg
        
    subject, html_body, summary = generate_daily_report_html()
    
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Paper Trading Bot <{user}>"
        msg["To"] = recipient
        
        part = MIMEText(html_body, "html")
        msg.attach(part)
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(user, pwd)
            server.sendmail(user, recipient, msg.as_string())
            
        success_msg = f"Daily summary email successfully sent to {recipient}."
        log_event("INFO", success_msg)
        return True, success_msg
    except Exception as e:
        err = f"Failed to send daily summary email via SMTP: {str(e)}"
        log_event("ERROR", err)
        return False, err

def send_telegram_message(text: str, parse_mode: str = "HTML") -> Tuple[bool, str]:
    """
    Sends an instant message notification via Telegram Bot API.
    Requires 'telegram_bot_token' and 'telegram_chat_id' in settings.
    """
    import urllib.request
    import urllib.parse
    import json
    
    cfg = load_config()
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()
    
    if not token or not chat_id:
        return False, "Telegram token or chat_id not configured."
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "PaperTradingBot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            if res_json.get("ok"):
                return True, "Telegram message sent successfully."
            else:
                desc = res_json.get("description", "Unknown error")
                log_event("WARNING", f"Telegram API error: {desc}")
                return False, desc
    except Exception as e:
        err = f"Telegram send error: {str(e)}"
        log_event("WARNING", err)
        return False, err

def notify_trade_buy(trade: Dict[str, Any]):
    """Dispatches a Telegram alert for a newly executed BUY order."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sym = trade.get("symbol", "")
    name = trade.get("stock_name", sym)
    section = trade.get("section", "above_200_dma")
    section_label = "Above 200 DMA" if section == "above_200_dma" else "Below 200 DMA"
    price = trade.get("price", 0.0)
    qty = trade.get("quantity", 0)
    invested = trade.get("invested_amount", price * qty)
    sl = trade.get("stop_loss", price * 0.98)
    target = trade.get("target_price", price * 1.05)
    
    msg = (
        f"🚀 <b>BUY ORDER EXECUTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>Stock:</b> <code>{sym}</code> ({name})\n"
        f"📑 <b>Section:</b> {section_label}\n"
        f"💵 <b>Buy Price:</b> ₹{price:,.2f}\n"
        f"🔢 <b>Quantity:</b> {qty}\n"
        f"💰 <b>Invested:</b> ₹{invested:,.2f}\n"
        f"🛑 <b>Stop-Loss (-2%):</b> ₹{sl:,.2f}\n"
        f"🎯 <b>Target (+5%):</b> ₹{target:,.2f}\n"
        f"⏰ <b>Time:</b> {now_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>Strategy: 200 DMA + 1% Breakout</i>"
    )
    send_telegram_message(msg)

def notify_trade_sell(trade: Dict[str, Any]):
    """Dispatches a Telegram alert for an exit (Target Hit, Stop Loss Hit, or Manual)."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sym = trade.get("symbol", "")
    name = trade.get("stock_name", sym)
    reason = trade.get("exit_reason", "SELL")
    sell_price = trade.get("price", 0.0)
    buy_price = trade.get("buy_price", 0.0)
    qty = trade.get("quantity", 0)
    pnl = trade.get("pnl", 0.0)
    proceeds = trade.get("proceeds", round(sell_price * qty, 2))
    pnl_pct = round(((sell_price - buy_price) / buy_price * 100), 2) if buy_price > 0 else 0.0
    sign = "+" if pnl >= 0 else ""
    
    if reason == "TARGET_HIT":
        header = "🎯 <b>TARGET REACHED (+5% EXIT)</b>"
    elif reason == "STOP_LOSS_HIT":
        header = "🛑 <b>STOP-LOSS TRIGGERED (-2% EXIT)</b>"
    else:
        header = f"✋ <b>POSITION CLOSED ({reason})</b>"
        
    msg = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📉 <b>Stock:</b> <code>{sym}</code> ({name})\n"
        f"💵 <b>Exit Price:</b> ₹{sell_price:,.2f}\n"
        f"🛒 <b>Buy Price:</b> ₹{buy_price:,.2f}\n"
        f"🔢 <b>Quantity:</b> {qty}\n"
        f"💰 <b>Total Value:</b> ₹{proceeds:,.2f}\n"
        f"📊 <b>Realized P&L:</b> {sign}₹{pnl:,.2f} ({sign}{pnl_pct}%)\n"
        f"⏰ <b>Time:</b> {now_str}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    send_telegram_message(msg)
