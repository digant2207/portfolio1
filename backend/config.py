"""
Configuration manager for Paper Trading system.
Loads settings from config.json if available, otherwise environment or defaults.
"""
import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "portfolio.db"

DEFAULT_CONFIG = {
    # Capital & Trade Management
    "total_capital": 100000.0,
    "trade_allocation": 10000.0,
    "max_active_trades": 10,
    "stop_loss_pct": 2.0,       # 2% stop loss
    "target_pct": 5.0,          # 5% minimum target
    "trigger_buffer_pct": 1.0,  # 200 DMA + 1%
    "min_stock_price": 20.0,    # Ignore stocks with CMP <= 20
    "min_1m_avg_volume": 10000, # Ignore stocks with 1-month avg volume < 10,000
    
    # Gmail Configuration
    "gmail_user": "",
    "gmail_app_password": "",
    "gmail_imap_server": "imap.gmail.com",
    "gmail_smtp_server": "smtp.gmail.com",
    "gmail_smtp_port": 587,
    "email_report_subject": "Daily smart money finder report",
    "notification_recipient": "",
    
    # Engine Settings
    "market_check_interval_seconds": 120, # 2 minutes
    "simulate_market_hours": False,       # Allow executing tests outside 9:15-15:30 IST
    "server_port": 8000
}

def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config.update(saved)
        except Exception as e:
            print(f"Error loading config.json: {e}")
            
    # Allow Environment Variables (e.g. from GitHub Actions Secrets or Cloud hosting)
    env_user = os.environ.get("GMAIL_USER")
    if env_user:
        config["gmail_user"] = env_user.strip()
        
    env_pwd = os.environ.get("GMAIL_APP_PASSWORD")
    if env_pwd:
        config["gmail_app_password"] = env_pwd.strip()
        
    env_recipient = os.environ.get("NOTIFICATION_RECIPIENT")
    if env_recipient:
        config["notification_recipient"] = env_recipient.strip()
        
    env_port = os.environ.get("PORT")
    if env_port:
        try:
            config["server_port"] = int(env_port)
        except ValueError:
            pass
            
    return config

def save_config(new_config: dict) -> dict:
    current = load_config()
    current.update(new_config)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current

