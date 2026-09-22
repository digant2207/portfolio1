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
    today_str = datetime.now().strftime("%Y-%m-%d")
    if is_notification_sent(today_str, "DAILY_REPORT_630"):
        log_event("INFO", f"Daily 6:30 PM report for {today_str} already sent earlier today. Skipping duplicate.")
        return
        
    # Ensure latest Google Sheet data is fetched before generating report
    try:
        fetch_and_process_sheets()
    except Exception as e:
        log_event("WARNING", f"Pre-report sheet fetch notice: {e}")
        
    log_event("INFO", "Scheduled task (18:30 IST): Generating and sending comprehensive daily report & nearest breakouts...")
    success, msg = send_daily_email_report()
    if success:
        record_notification_sent(today_str, "DAILY_REPORT_630", msg)
    log_event("INFO" if success else "WARNING", f"Daily 6:30 PM report result: {msg}")

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
