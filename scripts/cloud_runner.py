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
    parser.add_argument("--task", choices=["fetch-mail", "trade-cycle", "daily-report"], required=True, help="Task to execute")
    args = parser.parse_args()

    init_db()

    if args.task == "fetch-mail":
        print("[*] Executing Cloud Task: fetch-mail")
        success, msg, items = fetch_and_parse_gmail_report()
        print(f"Result: {msg}")
        if items:
            print(f"[+] Loaded {len(items)} stocks into watchlist.")
        if not success:
            sys.exit(1)

    elif args.task == "trade-cycle":
        print("[*] Executing Cloud Task: trade-cycle")
        summary = run_trading_cycle(force_market_open=False)
        print(f"Result: {len(summary.get('buys_triggered', []))} buys, {len(summary.get('targets_hit', []))} targets, {len(summary.get('stop_losses_hit', []))} stop-losses.")

    elif args.task == "daily-report":
        print("[*] Executing Cloud Task: daily-report")
        success, msg = send_daily_email_report()
        print(f"Result: {msg}")
        if not success:
            sys.exit(1)

if __name__ == "__main__":
    main()
