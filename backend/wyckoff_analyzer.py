"""
Wyckoff & Volume Spread Analysis (VSA) Screening Engine — Portfolio 2.

Analyses the last 30–60 trading days of daily OHLCV data for each candidate
stock and scores it across four Wyckoff phases:

  Phase A/B  – Accumulation range detection (support floor & resistance ceiling)
  VSA        – Volume absorption score (supply exhaustion on red candles,
                institutional demand on green candles)
  Phase C    – Spring / shakeout detection (brief dip below support on light volume,
                immediate recovery into range)
  Phase D    – Sign of Strength (SOS) wide-range green candle with >=1.5x avg volume

Each stock receives a total Wyckoff score (0–100).  Stocks with a score >= 60
are considered high-conviction swing candidates for Portfolio 2.

Risk rules (per SWING_PORTFOLIO2_PLAN.md):
  - Stop-Loss:      -3.5% to -5%  (placed below the Spring low or swing support)
  - Target:         +8% to +14%   (Phase E markup)
  - Trailing Stop:  once gain hits +5%, move SL to breakeven; trail on 10 EMA
  - Time Stop:      exit after 10 trading sessions if neither target nor SL hit
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

import yfinance as yf


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOOKBACK_DAYS: int = 60          # How many trading days of history to analyse
RANGE_WINDOW: int = 30           # Days used to detect the accumulation range
SOS_VOLUME_MULTIPLIER: float = 1.5  # Phase D: volume must be >= 1.5x 20-day avg
SPRING_RECOVERY_BARS: int = 3    # Max bars allowed between dip & recovery
MIN_WYCKOFF_SCORE: int = 60      # Minimum score to pass screening

# Portfolio 2 risk parameters
SL_PCT_LOW: float = 3.5          # Minimum stop-loss distance (%)
SL_PCT_HIGH: float = 5.0         # Maximum stop-loss distance (%)
TARGET_PCT_LOW: float = 8.0      # Minimum profit target (%)
TARGET_PCT_HIGH: float = 14.0    # Maximum profit target (%)
TRAILING_TRIGGER_PCT: float = 5.0  # Move SL to breakeven once gain hits this %
TIME_STOP_SESSIONS: int = 10     # Exit after N trading sessions regardless


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class WyckoffResult:
    """Full Wyckoff analysis result for a single stock."""
    symbol: str
    stock_name: str
    cmp: float                       # Current market price at time of scan

    # Accumulation range
    support: float = 0.0
    resistance: float = 0.0
    range_width_pct: float = 0.0    # (resistance - support) / support * 100

    # VSA scores (each 0–25)
    absorption_score: float = 0.0   # Red candles on declining volume
    demand_score: float = 0.0       # Green candles on expanding volume

    # Phase flags
    spring_detected: bool = False
    spring_low: float = 0.0
    sos_detected: bool = False
    sos_candle_date: str = ""

    # Composite
    wyckoff_score: float = 0.0      # 0–100
    phase_label: str = "UNKNOWN"    # 'ACCUMULATION', 'MARKUP', 'DISTRIBUTION', 'MARKDOWN'

    # Entry plan
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    sl_pct: float = 0.0
    target_pct: float = 0.0

    # Extra context
    avg_volume_20d: float = 0.0
    latest_volume: float = 0.0
    latest_volume_vs_avg_pct: float = 0.0
    ema_10: float = 0.0

    # Diagnostics
    passed: bool = False
    failure_reason: str = ""
    raw_data_bars: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ema(values: List[float], period: int) -> float:
    """Returns the last EMA value for the given period."""
    if len(values) < period:
        return statistics.mean(values) if values else 0.0
    k = 2 / (period + 1)
    ema = statistics.mean(values[:period])
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return round(ema, 4)


def _avg_volume(volumes: List[float], window: int = 20) -> float:
    """Returns the average of the last `window` volume bars."""
    recent = volumes[-window:] if len(volumes) >= window else volumes
    return statistics.mean(recent) if recent else 0.0


def _fetch_ohlcv(symbol: str, days: int = LOOKBACK_DAYS) -> Optional[List[Dict[str, Any]]]:
    """
    Downloads daily OHLCV from Yahoo Finance for the last `days` trading days.
    Returns a list of dicts sorted oldest to newest, or None on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=f"{days}d", interval="1d", auto_adjust=True)
        if hist is None or hist.empty or len(hist) < 10:
            return None
        bars = []
        for ts, row in hist.iterrows():
            bars.append({
                "date":   str(ts.date()),
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        return bars
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Phase A/B – Accumulation range
# ---------------------------------------------------------------------------

def _detect_accumulation_range(
    bars: List[Dict[str, Any]],
    window: int = RANGE_WINDOW,
) -> Tuple[float, float, float]:
    """
    Identifies the consolidation support and resistance over the last `window` bars.
    Returns (support, resistance, range_width_pct).
    """
    recent = bars[-window:]
    lows   = sorted([b["low"]  for b in recent])
    highs  = sorted([b["high"] for b in recent])

    # 15th-percentile low, 85th-percentile high
    idx_low  = max(0, int(len(lows)  * 0.15) - 1)
    idx_high = min(len(highs) - 1, int(len(highs) * 0.85))
    support    = round(lows[idx_low],   2)
    resistance = round(highs[idx_high], 2)

    range_width_pct = round(((resistance - support) / support) * 100, 2) if support > 0 else 0.0
    return support, resistance, range_width_pct


# ---------------------------------------------------------------------------
# VSA – Volume Spread Analysis
# ---------------------------------------------------------------------------

def _vsa_absorption_score(bars: List[Dict[str, Any]], window: int = 20) -> float:
    """
    Checks that red (down) candles within the accumulation window have
    declining or below-average volume -> supply exhaustion.

    Score: 0–25.
    """
    recent = bars[-window:]
    avg_vol = _avg_volume([b["volume"] for b in recent], window)
    if avg_vol <= 0:
        return 0.0

    red_bars = [b for b in recent if b["close"] < b["open"]]
    if not red_bars:
        return 12.5   # Neutral — no red candles is mildly bullish

    below_avg = sum(1 for b in red_bars if b["volume"] < avg_vol)
    score = (below_avg / len(red_bars)) * 25
    return round(score, 2)


def _vsa_demand_score(bars: List[Dict[str, Any]], window: int = 20) -> float:
    """
    Checks that green (up) candles within the accumulation window have
    expanding or above-average volume -> institutional demand.

    Score: 0–25.
    """
    recent = bars[-window:]
    avg_vol = _avg_volume([b["volume"] for b in recent], window)
    if avg_vol <= 0:
        return 0.0

    green_bars = [b for b in recent if b["close"] >= b["open"]]
    if not green_bars:
        return 0.0

    above_avg = sum(1 for b in green_bars if b["volume"] > avg_vol)
    score = (above_avg / len(green_bars)) * 25
    return round(score, 2)


# ---------------------------------------------------------------------------
# Phase C – Spring / Shakeout
# ---------------------------------------------------------------------------

def _detect_spring(
    bars: List[Dict[str, Any]],
    support: float,
    window: int = RANGE_WINDOW,
    recovery_bars: int = SPRING_RECOVERY_BARS,
) -> Tuple[bool, float]:
    """
    Detects a Wyckoff Spring: price briefly dips below `support`, then
    recovers and closes back above `support` within `recovery_bars` sessions.

    Returns (spring_detected, spring_low_price).
    """
    recent = bars[-window:]
    avg_vol = _avg_volume([b["volume"] for b in recent])

    for i, bar in enumerate(recent):
        if bar["low"] < support and bar["close"] > support:
            # Same-bar recovery (immediate spring)
            if bar["volume"] < avg_vol * 0.9:
                return True, round(bar["low"], 2)

        elif bar["low"] < support and bar["close"] < support:
            # Multi-bar spring — look for recovery within recovery_bars
            spring_low = bar["low"]
            spring_vol = bar["volume"]
            for j in range(i + 1, min(i + 1 + recovery_bars, len(recent))):
                if recent[j]["close"] > support:
                    if spring_vol < avg_vol * 0.9:
                        return True, round(spring_low, 2)
                    break  # Recovery happened but volume was high -> not a clean spring

    return False, 0.0


# ---------------------------------------------------------------------------
# Phase D – Sign of Strength (SOS) + Breakout
# ---------------------------------------------------------------------------

def _detect_sos(
    bars: List[Dict[str, Any]],
    resistance: float,
    vol_multiplier: float = SOS_VOLUME_MULTIPLIER,
) -> Tuple[bool, str]:
    """
    Detects a Sign of Strength (SOS): a wide-range green candle that:
      1. Closes near the session high (upper 25% of the candle range)
      2. Has volume >= vol_multiplier x 20-day average
      3. Closes above or near the resistance level

    Searches the last 10 bars for a recent SOS.
    Returns (sos_detected, date_string).
    """
    if len(bars) < 20:
        return False, ""

    avg_vol = _avg_volume([b["volume"] for b in bars], window=20)
    if avg_vol <= 0:
        return False, ""

    search_bars = bars[-10:]
    for bar in reversed(search_bars):
        candle_range = bar["high"] - bar["low"]
        if candle_range <= 0:
            continue
        upper_close = (bar["close"] - bar["low"]) / candle_range >= 0.75
        is_green    = bar["close"] > bar["open"]
        high_vol    = bar["volume"] >= avg_vol * vol_multiplier
        near_resist = bar["close"] >= resistance * 0.985   # within 1.5% of resistance or above

        if is_green and upper_close and high_vol and near_resist:
            return True, bar["date"]

    return False, ""


# ---------------------------------------------------------------------------
# Score assembly
# ---------------------------------------------------------------------------

def _compute_wyckoff_score(result: WyckoffResult) -> float:
    """
    Combines sub-scores into a 0–100 composite Wyckoff score.

    Weights:
      Absorption score (VSA red)    0–25
      Demand score (VSA green)      0–25
      Spring bonus                  0–20
      SOS bonus                     0–20
      Range quality (tight range)   0–10
    """
    score = result.absorption_score + result.demand_score

    if result.spring_detected:
        score += 20
    if result.sos_detected:
        score += 20

    # Range quality: favour tight, well-defined ranges (5–15%)
    rw = result.range_width_pct
    if 5.0 <= rw <= 15.0:
        score += 10
    elif 3.0 <= rw < 5.0 or 15.0 < rw <= 20.0:
        score += 5

    return round(min(score, 100.0), 2)


def _phase_label(result: WyckoffResult) -> str:
    """Assigns a human-readable Wyckoff phase label."""
    if result.wyckoff_score >= 80:
        return "PHASE_D_MARKUP"
    if result.spring_detected and result.wyckoff_score >= 60:
        return "PHASE_C_SPRING"
    if result.absorption_score >= 15 and result.wyckoff_score >= 40:
        return "PHASE_B_ACCUMULATION"
    if result.wyckoff_score >= 20:
        return "PHASE_A_STOPPING"
    return "UNCERTAIN"


# ---------------------------------------------------------------------------
# Entry plan
# ---------------------------------------------------------------------------

def _build_entry_plan(result: WyckoffResult) -> WyckoffResult:
    """
    Populates stop_loss, target_price, and entry_price on the result.

    Stop-Loss anchor:
      - If a spring was detected, SL is placed 0.5% below the spring low.
      - Otherwise, SL is placed below the support floor (-3.5% to -5%).

    Target:
      - +8% (conservative) to +14% (aggressive) from entry.
      - Use +8% for score 60–75, +11% for 76–89, +14% for 90+.
    """
    cmp = result.cmp
    if cmp <= 0:
        return result

    # Breakout Trigger Level:
    # If CMP is below resistance, breakout confirms when price breaks through resistance ceiling (+0.5%).
    # If CMP is already above resistance, current price is the confirmed breakout level.
    if result.resistance > 0 and cmp < result.resistance:
        trigger_price = round(result.resistance * 1.005, 2)
    else:
        trigger_price = round(cmp, 2)

    result.entry_price = trigger_price

    # Stop-Loss: placed below spring low or support floor (-3.5% to -5.0%)
    if result.spring_detected and result.spring_low > 0:
        sl = round(result.spring_low * 0.995, 2)
        sl_pct = round(((trigger_price - sl) / trigger_price) * 100, 2)
        if sl_pct < SL_PCT_LOW:
            sl_pct = SL_PCT_LOW
            sl = round(trigger_price * (1 - sl_pct / 100), 2)
        elif sl_pct > SL_PCT_HIGH:
            sl_pct = SL_PCT_HIGH
            sl = round(trigger_price * (1 - sl_pct / 100), 2)
    else:
        sl_pct = SL_PCT_LOW + ((SL_PCT_HIGH - SL_PCT_LOW) * (1 - result.wyckoff_score / 100))
        sl_pct = round(max(SL_PCT_LOW, min(sl_pct, SL_PCT_HIGH)), 2)
        sl = round(trigger_price * (1 - sl_pct / 100), 2)

    result.stop_loss = sl
    result.sl_pct    = sl_pct

    # Target: +8% to +14% markup from breakout trigger
    if result.wyckoff_score >= 90:
        target_pct = TARGET_PCT_HIGH
    elif result.wyckoff_score >= 76:
        target_pct = (TARGET_PCT_LOW + TARGET_PCT_HIGH) / 2   # 11%
    else:
        target_pct = TARGET_PCT_LOW

    result.target_price = round(trigger_price * (1 + target_pct / 100), 2)
    result.target_pct   = target_pct
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_stock(symbol: str, stock_name: str = "") -> WyckoffResult:
    """
    Runs the full Wyckoff + VSA analysis for a single stock.

    Args:
        symbol:     NSE ticker symbol (e.g. 'RELIANCE.NS').
        stock_name: Human-readable company name (optional).

    Returns:
        WyckoffResult with all computed metrics and entry plan.
    """
    result = WyckoffResult(symbol=symbol, stock_name=stock_name or symbol, cmp=0.0)

    bars = _fetch_ohlcv(symbol, days=LOOKBACK_DAYS)
    if not bars:
        result.failure_reason = "Could not fetch OHLCV data from Yahoo Finance."
        return result

    result.raw_data_bars = len(bars)
    result.cmp = bars[-1]["close"]

    if result.cmp <= 0:
        result.failure_reason = "Invalid CMP (<=0) received."
        return result

    # Phase A/B
    support, resistance, range_width_pct = _detect_accumulation_range(bars, window=RANGE_WINDOW)
    result.support         = support
    result.resistance      = resistance
    result.range_width_pct = range_width_pct

    # VSA
    result.absorption_score = _vsa_absorption_score(bars, window=20)
    result.demand_score     = _vsa_demand_score(bars, window=20)

    # Phase C
    result.spring_detected, result.spring_low = _detect_spring(bars, support, window=RANGE_WINDOW)

    # Phase D
    result.sos_detected, result.sos_candle_date = _detect_sos(bars, resistance)

    # Volume context
    volumes = [b["volume"] for b in bars]
    result.avg_volume_20d = round(_avg_volume(volumes, window=20), 0)
    result.latest_volume  = volumes[-1]
    if result.avg_volume_20d > 0:
        result.latest_volume_vs_avg_pct = round(
            (result.latest_volume / result.avg_volume_20d) * 100, 1
        )

    # 10 EMA
    closes = [b["close"] for b in bars]
    result.ema_10 = round(_ema(closes, period=10), 2)

    # Composite score
    result.wyckoff_score = _compute_wyckoff_score(result)
    result.phase_label   = _phase_label(result)

    # Entry plan
    result = _build_entry_plan(result)

    # Pass/fail gate
    if result.wyckoff_score >= MIN_WYCKOFF_SCORE:
        result.passed = True
    else:
        result.failure_reason = (
            f"Wyckoff score {result.wyckoff_score:.0f} is below minimum {MIN_WYCKOFF_SCORE}. "
            f"Phase: {result.phase_label}. "
            f"(Absorption={result.absorption_score:.1f}, "
            f"Demand={result.demand_score:.1f}, "
            f"Spring={'YES' if result.spring_detected else 'NO'}, "
            f"SOS={'YES' if result.sos_detected else 'NO'})"
        )

    return result


def screen_candidates(
    candidates: List[Dict[str, Any]],
    min_score: int = MIN_WYCKOFF_SCORE,
) -> List[WyckoffResult]:
    """
    Runs Wyckoff analysis on a list of candidate stocks (e.g. from Google Sheet).

    Args:
        candidates: List of dicts with at least 'symbol' and optionally 'stock_name'.
        min_score:  Minimum Wyckoff score to include in results.

    Returns:
        List of WyckoffResult sorted by wyckoff_score descending (highest conviction first).
        Only stocks that PASS the min_score gate are included.
    """
    results: List[WyckoffResult] = []
    for c in candidates:
        sym  = c.get("symbol", "")
        name = c.get("stock_name", sym)
        if not sym:
            continue
        r = analyze_stock(sym, name)
        if r.passed and r.wyckoff_score >= min_score:
            results.append(r)

    results.sort(key=lambda x: x.wyckoff_score, reverse=True)
    return results


def result_to_dict(r: WyckoffResult) -> Dict[str, Any]:
    """Converts a WyckoffResult to a plain dict (JSON-serialisable)."""
    return {
        "symbol":                    r.symbol,
        "stock_name":                r.stock_name,
        "cmp":                       r.cmp,
        "wyckoff_score":             r.wyckoff_score,
        "phase_label":               r.phase_label,
        "passed":                    r.passed,
        "failure_reason":            r.failure_reason,
        # Range
        "support":                   r.support,
        "resistance":                r.resistance,
        "range_width_pct":           r.range_width_pct,
        # VSA
        "absorption_score":          r.absorption_score,
        "demand_score":              r.demand_score,
        # Phase flags
        "spring_detected":           r.spring_detected,
        "spring_low":                r.spring_low,
        "sos_detected":              r.sos_detected,
        "sos_candle_date":           r.sos_candle_date,
        # Volume
        "avg_volume_20d":            r.avg_volume_20d,
        "latest_volume":             r.latest_volume,
        "latest_volume_vs_avg_pct":  r.latest_volume_vs_avg_pct,
        "ema_10":                    r.ema_10,
        # Entry plan
        "entry_price":               r.entry_price,
        "stop_loss":                 r.stop_loss,
        "sl_pct":                    r.sl_pct,
        "target_price":              r.target_price,
        "target_pct":                r.target_pct,
        # Meta
        "raw_data_bars":             r.raw_data_bars,
        "trailing_trigger_pct":      TRAILING_TRIGGER_PCT,
        "time_stop_sessions":        TIME_STOP_SESSIONS,
        "portfolio_id":              2,
        "strategy":                  "WYCKOFF_SWING_DELIVERY",
    }
