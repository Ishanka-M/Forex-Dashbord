"""
modules/market_data.py
Live Market Data Fetcher — bulletproof yfinance parsing
Handles MultiIndex columns, timezone issues, empty DataFrames
"""

import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime
import pytz
import warnings
warnings.filterwarnings("ignore")

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

# ── Symbol Map ───────────────────────────────────────────────────────────────
SYMBOL_MAP = {
    # Majors
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCAD": "USDCAD=X",
    # Crosses
    "EURGBP": "EURGBP=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
    "AUDJPY": "AUDJPY=X",
    "CADJPY": "CADJPY=X",
    "CHFJPY": "CHFJPY=X",
    "EURCHF": "EURCHF=X",
    "EURAUD": "EURAUD=X",
    "EURCAD": "EURCAD=X",
    "GBPCHF": "GBPCHF=X",
    "GBPAUD": "GBPAUD=X",
    "GBPCAD": "GBPCAD=X",
    "AUDCAD": "AUDCAD=X",
    "AUDCHF": "AUDCHF=X",
    "AUDNZD": "AUDNZD=X",
    "NZDJPY": "NZDJPY=X",
    "NZDCAD": "NZDCAD=X",
    "NZDCHF": "NZDCHF=X",
    "CADCHF": "CADCHF=X",
    # Exotics
    "USDSEK": "USDSEK=X",
    "USDNOK": "USDNOK=X",
    "USDSGD": "USDSGD=X",
    "USDMXN": "USDMXN=X",
    "USDZAR": "USDZAR=X",
    "USDTRY": "USDTRY=X",
    # Metals
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "XPTUSD": "PL=F",
    # Commodities
    "USOIL":  "CL=F",
    "UKOIL":  "BZ=F",
    # Crypto
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "BNBUSD": "BNB-USD",
    "SOLUSD": "SOL-USD",
    "XRPUSD": "XRP-USD",
    # Indices
    "US30":   "^DJI",
    "NAS100": "^IXIC",
    "SPX500": "^GSPC",
    "UK100":  "^FTSE",
    "GER40":  "^GDAXI",
    "JPN225": "^N225",
}

SYMBOL_CATEGORIES = {
    "⭐ Major Pairs":  ["EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","NZDUSD","USDCAD"],
    "🔀 Cross Pairs":  ["EURGBP","EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY",
                        "EURCHF","EURAUD","EURCAD","GBPCHF","GBPAUD","GBPCAD",
                        "AUDCAD","AUDCHF","AUDNZD","NZDJPY","NZDCAD","NZDCHF","CADCHF"],
    "🌍 Exotic Pairs": ["USDSEK","USDNOK","USDSGD","USDMXN","USDZAR","USDTRY"],
    "🥇 Metals":       ["XAUUSD","XAGUSD","XPTUSD"],
    "🛢️ Commodities":  ["USOIL","UKOIL"],
    "₿  Crypto":       ["BTCUSD","ETHUSD","BNBUSD","SOLUSD","XRPUSD"],
    "📊 Indices":      ["US30","NAS100","SPX500","UK100","GER40","JPN225"],
}

MAJOR_PAIRS = [
    "EURUSD","GBPUSD","USDJPY","XAUUSD",
    "AUDUSD","USDCAD","BTCUSD","GBPJPY",
    "EURJPY","USOIL",
]

TIMEFRAME_MAP = {
    "M1":  ("1m",  "1d"),
    "M5":  ("5m",  "2d"),
    "M15": ("15m", "5d"),
    "H1":  ("1h",  "30d"),
    "H4":  ("1h",  "60d"),   # resample 1h → 4h
    "D1":  ("1d",  "365d"),
    "W1":  ("1wk", "730d"),
}


# ── Core DataFrame cleaner ────────────────────────────────────────────────────
def _clean_df(raw: pd.DataFrame, timeframe: str = "H1") -> pd.DataFrame:
    """
    Normalize any yfinance DataFrame regardless of:
    - MultiIndex columns  (new yfinance >= 0.2.38)
    - Single-level columns (old yfinance)
    - Mixed case column names
    Returns clean df with [open, high, low, close, volume] or empty df.
    """
    if raw is None or raw.empty:
        return pd.DataFrame()

    df = raw.copy()

    # ── 1. Flatten MultiIndex columns ────────────────────────────────────
    if isinstance(df.columns, pd.MultiIndex):
        # MultiIndex looks like: ('Close', 'EURUSD=X'), ('High', 'EURUSD=X')…
        # Take only the first level (price type)
        df.columns = [str(c[0]).strip() if isinstance(c, tuple) else str(c).strip()
                      for c in df.columns]

    # ── 2. Lowercase all column names ────────────────────────────────────
    df.columns = [c.lower().strip() for c in df.columns]

    # ── 3. Rename common variants ─────────────────────────────────────────
    rename_map = {
        "adj close": "close",
        "adj_close": "close",
        "adjclose":  "close",
    }
    df = df.rename(columns=rename_map)

    # ── 4. Keep only OHLCV columns ────────────────────────────────────────
    needed = ["open", "high", "low", "close"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return pd.DataFrame()

    keep = needed + (["volume"] if "volume" in df.columns else [])
    df = df[keep].copy()

    # ── 5. Drop rows where OHLC are all NaN ──────────────────────────────
    df = df.dropna(subset=needed, how="all")
    df = df[df["close"].notna() & (df["close"] > 0)]

    if df.empty:
        return pd.DataFrame()

    # ── 6. Resample to H4 if needed ──────────────────────────────────────
    if timeframe == "H4":
        agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
        if "volume" in df.columns:
            agg["volume"] = "sum"
        try:
            df = df.resample("4h").agg(agg).dropna(subset=["close"])
        except Exception:
            pass

    # ── 7. Timezone → Asia/Colombo ────────────────────────────────────────
    try:
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(COLOMBO_TZ)
    except Exception:
        pass

    # ── 8. Ensure numeric types ───────────────────────────────────────────
    for col in keep:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"])
    return df


# ── OHLCV Fetcher ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def get_ohlcv(symbol: str, timeframe: str = "H1",
              period_override: str = None) -> pd.DataFrame:
    """
    Fetch OHLCV data for symbol + timeframe.
    Returns clean DataFrame with Colombo TZ index, or empty DataFrame on failure.
    """
    ticker = SYMBOL_MAP.get(symbol, symbol)
    interval, default_period = TIMEFRAME_MAP.get(timeframe, ("1h", "30d"))
    period = period_override or default_period

    # ── Strategy 1: yf.download ──────────────────────────────────────────
    try:
        raw = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
            threads=False,
        )
        df = _clean_df(raw, timeframe)
        if not df.empty and len(df) >= 10:
            return df
    except Exception:
        pass

    # ── Strategy 2: yf.Ticker.history ────────────────────────────────────
    try:
        raw = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            auto_adjust=True,
        )
        df = _clean_df(raw, timeframe)
        if not df.empty and len(df) >= 10:
            return df
    except Exception:
        pass

    # ── Strategy 3: shorter period fallback ──────────────────────────────
    fallback_periods = {
        "1d": "2d", "5d": "7d", "30d": "60d",
        "60d": "90d", "365d": "2y"
    }
    fb_period = fallback_periods.get(period)
    if fb_period:
        try:
            raw = yf.Ticker(ticker).history(
                period=fb_period,
                interval=interval,
                auto_adjust=True,
            )
            df = _clean_df(raw, timeframe)
            if not df.empty:
                return df
        except Exception:
            pass

    return pd.DataFrame()


# ── Live Price ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def get_live_price(symbol: str) -> dict:
    """Get current live price. Falls back to D1 close if 1m data unavailable."""
    ticker = SYMBOL_MAP.get(symbol, symbol)
    base   = {"symbol": symbol, "price": None, "change": None,
               "change_pct": None, "volume": None, "high": None, "low": None}

    for interval, period in [("5m", "2d"), ("1h", "5d"), ("1d", "30d")]:
        try:
            t   = yf.Ticker(ticker)
            raw = t.history(period=period, interval=interval, auto_adjust=True)
            df  = _clean_df(raw)
            if df.empty or len(df) < 2:
                continue

            current = float(df["close"].iloc[-1])
            prev    = float(df["close"].iloc[-2])
            change  = current - prev
            pct     = (change / prev * 100) if prev else 0
            vol     = int(df["volume"].iloc[-1]) if "volume" in df.columns else 0

            return {
                "symbol":     symbol,
                "price":      round(current, 5),
                "change":     round(change, 5),
                "change_pct": round(pct, 3),
                "volume":     vol,
                "high":       round(float(df["high"].max()), 5),
                "low":        round(float(df["low"].min()), 5),
            }
        except Exception:
            continue

    return base


@st.cache_data(ttl=30, show_spinner=False)
def get_all_live_prices(symbols: list = None) -> list:
    return [get_live_price(s) for s in (symbols or MAJOR_PAIRS)]


# ── Session Status ────────────────────────────────────────────────────────────
def get_session_status() -> dict:
    t = datetime.now(pytz.UTC)
    h = t.hour + t.minute / 60
    sessions = {
        "Sydney":   {"open": 22.0, "close": 7.0,  "color": "#4ECDC4", "utc_label": "22:00–07:00 UTC"},
        "Tokyo":    {"open": 0.0,  "close": 9.0,  "color": "#45B7D1", "utc_label": "00:00–09:00 UTC"},
        "London":   {"open": 8.0,  "close": 17.0, "color": "#FFA07A", "utc_label": "08:00–17:00 UTC"},
        "New York": {"open": 13.0, "close": 22.0, "color": "#98D8C8", "utc_label": "13:00–22:00 UTC"},
    }
    result = {}
    for name, info in sessions.items():
        o, c = info["open"], info["close"]
        active = (h >= o or h < c) if o > c else (o <= h < c)
        result[name] = {**info, "active": active, "overlap": False}
    if result["London"]["active"] and result["New York"]["active"]:
        result["London"]["overlap"] = result["New York"]["overlap"] = True
    if result["Tokyo"]["active"] and result["London"]["active"]:
        result["Tokyo"]["overlap"] = result["London"]["overlap"] = True
    return result


def get_colombo_time() -> str:
    return datetime.now(COLOMBO_TZ).strftime("%A, %d %b %Y  %H:%M:%S %Z")


def get_all_symbols() -> list:
    return list(SYMBOL_MAP.keys())
