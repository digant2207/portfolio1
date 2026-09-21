"""
Task scheduler for:
1. 18:05 IST daily - Fetch and parse Gmail report
2. 09:16 - 15:30 IST (Mon-Fri) every 2 mins - Run paper trading market cycle
3. 15:45 IST (Mon-Fri) - Send daily email summary report
"""
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from .database import log_event
from .mail_reader import fetch_and_parse_gmail_report
from .trading_engine import run_trading_cycle
from .notifier import send_daily_email_report

IST = pytz.timezone("Asia/Kolkata")
scheduler = BackgroundScheduler(timezone=IST)

def scheduled_mail_fetch():
    log_event("INFO", "Scheduled task: Fetching daily Gmail report...")
    success, msg, items = fetch_and_parse_gmail_report()
    log_event("INFO" if success else "WARNING", f"Mail fetch result: {msg}")

def scheduled_market_check():
    # Only runs during market hours or if forced
    run_trading_cycle(force_market_open=False)

def scheduled_daily_report():
    log_event("INFO", "Scheduled task: Generating and dispatching daily portfolio report...")
    success, msg = send_daily_email_report()
    log_event("INFO" if success else "WARNING", f"Daily report result: {msg}")

def scheduled_evening_watchlist():
    log_event("INFO", "Scheduled task (18:30 IST): Sending Tomorrow's Candidate List (Top 10)...")
    from .notifier import send_evening_watchlist_email, notify_evening_watchlist_telegram
    from .database import get_pending_watchlist
    items = get_pending_watchlist()
    if items:
        send_evening_watchlist_email(items)
        notify_evening_watchlist_telegram(items)
    else:
        log_event("INFO", "18:30 IST watchlist check: No pending candidate items in database yet.")

def start_scheduler():
    if not scheduler.running:
        # 1. Evening Gmail Window: Poll every 15 minutes between 17:30 and 20:45 IST
        # This guarantees catching the report whether it arrives early or delayed.
        scheduler.add_job(
            scheduled_mail_fetch,
            CronTrigger(hour="17-20", minute="*/15", timezone=IST),
            id="mail_fetch_job",
            replace_existing=True
        )
        
        # 2. Every 2 minutes during Indian market hours (09:16 - 15:30 Mon-Fri)
        scheduler.add_job(
            scheduled_market_check,
            CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/2", timezone=IST),
            id="market_check_job",
            replace_existing=True
        )
        
        # 3. 15:45 IST (Mon-Fri): Send EOD report
        scheduler.add_job(
            scheduled_daily_report,
            CronTrigger(day_of_week="mon-fri", hour=15, minute=45, timezone=IST),
            id="daily_report_job",
            replace_existing=True
        )

        # 4. 18:30 IST daily: Dispatch Tomorrow's Candidate List (Top 10)
        scheduler.add_job(
            scheduled_evening_watchlist,
            CronTrigger(hour=18, minute=30, timezone=IST),
            id="evening_watchlist_job",
            replace_existing=True
        )
        
        scheduler.start()
        log_event("INFO", "Background task scheduler started successfully (Timezone: Asia/Kolkata).")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log_event("INFO", "Background task scheduler stopped.")
