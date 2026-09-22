"""
Cloud Runner CLI for GitHub Actions & Automated Cloud Jobs.
Usage:
  python scripts/cloud_runner.py --task fetch-sheets
  python scripts/cloud_runner.py --task trade-cycle
  python scripts/cloud_runner.py --task daily-report
  python scripts/cloud_runner.py --task evening-watchlist
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
from backend.sheet_reader import fetch_and_process_sheets
from backend.trading_engine import run_trading_cycle
from backend.notifier import send_daily_email_report

def main():
    parser = argparse.ArgumentParser(description="Paper Trading Cloud Runner")
    parser.add_argument("--task", choices=["fetch-sheets", "fetch-mail", "trade-cycle", "daily-report", "evening-report", "evening-watchlist"], required=True, help="Task to execute")
    args = parser.parse_args()

    init_db()

    if args.task in ("fetch-sheets", "fetch-mail"):
        # 'fetch-mail' is kept as alias for backward compatibility with existing GitHub Actions
        print("[*] Executing Cloud Task: fetch-sheets (Google Sheets)")
        success, msg, items = fetch_and_process_sheets()
        print(f"Result: {msg}")
        if items:
            print(f"[+] Loaded {len(items)} candidate stocks into watchlist from Google Sheets.")
        if not success:
            sys.exit(1)

    elif args.task == "trade-cycle":
        print("[*] Executing Cloud Task: trade-cycle")
        summary = run_trading_cycle(force_market_open=False)
        print(f"Result: {len(summary.get('buys_triggered', []))} buys, {len(summary.get('targets_hit', []))} targets, {len(summary.get('stop_losses_hit', []))} stop-losses.")

    elif args.task in ("daily-report", "evening-report", "evening-watchlist"):
        print("[*] Executing Cloud Task: daily-report (Unified 6:30 PM Email & Telegram Report)")
        try:
            fetch_and_process_sheets()
        except Exception as e:
            print(f"[!] Warning fetching sheets before report: {e}")

        from backend.database import is_notification_sent, record_notification_sent
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        if is_notification_sent(today_str, "DAILY_REPORT_630"):
            print(f"[i] Daily 6:30 PM report for {today_str} already sent today. Skipping duplicate.")
        else:
            success, msg = send_daily_email_report()
            print(f"Result: {msg}")
            if success:
                record_notification_sent(today_str, "DAILY_REPORT_630", msg)
            if not success:
                sys.exit(1)

if __name__ == "__main__":
    main()
