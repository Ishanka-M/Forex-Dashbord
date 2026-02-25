"""
modules/market_data.py
Live Market Data Fetcher using yfinance
"""

import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta
import pytz

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

# Symbol mapping: display name -> yfinance ticker
SYMBOL_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCAD": "USDCAD=X",
    "XAUUSD": "GC=F",       # Gold
    "XAGUSD": "SI=F",       # Silver
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "US30":   "^DJI",
    "NAS100": "^IXIC",
    "SPX500": "^GSPC",
}

TIMEFRAME_MAP = {
    "M5":  ("5m",  "1d"),
    "M15": ("15m", "5d"),
    "H1":  ("1h",  "30d"),
    "H4":  ("1h",  "60d"),   # yf doesn't have 4h; we resample
    "D1":  ("1d",  "365d"),
}

MAJOR_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "AUDUSD", "USDCAD", "BTCUSD"]


@st.cache_data(ttl=60)
def get_live_price(symbol: str) -> dict:
    """Get current price for a symbol."""
    ticker = SYMBOL_MAP.get(symbol, symbol)
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="1d", interval="1m")
        if hist.empty:
            return {"symbol": symbol, "price": None, "change": None, "change_pct": None, "volume": None}
        
        current = hist["Close"].iloc[-1]
        prev = hist["Close"].iloc[0]
        change = current - prev
        change_pct = (change / prev) * 100 if prev != 0 else 0
        volume = hist["Volume"].iloc[-1]
        
        return {
            "symbol": symbol,
            "price": round(current, 5),
            "change": round(change, 5),
            "change_pct": round(change_pct, 3),
            "volume": int(volume),
            "high": round(hist["High"].max(), 5),
            "low": round(hist["Low"].min(), 5),
        }
    except Exception as e:
        return {"symbol": symbol, "price": None, "change": None, "change_pct": None, "volume": None}


@st.cache_data(ttl=300)
def get_ohlcv(symbol: str, timeframe: str = "H1", period_override: str = None) -> pd.DataFrame:
    """Fetch OHLCV data for a symbol and timeframe."""
    ticker = SYMBOL_MAP.get(symbol, symbol)
    interval, default_period = TIMEFRAME_MAP.get(timeframe, ("1h", "30d"))
    period = period_override or default_period

    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()

        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        
        # Resample to H4 if needed
        if timeframe == "H4":
            df = df.resample("4H").agg({
                "open": "first", "high": "max", "low": "min",
                "close": "last", "volume": "sum"
            }).dropna()

        # Convert index to Colombo time
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(COLOMBO_TZ)
        
        return df
    except Exception as e:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def get_all_live_prices() -> list[dict]:
    """Get live prices for all major pairs."""
    prices = []
    for symbol in MAJOR_PAIRS:
        prices.append(get_live_price(symbol))
    return prices


def get_session_status() -> dict:
    """Determine which Forex sessions are currently active (in Colombo time)."""
    now_colombo = datetime.now(COLOMBO_TZ)
    now_utc = now_colombo.astimezone(pytz.UTC)
    hour_utc = now_utc.hour
    minute_utc = now_utc.minute
    time_decimal = hour_utc + minute_utc / 60

    sessions = {
        "Sydney":   {"open": 22.0,  "close": 7.0,   "color": "#4ECDC4", "utc_label": "22:00-07:00 UTC"},
        "Tokyo":    {"open": 0.0,   "close": 9.0,   "color": "#45B7D1", "utc_label": "00:00-09:00 UTC"},
        "London":   {"open": 8.0,   "close": 17.0,  "color": "#FFA07A", "utc_label": "08:00-17:00 UTC"},
        "New York": {"open": 13.0,  "close": 22.0,  "color": "#98D8C8", "utc_label": "13:00-22:00 UTC"},
    }

    result = {}
    for session, info in sessions.items():
        o, c = info["open"], info["close"]
        if o > c:  # Overnight session (Sydney)
            active = time_decimal >= o or time_decimal < c
        else:
            active = o <= time_decimal < c
        
        result[session] = {
            **info,
            "active": active,
            "overlap": False,
        }

    # Check overlaps
    if result["London"]["active"] and result["New York"]["active"]:
        result["London"]["overlap"] = True
        result["New York"]["overlap"] = True
    if result["Tokyo"]["active"] and result["London"]["active"]:
        result["Tokyo"]["overlap"] = True
        result["London"]["overlap"] = True

    return result


def get_colombo_time() -> str:
    return datetime.now(COLOMBO_TZ).strftime("%A, %d %b %Y  %H:%M:%S %Z")
