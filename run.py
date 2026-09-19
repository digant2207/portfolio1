"""
Application Launcher for Smart Money 200 DMA Paper Trading Terminal.
Runs FastAPI backend on http://127.0.0.1:8000
"""
import sys
from pathlib import Path
import uvicorn
from backend.config import load_config

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

if __name__ == "__main__":
    cfg = load_config()
    port = cfg.get("server_port", 8000)
    print("=" * 65)
    print("[*] Starting Smart Money 200 DMA Paper Trading Terminal")
    print(f"[*] Web Dashboard: http://127.0.0.1:{port}")
    print(f"[*] Automated Schedule: 18:05 IST Mail Fetch, Market Tracking, 15:45 IST EOD Report")
    print("=" * 65)
    
    uvicorn.run("backend.api:app", host="127.0.0.1", port=port, reload=False)
