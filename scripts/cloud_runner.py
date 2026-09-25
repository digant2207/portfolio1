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

from backend.database import init_db, log_event, export_portfolio_snapshot
from backend.sheet_reader import fetch_and_process_sheets
from backend.trading_engine import run_trading_cycle
from backend.notifier import send_daily_email_report

def main():
    parser = argparse.ArgumentParser(description="Paper Trading Cloud Runner")
    parser.add_argument("--task", choices=["fetch-sheets", "fetch-mail", "trade-cycle", "p2-trade-cycle", "daily-report", "evening-report", "evening-watchlist", "evening-wyckoff", "export-snapshot", "wyckoff-scan"], required=True, help="Task to execute")
    args = parser.parse_args()

    init_db()

    if args.task in ("fetch-sheets", "fetch-mail"):
        # 'fetch-mail' is kept as alias for backward compatibility with existing GitHub Actions
        print("[*] Executing Cloud Task: fetch-sheets (Google Sheets)")
        success, msg, items = fetch_and_process_sheets()
        print(f"Result: {msg}")
        if items:
            print(f"[+] Loaded {len(items)} candidate stocks into watchlist from Google Sheets.")
        export_portfolio_snapshot()
        if not success:
            sys.exit(1)

    elif args.task == "trade-cycle":
        print("[*] Executing Cloud Task: trade-cycle (Portfolio 1: 200 DMA + Portfolio 2: Wyckoff Swing)")
        from backend.trading_engine import run_trading_cycle, run_p2_trading_cycle
        summary1 = run_trading_cycle(force_market_open=False)
        print(f"Portfolio 1 Result: {len(summary1.get('buys_triggered', []))} buys, {len(summary1.get('targets_hit', []))} targets, {len(summary1.get('stop_losses_hit', []))} stop-losses.")
        summary2 = run_p2_trading_cycle(force_market_open=False)
        print(f"Portfolio 2 Result: {len(summary2.get('buys_triggered', []))} buys, {len(summary2.get('targets_hit', []))} targets, {len(summary2.get('stop_losses_hit', []))} stop-losses.")
        export_portfolio_snapshot()

    elif args.task == "p2-trade-cycle":
        print("[*] Executing Cloud Task: p2-trade-cycle (Portfolio 2: Wyckoff Swing Delivery)")
        from backend.trading_engine import run_p2_trading_cycle
        summary2 = run_p2_trading_cycle(force_market_open=False)
        print(f"Portfolio 2 Result: {len(summary2.get('buys_triggered', []))} buys, {len(summary2.get('targets_hit', []))} targets, {len(summary2.get('stop_losses_hit', []))} stop-losses.")
        export_portfolio_snapshot()

    elif args.task == "export-snapshot":
        print("[*] Executing Cloud Task: export-snapshot")
        snap = export_portfolio_snapshot()
        print(f"Result: Portfolio snapshot exported with {len(snap.get('upcoming_trades', []))} upcoming trades.")

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
            if success:
                record_notification_sent(today_str, "DAILY_REPORT_630", msg)
        # Send dedicated Evening Top 10 Wyckoff candidates Telegram digest
        try:
            from backend.notifier import send_evening_p2_wyckoff_top10
            send_evening_p2_wyckoff_top10()
        except Exception as e:
            print(f"[!] Warning sending evening Wyckoff top 10: {e}")

        export_portfolio_snapshot()

    elif args.task == "evening-wyckoff":
        print("[*] Executing Cloud Task: evening-wyckoff (Send Top 10 Wyckoff Candidates to Telegram)")
        from backend.notifier import send_evening_p2_wyckoff_top10
        ok, msg = send_evening_p2_wyckoff_top10(force=True)
        print(f"Result: {msg}")

    elif args.task == "wyckoff-scan":
        print("[*] Executing Cloud Task: wyckoff-scan (Wyckoff + VSA Swing Screener)")
        from backend.wyckoff_analyzer import analyze_stock, result_to_dict
        from backend.database import get_all_watchlist, upsert_p2_watchlist, export_p2_snapshot
        from datetime import datetime

        wl = get_all_watchlist(limit=100)
        symbols = [w["symbol"] for w in wl if w.get("symbol")]
        if not symbols:
            symbols = [
                "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
                "SBIN.NS", "BHARTIARTL.NS", "TATAMOTORS.NS", "LT.NS", "ITC.NS"
            ]

        seen = set()
        unique = [s for s in symbols if not (s in seen or seen.add(s))]
        print(f"[i] Scanning {len(unique)} candidate symbols...")
        results, passed = [], []
        today = datetime.now().strftime("%Y-%m-%d")

        for sym in unique:
            try:
                r = analyze_stock(sym)
                d = result_to_dict(r)
                d["report_date"] = today
                results.append(d)
                if r.passed:
                    passed.append(d)
                    print(f"  [+] PASSED: {sym} (Score: {d['wyckoff_score']}, Phase: {d['phase_label']})")
            except Exception as e:
                print(f"  [!] Error scanning {sym}: {e}")

        if passed:
            upsert_p2_watchlist(passed)
        export_p2_snapshot()
        export_portfolio_snapshot()
        print(f"Result: Scanned {len(results)} stocks. {len(passed)} passed Wyckoff screening (score >= 60).")

if __name__ == "__main__":
    main()
