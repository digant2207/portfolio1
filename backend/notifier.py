"""
Notification module for daily paper trading summary reports.
Sends comprehensive HTML report via Gmail SMTP at market close (or on demand).
"""
import smtplib
import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
from typing import List, Dict, Any, Tuple, Optional
from .config import load_config
from .database import (
    get_portfolio_summary, get_open_positions, get_trades,
    get_pending_watchlist, get_nearest_breakout_candidates, log_event, get_db
)

def generate_daily_report_html() -> Tuple[str, str, Dict[str, Any]]:
    """
    Generates subject and HTML content for the comprehensive daily 6:30 PM email report
    covering:
    1. Portfolio Financial Status & Open Positions
    2. Today's Executed Trades
    3. Tomorrow's Top 10 Most Near Breakout Candidates (Ranked by 200 DMA + 1% proximity)
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
        
    breakout_candidates = get_nearest_breakout_candidates(limit=10)
    summary["breakout_candidates"] = breakout_candidates
    summary["todays_trades"] = todays_trades
    
    total_val = summary.get("total_portfolio_value", 100000.0)
    cash = summary.get("cash_balance", 100000.0)
    invested = summary.get("invested_capital", 0.0)
    ret_pct = summary.get("total_return_pct", 0.0)
    pnl_today = sum(t.get("pnl", 0.0) for t in todays_trades if t.get("trade_type") == "SELL")
    
    color_ret = "#10b981" if ret_pct >= 0 else "#ef4444"
    sign_ret = "+" if ret_pct >= 0 else ""
    sign_pnl_today = "+" if pnl_today >= 0 else ""
    color_pnl_today = "#10b981" if pnl_today >= 0 else "#ef4444"
    
    subject = f"📊 Smart Money Daily Report [6:30 PM | {today_str}] - Value: ₹{total_val:,.2f} ({sign_ret}{ret_pct}%) | Top Breakouts"
    
    # 1. Render Open Positions rows
    positions_html = ""
    if open_positions:
        for p in open_positions:
            pnl = p.get("current_pnl", 0.0)
            pnl_pct = p.get("current_pnl_pct", 0.0)
            pnl_color = "#10b981" if pnl >= 0 else "#ef4444"
            pnl_sign = "+" if pnl >= 0 else ""
            positions_html += f"""
            <tr style="border-bottom: 1px solid #1e293b;">
                <td style="padding: 10px 12px; font-weight: 700; color: #f8fafc;">
                    {p['symbol']}
                    <div style="font-size: 11px; color: #94a3b8; font-weight: 400;">{p.get('stock_name', '')}</div>
                </td>
                <td style="padding: 10px 12px; color: #94a3b8;">{p['quantity']}</td>
                <td style="padding: 10px 12px; color: #cbd5e1;">₹{p['buy_price']:,.2f}</td>
                <td style="padding: 10px 12px; color: #f8fafc; font-weight: 600;">₹{p.get('current_price', p['buy_price']):,.2f}</td>
                <td style="padding: 10px 12px; color: #ef4444;">₹{p['stop_loss']:,.2f} (-2%)</td>
                <td style="padding: 10px 12px; color: #10b981;">₹{p['target_price']:,.2f} (+5%)</td>
                <td style="padding: 10px 12px; color: {pnl_color}; font-weight: 700;">{pnl_sign}₹{pnl:,.2f} ({pnl_sign}{pnl_pct}%)</td>
            </tr>
            """
    else:
        positions_html = '<tr><td colspan="7" style="padding: 16px; text-align: center; color: #64748b;">No active open positions currently held.</td></tr>'

    # 2. Render Today's Trades rows
    trades_html = ""
    if todays_trades:
        for t in todays_trades:
            is_buy = t['trade_type'] == 'BUY'
            type_color = "#3b82f6" if is_buy else "#f59e0b"
            trade_pnl_str = f"₹{t.get('pnl', 0.0):,.2f}" if not is_buy else "-"
            trade_pnl_color = "#10b981" if t.get('pnl', 0) >= 0 else "#ef4444"
            trades_html += f"""
            <tr style="border-bottom: 1px solid #1e293b;">
                <td style="padding: 8px 12px; color: #94a3b8; font-size: 12px;">{t['timestamp'].split()[1] if ' ' in t['timestamp'] else t['timestamp']}</td>
                <td style="padding: 8px 12px; font-weight: 600; color: #f8fafc;">{t['symbol']}</td>
                <td style="padding: 8px 12px;"><span style="background: {type_color}22; color: {type_color}; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">{t['trade_type']}</span></td>
                <td style="padding: 8px 12px; color: #cbd5e1;">₹{t['price']:,.2f}</td>
                <td style="padding: 8px 12px; color: #cbd5e1;">{t['quantity']}</td>
                <td style="padding: 8px 12px; color: #f8fafc;">₹{t['total_value']:,.2f}</td>
                <td style="padding: 8px 12px; color: {trade_pnl_color}; font-weight: 600;">{trade_pnl_str}</td>
                <td style="padding: 8px 12px; color: #94a3b8; font-size: 12px;">{t.get('exit_reason') or 'ENTRY'}</td>
            </tr>
            """
    else:
        trades_html = '<tr><td colspan="8" style="padding: 16px; text-align: center; color: #64748b;">No trades executed during today\'s market session.</td></tr>'

    # 3. Render Tomorrow's Top 10 Breakout Candidates
    candidates_html = ""
    if breakout_candidates:
        for idx, c in enumerate(breakout_candidates, 1):
            is_above = c.get("section") == "above_200_dma"
            sec_badge = '<span style="background: rgba(16, 185, 129, 0.15); color: #10b981; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">Above 200 DMA</span>' if is_above else '<span style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">Below 200 DMA</span>'
            gc_badge = ""
            
            cmp_val = c.get("current_price") or c.get("cmp_report", 0.0)
            trig_val = c.get("trigger_price", 0.0)
            dma_val = c.get("dma_200", 0.0)
            prox_pct = c.get("proximity_pct", 0.0)
            is_crossed = c.get("is_crossed", False)
            bar_color = "#10b981" if is_crossed else "#38bdf8"
            status_color = "#10b981" if is_crossed else "#38bdf8"
            vol_str = f"{int(c.get('avg_volume_1m', 0)):,}" if c.get("avg_volume_1m") else "-"
            
            candidates_html += f"""
            <tr style="border-bottom: 1px solid #1e293b;">
                <td style="padding: 10px 12px; font-weight: 700; color: #f8fafc;">
                    <span style="color: #64748b; font-size: 11px; margin-right: 4px;">#{idx}</span>
                    {c['symbol']}
                    <div style="font-size: 11px; color: #94a3b8; font-weight: 400; margin-top: 2px;">{c.get('stock_name', '')}</div>
                </td>
                <td style="padding: 10px 12px;">{sec_badge}{gc_badge}</td>
                <td style="padding: 10px 12px; color: #cbd5e1; font-weight: 600;">₹{cmp_val:,.2f}</td>
                <td style="padding: 10px 12px; color: #94a3b8;">₹{dma_val:,.2f}</td>
                <td style="padding: 10px 12px; color: #38bdf8; font-weight: 700;">₹{trig_val:,.2f}</td>
                <td style="padding: 10px 12px;">
                    <div style="background: #1e293b; border-radius: 4px; height: 6px; overflow: hidden; margin-bottom: 4px; width: 110px;">
                        <div style="background: {bar_color}; width: {min(100, prox_pct)}%; height: 100%;"></div>
                    </div>
                    <span style="color: {status_color}; font-weight: 600; font-size: 11px;">{c.get('proximity_status')}</span>
                </td>
                <td style="padding: 10px 12px; color: #94a3b8; font-size: 12px;">{vol_str}</td>
            </tr>
            """
    else:
        candidates_html = '<tr><td colspan="7" style="padding: 16px; text-align: center; color: #64748b;">No candidate breakout stocks found in watchlist.</td></tr>'

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #e2e8f0; margin: 0; padding: 20px; }}
            .container {{ max-width: 820px; margin: 0 auto; background: #131b2e; border: 1px solid #202b42; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            .header {{ background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 24px; border-bottom: 1px solid #243049; }}
            .badge-hdr {{ display: inline-block; background: #0284c7; color: #ffffff; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }}
            .metric-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 20px; background: #0d1322; border-bottom: 1px solid #1c263c; }}
            .card {{ background: #162035; border: 1px solid #23304b; border-radius: 8px; padding: 14px; text-align: center; }}
            .card-label {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
            .card-val {{ font-size: 18px; font-weight: 700; color: #f8fafc; }}
            .section {{ padding: 20px; border-bottom: 1px solid #1c263c; }}
            .section-title {{ font-size: 15px; font-weight: 600; color: #38bdf8; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
            th {{ background: #0d1322; color: #64748b; font-weight: 600; text-align: left; padding: 10px 12px; border-bottom: 1px solid #232936; }}
            .rules-box {{ background: #0d1322; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; margin: 20px; }}
            .footer {{ padding: 16px 20px; background: #0d1322; color: #64748b; font-size: 11px; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <span class="badge-hdr">Daily 6:30 PM IST Summary</span>
                <h1 style="margin: 0 0 6px 0; font-size: 22px; color: #f8fafc;">Smart Money Paper Trading Report</h1>
                <p style="margin: 0; color: #94a3b8; font-size: 13px;">Date: {today_str} | Generated at: 18:30 IST | Strategy: 200 DMA + 1% Breakout</p>
            </div>
            
            <!-- Section 1: Portfolio Financial Metrics -->
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
                    <div class="card-label">Invested Capital</div>
                    <div class="card-val">₹{invested:,.2f}</div>
                </div>
                <div class="card">
                    <div class="card-label">Overall Return</div>
                    <div class="card-val" style="color: {color_ret};">{sign_ret}{ret_pct}%</div>
                </div>
            </div>

            <!-- Section 2: Active Open Positions -->
            <div class="section">
                <h3 class="section-title">💼 Active Open Holdings ({len(open_positions)})</h3>
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

            <!-- Section 3: Today's Executed Trades -->
            <div class="section">
                <h3 class="section-title">⚡ Today's Executed Trades ({len(todays_trades)})</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Time (IST)</th>
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

            <!-- Section 4: Tomorrow's Top 10 Most Near Breakout Candidates -->
            <div class="section">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 class="section-title" style="margin: 0; color: #38bdf8;">🎯 Tomorrow's Top 10 Most Near Breakout Candidates</h3>
                    <span style="font-size: 11px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 3px 8px; border-radius: 4px; font-weight: 600;">Ranked by Proximity (Min Vol: 10,000+ | CMP &gt; ₹20)</span>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Rank & Stock</th>
                            <th>Category</th>
                            <th>Report CMP</th>
                            <th>200 DMA</th>
                            <th>Buy Trigger (+1%)</th>
                            <th>Breakout Proximity</th>
                            <th>1-Mo Avg Vol</th>
                        </tr>
                    </thead>
                    <tbody>
                        {candidates_html}
                    </tbody>
                </table>
            </div>

            <div class="rules-box">
                <h4 style="margin: 0 0 8px 0; color: #38bdf8; font-size: 13px;">⚙️ Execution & Risk Management Rules:</h4>
                <ul style="margin: 0; padding-left: 20px; color: #94a3b8; font-size: 12px; line-height: 1.6;">
                    <li><strong>Trigger Entry:</strong> Buy is automatically evaluated when live CMP crosses 200 DMA + 1% during market hours (09:15 - 15:30 IST).</li>
                    <li><strong>Allocation:</strong> ₹10,000 per trade (Max 10 active positions from ₹1,00,000 capital).</li>
                    <li><strong>Safety Filters:</strong> Stocks with CMP &le; ₹20 or 1-Month Avg Volume &lt; 10,000 shares are automatically ignored.</li>
                    <li><strong>Target Exit:</strong> +5% profit target exit.</li>
                    <li><strong>Stop-Loss Exit:</strong> Strict -2% capital protection stop-loss.</li>
                </ul>
            </div>

            <div class="footer">
                Automated notification from your Paper Trading Terminal. Instant Telegram alerts enabled for all live trade triggers.
            </div>
        </div>
    </body>
    </html>
    """
    
    return subject, html_body, summary

def notify_daily_summary_telegram(summary: Dict[str, Any], todays_trades: List[Dict[str, Any]], candidates: List[Dict[str, Any]]):
    """
    Dispatches a compact evening daily summary alert via Telegram at 6:30 PM IST.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    total_val = summary.get("total_portfolio_value", 100000.0)
    cash = summary.get("cash_balance", 100000.0)
    invested = summary.get("invested_capital", 0.0)
    ret_pct = summary.get("total_return_pct", 0.0)
    sign_ret = "+" if ret_pct >= 0 else ""
    open_count = summary.get("open_positions_count", 0)
    trades_count = len(todays_trades)

    lines = [
        "📊 <b>PAPER TRADING DAILY SUMMARY (6:30 PM IST)</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📅 <b>Date:</b> {today_str}",
        f"💰 <b>Total Portfolio:</b> ₹{total_val:,.2f} ({sign_ret}{ret_pct}%)",
        f"💵 <b>Cash:</b> ₹{cash:,.2f} | <b>Invested:</b> ₹{invested:,.2f}",
        f"💼 <b>Open Positions:</b> {open_count} | <b>Trades Today:</b> {trades_count}\n",
        "🎯 <b>TOMORROW'S MOST NEAR BREAKOUTS (TOP 5)</b>",
        "━━━━━━━━━━━━━━━━━━"
    ]

    for idx, c in enumerate(candidates[:5], 1):
        stock_name = html.escape(str(c.get("stock_name") or c.get("symbol", "")).strip())
        cmp_val = c.get("current_price") or c.get("cmp_report", 0.0)
        trig = c.get("trigger_price", 0.0)
        prox_status = c.get("proximity_status", "")
        lines.append(f"<b>{idx}. {stock_name}</b> | CMP: ₹{cmp_val:,.2f} | Trig: ₹{trig:,.2f}\n   <i>{prox_status}</i>")

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("📧 <i>Comprehensive report sent to your email inbox!</i>")
    
    msg = "\n".join(lines)
    send_telegram_message(msg)

def send_daily_email_report() -> Tuple[bool, str]:
    """
    Sends the generated comprehensive daily report email via Gmail SMTP and dispatches Telegram summary.
    """
    import os
    if os.environ.get("MOCK_NOTIFICATIONS") == "1":
        return True, "Mock daily summary email delivered (test mode active)."

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
    todays_trades = summary.get("todays_trades", [])
    breakout_candidates = summary.get("breakout_candidates", [])
    
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
        
        # Dispatch compact Telegram summary alongside email
        try:
            notify_daily_summary_telegram(summary, todays_trades, breakout_candidates)
        except Exception as tg_e:
            log_event("WARNING", f"Telegram daily summary alert error: {tg_e}")
            
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
    
    import os
    if os.environ.get("MOCK_NOTIFICATIONS") == "1":
        return True, "Mock Telegram notification delivered (test mode active)."
        
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

def generate_evening_watchlist_html(items: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Generates subject and HTML email content for tomorrow's candidate watchlist (Top 10).
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    top_candidates = items[:10]
    
    subject = f"🎯 Tomorrow's Candidate Watchlist [Top {len(top_candidates)}] - Smart Money 200 DMA ({today_str})"
    
    rows_html = ""
    for idx, item in enumerate(top_candidates, 1):
        sec = item.get("section", "above_200_dma")
        sec_badge = '<span style="background: rgba(16, 185, 129, 0.15); color: #10b981; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">Above 200 DMA</span>' if sec == "above_200_dma" else '<span style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">Below 200 DMA</span>'
        
        rows_html += f"""
        <tr style="border-bottom: 1px solid #1e293b;">
            <td style="padding: 12px 14px; font-weight: 700; color: #f8fafc; font-size: 14px;">
                <span style="color: #64748b; font-size: 12px; margin-right: 6px;">#{idx}</span>
                {item['symbol']}
            </td>
            <td style="padding: 12px 14px; color: #cbd5e1;">{item.get('stock_name', item['symbol'])}</td>
            <td style="padding: 12px 14px;">{sec_badge}</td>
            <td style="padding: 12px 14px; color: #94a3b8;">₹{item['cmp_report']:,.2f}</td>
            <td style="padding: 12px 14px; color: #cbd5e1;">₹{item['dma_200']:,.2f}</td>
            <td style="padding: 12px 14px; color: #38bdf8; font-weight: 700; font-size: 14px;">₹{item['trigger_price']:,.2f}</td>
        </tr>
        """
        
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #e2e8f0; margin: 0; padding: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; background: #131b2e; border: 1px solid #202b42; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            .header {{ background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 24px; border-bottom: 1px solid #243049; }}
            .badge-hdr {{ display: inline-block; background: #0284c7; color: #ffffff; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }}
            .section {{ padding: 20px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }}
            th {{ background: #0d1322; color: #64748b; font-weight: 600; text-align: left; padding: 10px 14px; border-bottom: 1px solid #232936; }}
            .rules-box {{ background: #0d1322; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; margin: 20px; }}
            .footer {{ padding: 16px 20px; background: #0d1322; color: #64748b; font-size: 11px; text-align: center; border-top: 1px solid #1e293b; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <span class="badge-hdr">Evening 6:30 PM Report</span>
                <h1 style="margin: 0 0 6px 0; font-size: 22px; color: #f8fafc;">Tomorrow's Candidate Watchlist</h1>
                <p style="margin: 0; color: #94a3b8; font-size: 13px;">Extracted from Smart Money Finder Report | Date: {today_str}</p>
            </div>

            <div class="section">
                <h3 style="font-size: 15px; font-weight: 600; color: #38bdf8; margin: 0 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px;">
                    Top {len(top_candidates)} Breakout Candidates For Next Trading Session
                </h3>
                <table>
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Company</th>
                            <th>Category</th>
                            <th>Report CMP</th>
                            <th>200 DMA</th>
                            <th>Buy Trigger (+1%)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>

            <div class="rules-box">
                <h4 style="margin: 0 0 8px 0; color: #38bdf8; font-size: 13px;">⚙️ Execution & Risk Management Rules:</h4>
                <ul style="margin: 0; padding-left: 20px; color: #94a3b8; font-size: 12px; line-height: 1.6;">
                    <li><strong>Trigger Entry:</strong> Buy is automatically evaluated when live CMP crosses 200 DMA + 1%.</li>
                    <li><strong>Allocation:</strong> ₹10,000 per trade (Max 10 active positions from ₹1,00,000 capital).</li>
                    <li><strong>Safety Filters:</strong> Stocks with CMP &le; ₹20 or 1-Month Avg Volume &lt; 10,000 shares are automatically ignored.</li>
                    <li><strong>Target:</strong> Minimum +5% gain exit.</li>
                    <li><strong>Stop-Loss:</strong> Strict -2% loss exit.</li>
                </ul>
            </div>

            <div class="footer">
                Automated notification from your Paper Trading Terminal. Instant Telegram alerts enabled for live trades.
            </div>
        </div>
    </body>
    </html>
    """
    return subject, html

def send_evening_watchlist_email(items: Any = None) -> Tuple[bool, str]:
    """
    Dispatches tomorrow's candidate watchlist email (Top 10) to the user's inbox at 6:30 PM.
    """
    import os
    if os.environ.get("MOCK_NOTIFICATIONS") == "1":
        return True, "Mock evening watchlist email delivered (test mode active)."

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

    if not items:
        items = get_pending_watchlist()

    if not items:
        msg = "No watchlist candidate items available to send."
        log_event("INFO", msg)
        return False, msg

    subject, html_body = generate_evening_watchlist_html(items)
    
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
            
        success_msg = f"Tomorrow's Candidate Watchlist email successfully sent to {recipient} ({len(items[:10])} stocks)."
        log_event("INFO", success_msg)
        return True, success_msg
    except Exception as e:
        err = f"Failed to send evening watchlist email via SMTP: {str(e)}"
        log_event("ERROR", err)
        return False, err

def notify_evening_watchlist_telegram(items: List[Dict[str, Any]]):
    """
    Sends tomorrow's candidate list (Top 10) via Telegram.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    top_candidates = items[:10]
    if not top_candidates:
        return
        
    lines = [
        "🎯 <b>TOMORROW'S CANDIDATE WATCHLIST (TOP 10)</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"📅 <b>Report Date:</b> {today_str}",
        f"📊 <b>Strategy:</b> 200 DMA + 1% Breakout\n"
    ]
    
    for idx, it in enumerate(top_candidates, 1):
        stock_name = html.escape(str(it.get("stock_name") or it.get("symbol", "")).strip())
        sec = "Above 200 DMA" if it.get("section") == "above_200_dma" else "Below 200 DMA"
        cmp_val = it.get("cmp_report", 0.0)
        dma_val = it.get("dma_200", 0.0)
        trig = it.get("trigger_price", 0.0)
        
        lines.append(
            f"<b>{idx}. {stock_name}</b> (<i>{sec}</i>)\n"
            f"   💵 CMP: ₹{cmp_val:,.2f} | 200 DMA: ₹{dma_val:,.2f}\n"
            f"   🎯 <b>Trigger Buy:</b> ₹{trig:,.2f}\n"
        )
        
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("<i>Criteria: CMP > ₹20 | Vol > 10,000 | ₹10k Alloc | SL: 2% | Tgt: 5%</i>")
    
    full_msg = "\n".join(lines)
    send_telegram_message(full_msg)
