"""
Cloud Runner CLI for GitHub Actions & Automated Cloud Jobs.
Usage:
  python scripts/cloud_runner.py --task fetch-mail
  python scripts/cloud_runner.py --task trade-cycle
  python scripts/cloud_runner.py --task daily-report
"""
import sys
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from backend.database import init_db, log_event
from backend.mail_reader import fetch_and_parse_gmail_report
from backend.trading_engine import run_trading_cycle
from backend.notifier import send_daily_email_report

def main():
    parser = argparse.ArgumentParser(description="Paper Trading Cloud Runner")
    parser.add_argument("--task", choices=["fetch-mail", "trade-cycle", "daily-report", "evening-watchlist"], required=True, help="Task to execute")
    args = parser.parse_args()

    init_db()

    if args.task == "fetch-mail":
        print("[*] Executing Cloud Task: fetch-mail")
        success, msg, items = fetch_and_parse_gmail_report()
        print(f"Result: {msg}")
        if items:
            print(f"[+] Loaded {len(items)} stocks into watchlist and dispatched evening candidate alerts.")
        if not success:
            sys.exit(1)

    elif args.task == "trade-cycle":
        print("[*] Executing Cloud Task: trade-cycle")
        summary = run_trading_cycle(force_market_open=False)
        print(f"Result: {len(summary.get('buys_triggered', []))} buys, {len(summary.get('targets_hit', []))} targets, {len(summary.get('stop_losses_hit', []))} stop-losses.")

    elif args.task == "daily-report":
        print("[*] Executing Cloud Task: daily-report")
        from backend.database import is_notification_sent, record_notification_sent
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        if is_notification_sent(today_str, "DAILY_SUMMARY"):
            print(f"[i] Daily summary report for {today_str} already sent today. Skipping.")
        else:
            success, msg = send_daily_email_report()
            print(f"Result: {msg}")
            if success:
                record_notification_sent(today_str, "DAILY_SUMMARY", msg)
            if not success:
                sys.exit(1)

    elif args.task == "evening-watchlist":
        print("[*] Executing Cloud Task: evening-watchlist")
        from backend.notifier import send_evening_watchlist_email, notify_evening_watchlist_telegram
        from backend.database import get_pending_watchlist, is_notification_sent, record_notification_sent
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        if is_notification_sent(today_str, "EVENING_WATCHLIST"):
            print(f"[i] Evening candidate watchlist for {today_str} already sent today. Skipping.")
        else:
            items = get_pending_watchlist()
            if items:
                success, msg = send_evening_watchlist_email(items)
                notify_evening_watchlist_telegram(items)
                record_notification_sent(today_str, "EVENING_WATCHLIST", f"Cloud runner dispatch ({len(items)} stocks)")
                print(f"Result: {msg}")
                if not success:
                    sys.exit(1)
            else:
                print("[i] No pending candidate items found in watchlist.")

if __name__ == "__main__":
    main()
