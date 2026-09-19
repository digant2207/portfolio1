"""
Quick verification script to test Gmail IMAP and SMTP connectivity.
Run with: .\\.venv\\Scripts\\python.exe test_gmail.py
"""
import sys
from pathlib import Path

# Fix console encoding
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.config import load_config
from backend.mail_reader import fetch_and_parse_gmail_report

def main():
    cfg = load_config()
    user = cfg.get("gmail_user", "").strip()
    pwd = cfg.get("gmail_app_password", "").strip()
    
    print("=" * 60)
    print("📬 GMAIL CONNECTION & REPORT PARSER TEST")
    print("=" * 60)
    print(f"User: {user or '[NOT SET]'}")
    print(f"App Password: {'[CONFIGURED]' if pwd else '[NOT SET]'}")
    print(f"Target Subject: '{cfg.get('email_report_subject')}'")
    print("-" * 60)
    
    if not user or not pwd:
        print("[!] Gmail credentials are not configured yet.")
        print("Please configure them via the dashboard (http://127.0.0.1:8000 -> ⚙️ Settings)")
        print("or edit config.json.")
        return
        
    print("[*] Connecting to Gmail IMAP...")
    success, message, items = fetch_and_parse_gmail_report()
    
    if success:
        print(f"[OK] {message}")
        if items:
            print(f"\n[+] Found {len(items)} stocks in latest report:")
            for it in items:
                print(f"    • {it['symbol']} | {it['section']} | CMP: Rs.{it['cmp_report']} | 200DMA: Rs.{it['dma_200']} | Buy Trigger: Rs.{it['trigger_price']}")
        else:
            print("[i] Connected to Gmail successfully, but no matching report was found yet.")
    else:
        print(f"[ERROR] Connection failed: {message}")

if __name__ == "__main__":
    main()
