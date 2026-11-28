"""
Task scheduler for:
1. 17:00-20:00 IST daily (every 15 min) - Fetch Google Sheets watchlist data
2. 09:16 - 15:30 IST (Mon-Fri) every 2 mins - Run paper trading market cycle
3. 15:45 IST (Mon-Fri) - Send daily email summary report
4. 18:30 IST daily - Dispatch Tomorrow's Candidate List (Top 10)
"""
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from .database import log_event
from .sheet_reader import fetch_and_process_sheets
from .trading_engine import run_trading_cycle
from .notifier import send_daily_email_report

IST = pytz.timezone("Asia/Kolkata")
scheduler = BackgroundScheduler(timezone=IST)

def scheduled_sheet_fetch():
    log_event("INFO", "Scheduled task: Fetching watchlist from Google Sheets...")
    success, msg, items = fetch_and_process_sheets()
    log_event("INFO" if success else "WARNING", f"Sheet fetch result: {msg}")

def scheduled_market_check():
    # Only runs during market hours or if forced
    run_trading_cycle(force_market_open=False)

def scheduled_daily_630_report():
    from datetime import datetime
    from .database import is_notification_sent, record_notification_sent
    from .notifier import send_p1_daily_email_report, send_p2_daily_email_report, notify_daily_summary_telegram
    today_str = datetime.now().strftime("%Y-%m-%d")
        
    # Ensure latest Google Sheet data is fetched before generating report
    try:
        fetch_and_process_sheets()
    except Exception as e:
        log_event("WARNING", f"Pre-report sheet fetch notice: {e}")
        
    log_event("INFO", "Scheduled task (18:30 IST): Generating and sending separate daily activity reports for Portfolio 1 & 2...")

    # 1. Portfolio 1 Report
    if not is_notification_sent(today_str, "DAILY_REPORT_P1_630"):
        s1, m1 = send_p1_daily_email_report()
        if s1:
            record_notification_sent(today_str, "DAILY_REPORT_P1_630", m1)
        log_event("INFO" if s1 else "WARNING", f"Daily P1 report result: {m1}")
    else:
        log_event("INFO", f"Daily P1 report for {today_str} already sent. Skipping duplicate.")

    # 2. Portfolio 2 Report
    if not is_notification_sent(today_str, "DAILY_REPORT_P2_630"):
        s2, m2 = send_p2_daily_email_report()
        if s2:
            record_notification_sent(today_str, "DAILY_REPORT_P2_630", m2)
        log_event("INFO" if s2 else "WARNING", f"Daily P2 report result: {m2}")
    else:
        log_event("INFO", f"Daily P2 report for {today_str} already sent. Skipping duplicate.")

    # 3. Telegram Summary Alert
    try:
        from .database import get_portfolio_summary, get_today_trades, get_nearest_breakout_candidates
        summary = get_portfolio_summary()
        today_trades = get_today_trades()
        breakout_candidates = get_nearest_breakout_candidates(limit=5)
        notify_daily_summary_telegram(summary, today_trades, breakout_candidates)
    except Exception as tg_e:
        log_event("WARNING", f"Telegram daily summary notice: {tg_e}")

def start_scheduler():
    if not scheduler.running:
        # 1. Evening Google Sheets Window: Poll every 15 minutes between 17:00 and 18:15 IST
        # Ensures fresh candidate data is ready before 18:30 report
        scheduler.add_job(
            scheduled_sheet_fetch,
            CronTrigger(hour="17", minute="*/15", timezone=IST),
            id="sheet_fetch_job",
            replace_existing=True
        )
        
        # 2. Every 2 minutes during Indian market hours (09:16 - 15:30 Mon-Fri)
        scheduler.add_job(
            scheduled_market_check,
            CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/2", timezone=IST),
            id="market_check_job",
            replace_existing=True
        )
        
        # 3. 18:30 IST Daily: Comprehensive Daily Report (Portfolio status, today's trades, top breakouts)
        scheduler.add_job(
            scheduled_daily_630_report,
            CronTrigger(hour=18, minute=30, timezone=IST),
            id="daily_630_report_job",
            replace_existing=True
        )
        
        scheduler.start()
        log_event("INFO", "Background task scheduler started successfully (Timezone: Asia/Kolkata).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log_event("INFO", "Background task scheduler stopped.")
