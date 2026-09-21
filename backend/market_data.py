"""
Market data fetcher for NSE/BSE equities.
Uses yfinance to fetch live/latest traded price (LTP/CMP) and checks Indian market hours.
"""
from datetime import datetime, time
import pytz
import yfinance as yf
from typing import Dict, List, Optional, Any
from .config import load_config
from .database import log_event

IST = pytz.timezone("Asia/Kolkata")

# Cache to avoid hammering yfinance
_price_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 30

def is_market_open() -> bool:
    """
    Checks if Indian stock market (NSE/BSE) is open.
    Regular hours: Mon - Fri, 09:15 AM to 03:30 PM IST.
    """
    cfg = load_config()
    if cfg.get("simulate_market_hours", False):
        return True
        
    now = datetime.now(IST)
    # Weekday check: 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if now.weekday() >= 5:
        return False
        
    current_time = now.time()
    market_open = time(9, 15)
    market_close = time(15, 30)
    
    return market_open <= current_time <= market_close

def get_market_status() -> Dict[str, Any]:
    now = datetime.now(IST)
    open_flag = is_market_open()
    return {
        "is_open": open_flag,
        "current_ist_time": now.strftime("%Y-%m-%d %H:%M:%S IST"),
        "weekday": now.strftime("%A"),
        "market_hours": "09:15 - 15:30 IST (Mon - Fri)"
    }

def fetch_current_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetches latest price for given list of symbols (e.g. ['RELIANCE.NS', 'TCS.NS']).
    Returns dict mapping symbol -> float price.
    """
    if not symbols:
        return {}
        
    clean_symbols = list(set([s.strip().upper() for s in symbols if s]))
    results: Dict[str, float] = {}
    to_fetch: List[str] = []
    now_ts = datetime.now().timestamp()
    
    # Check cache
    for s in clean_symbols:
        cached = _price_cache.get(s)
        if cached and (now_ts - cached["timestamp"]) < CACHE_TTL_SECONDS:
            results[s] = cached["price"]
        else:
            to_fetch.append(s)
            
    if not to_fetch:
        return results
        
    try:
        # yfinance download or Ticker.fast_info
        # For batch, download is fast
        batch_tickers = " ".join(to_fetch)
        data = yf.Tickers(batch_tickers)
        
        for sym in to_fetch:
            try:
                ticker = data.tickers.get(sym)
                if not ticker:
                    continue
                info = getattr(ticker, "fast_info", None)
                price = None
                if info and hasattr(info, "last_price") and info.last_price:
                    price = float(info.last_price)
                elif info and hasattr(info, "regular_market_price") and info.regular_market_price:
                    price = float(info.regular_market_price)
                else:
                    # Fallback to history 1d
                    hist = ticker.history(period="1d", interval="1m")
                    if not hist.empty:
                        price = float(hist["Close"].iloc[-1])
                        
                if price and price > 0:
                    results[sym] = round(price, 2)
                    _price_cache[sym] = {"price": round(price, 2), "timestamp": now_ts}
            except Exception as item_err:
                pass
    except Exception as e:
        log_event("WARNING", f"Market data fetch error for symbols {to_fetch}: {e}")
        
    return results

def simulate_price_update(symbol: str, target_price: float):
    """Allows simulating a market price for test/demo purposes."""
    _price_cache[symbol.strip().upper()] = {"price": round(target_price, 2), "timestamp": datetime.now().timestamp() + 3600}

# Volume cache with 4-hour TTL (1-month average volume changes very slowly)
_volume_cache: Dict[str, Dict[str, Any]] = {}
VOLUME_CACHE_TTL_SECONDS = 14400

def fetch_monthly_average_volume(symbol: str) -> float:
    """
    Fetches the 1-month average daily trading volume for a given stock symbol using yfinance.
    Returns average volume as float.
    """
    sym = symbol.strip().upper()
    now_ts = datetime.now().timestamp()
    
    cached = _volume_cache.get(sym)
    if cached and (now_ts - cached["timestamp"]) < VOLUME_CACHE_TTL_SECONDS:
        return cached["volume"]
        
    try:
        ticker = yf.Ticker(sym)
        # Fetch 1-month daily historical data
        hist = ticker.history(period="1mo")
        if not hist.empty and "Volume" in hist.columns:
            # Calculate mean of daily volumes excluding days with 0 volume
            valid_volumes = hist["Volume"][hist["Volume"] > 0]
            if not valid_volumes.empty:
                avg_vol = float(valid_volumes.mean())
                _volume_cache[sym] = {"volume": round(avg_vol, 2), "timestamp": now_ts}
                return round(avg_vol, 2)
        
        # Fallback to fast_info or info if history was empty
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info:
            vol = getattr(fast_info, "three_month_average_volume", None) or getattr(fast_info, "ten_day_average_volume", None)
            if vol and vol > 0:
                avg_vol = float(vol)
                _volume_cache[sym] = {"volume": round(avg_vol, 2), "timestamp": now_ts}
                return round(avg_vol, 2)
    except Exception as e:
        log_event("WARNING", f"Could not fetch 1-month average volume for {sym}: {e}")
        
    return 0.0

def simulate_volume_update(symbol: str, volume: float):
    """Allows simulating stock volume for testing."""
    _volume_cache[symbol.strip().upper()] = {"volume": float(volume), "timestamp": datetime.now().timestamp() + 3600}

