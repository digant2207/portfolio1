"""
Market data fetcher for NSE/BSE equities.
Uses yfinance to fetch live/latest traded price (LTP/CMP) and checks Indian market hours.
"""
from datetime import datetime, time
import logging
import pytz
import yfinance as yf
from typing import Dict, List, Optional, Any
from .config import load_config
from .database import log_event

# Suppress yfinance noisy connection and download warnings
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

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

def fetch_market_quotes(symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Fetches latest price, day high, day low, and open for given list of symbols.
    Returns dict mapping symbol -> {"price": float, "high": float, "low": float, "open": float}.
    """
    if not symbols:
        return {}
        
    clean_symbols = list(set([s.strip().upper() for s in symbols if s]))
    results: Dict[str, Dict[str, float]] = {}
    to_fetch: List[str] = []
    now_ts = datetime.now().timestamp()
    
    # Check cache
    for s in clean_symbols:
        cached = _price_cache.get(s)
        if cached and (now_ts - cached.get("timestamp", 0)) < CACHE_TTL_SECONDS:
            results[s] = {
                "price": cached.get("price", 0.0),
                "high": cached.get("high", cached.get("price", 0.0)),
                "low": cached.get("low", cached.get("price", 0.0)),
                "open": cached.get("open", cached.get("price", 0.0))
            }
        else:
            to_fetch.append(s)
            
    if not to_fetch:
        return results
        
    # Fetch in chunks of 50 using multi-threaded yf.download
    chunk_size = 50
    for i in range(0, len(to_fetch), chunk_size):
        chunk = to_fetch[i:i + chunk_size]
        try:
            df = yf.download(tickers=chunk, period="1d", interval="1d", progress=False, group_by="ticker", threads=True)
            if not df.empty:
                if len(chunk) == 1:
                    s = chunk[0]
                    if "Close" in df.columns:
                        c_series = df["Close"].dropna()
                        h_series = df["High"].dropna() if "High" in df.columns else c_series
                        l_series = df["Low"].dropna() if "Low" in df.columns else c_series
                        o_series = df["Open"].dropna() if "Open" in df.columns else c_series
                        if not c_series.empty and float(c_series.iloc[-1]) > 0:
                            c = round(float(c_series.iloc[-1]), 2)
                            h = round(float(h_series.iloc[-1]), 2) if not h_series.empty else c
                            l = round(float(l_series.iloc[-1]), 2) if not l_series.empty else c
                            o = round(float(o_series.iloc[-1]), 2) if not o_series.empty else c
                            quote = {"price": c, "high": h, "low": l, "open": o}
                            results[s] = quote
                            _price_cache[s] = {**quote, "timestamp": now_ts}
                else:
                    for s in chunk:
                        try:
                            if hasattr(df.columns, 'levels') and s in df.columns.levels[0]:
                                t_df = df[s]
                                if "Close" in t_df.columns:
                                    c_series = t_df["Close"].dropna()
                                    h_series = t_df["High"].dropna() if "High" in t_df.columns else c_series
                                    l_series = t_df["Low"].dropna() if "Low" in t_df.columns else c_series
                                    o_series = t_df["Open"].dropna() if "Open" in t_df.columns else c_series
                                    if not c_series.empty and float(c_series.iloc[-1]) > 0:
                                        c = round(float(c_series.iloc[-1]), 2)
                                        h = round(float(h_series.iloc[-1]), 2) if not h_series.empty else c
                                        l = round(float(l_series.iloc[-1]), 2) if not l_series.empty else c
                                        o = round(float(o_series.iloc[-1]), 2) if not o_series.empty else c
                                        quote = {"price": c, "high": h, "low": l, "open": o}
                                        results[s] = quote
                                        _price_cache[s] = {**quote, "timestamp": now_ts}
                        except Exception:
                            pass
        except Exception as batch_err:
            log_event("DEBUG", f"Batch download error for chunk: {batch_err}")

    # Fallback for any un-fetched symbol via fast_info
    missing = [s for s in to_fetch if s not in results]
    if missing and len(missing) <= 10:
        for sym in missing:
            try:
                t = yf.Ticker(sym)
                info = getattr(t, "fast_info", None)
                p = getattr(info, "last_price", None) or getattr(info, "regular_market_price", None)
                if p and float(p) > 0:
                    c = round(float(p), 2)
                    h = round(float(getattr(info, "day_high", None) or getattr(info, "dayHigh", None) or c), 2)
                    l = round(float(getattr(info, "day_low", None) or getattr(info, "dayLow", None) or c), 2)
                    o = round(float(getattr(info, "open", None) or getattr(info, "regular_market_open", None) or c), 2)
                    quote = {"price": c, "high": h, "low": l, "open": o}
                    results[sym] = quote
                    _price_cache[sym] = {**quote, "timestamp": now_ts}
            except Exception:
                pass
                
    return results

def fetch_current_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetches latest price for given list of symbols (e.g. ['RELIANCE.NS', 'TCS.NS']).
    Returns dict mapping symbol -> float price.
    """
    quotes = fetch_market_quotes(symbols)
    return {s: q["price"] for s, q in quotes.items()}

def simulate_price_update(symbol: str, target_price: float, high: Optional[float] = None, low: Optional[float] = None, open_price: Optional[float] = None):
    """Allows simulating a market price and optional High/Low for test/demo purposes."""
    sym = symbol.strip().upper()
    c = round(target_price, 2)
    h = round(high, 2) if high is not None else c
    l = round(low, 2) if low is not None else c
    o = round(open_price, 2) if open_price is not None else c
    _price_cache[sym] = {
        "price": c,
        "high": h,
        "low": l,
        "open": o,
        "timestamp": datetime.now().timestamp() + 3600
    }

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

