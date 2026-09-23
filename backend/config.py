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
DEFAULT_DB_PATH = DATA_DIR / "portfolio.db"

def get_db_path() -> Path:
    env_path = os.environ.get("PORTFOLIO_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH

DB_PATH = DEFAULT_DB_PATH

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
    "only_above_200_dma": True, # Strictly buy only stocks above 200 DMA; exclude below 200 DMA
    
    # Google Sheets Data Source (Unified Sheet)
    "google_sheet_id": "1EKaY7YGSgQWnPrs57naHhJCSHp7VJ_PvXdFhzBfow1w",
    
    # Gmail SMTP Configuration (for sending notifications only)
    "gmail_user": "",
    "gmail_app_password": "",
    "gmail_smtp_server": "smtp.gmail.com",
    "gmail_smtp_port": 587,
    "notification_recipient": "",
    
    # Telegram Configuration
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    
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
    if env_user and env_user.strip():
        config["gmail_user"] = env_user.strip()
        
    env_pwd = os.environ.get("GMAIL_APP_PASSWORD")
    if env_pwd and env_pwd.strip():
        config["gmail_app_password"] = env_pwd.strip()
        
    env_recipient = os.environ.get("NOTIFICATION_RECIPIENT")
    if env_recipient and env_recipient.strip():
        config["notification_recipient"] = env_recipient.strip()

    env_tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if env_tg_token and env_tg_token.strip():
        config["telegram_bot_token"] = env_tg_token.strip()

    env_tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
    if env_tg_chat and env_tg_chat.strip():
        config["telegram_chat_id"] = env_tg_chat.strip()
        
    env_sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if env_sheet_id and env_sheet_id.strip():
        config["google_sheet_id"] = env_sheet_id.strip()

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

