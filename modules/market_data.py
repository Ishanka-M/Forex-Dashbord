"""
modules/market_data.py
Live Market Data Fetcher
Strategy 1: yfinance (fast)
Strategy 2: Yahoo Finance v8 API direct (rate-limit bypass)
Strategy 3: Yahoo Finance v7 API direct (legacy fallback)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
import requests
import json
from datetime import datetime, timezone
import pytz
import time
import warnings
warnings.filterwarnings("ignore")

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

# Browser-like headers to avoid Yahoo Finance blocks
_YF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://finance.yahoo.com",
    "Referer": "https://finance.yahoo.com/",
}

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

# yfinance interval + period
TIMEFRAME_MAP = {
    "M1":  ("1m",  "1d"),
    "M5":  ("5m",  "2d"),
    "M15": ("15m", "5d"),
    "H1":  ("1h",  "30d"),
    "H4":  ("1h",  "60d"),
    "D1":  ("1d",  "365d"),
    "W1":  ("1wk", "730d"),
}

# Yahoo Finance v8 API interval codes
_YF_API_INTERVAL = {
    "M1":  "1m",
    "M5":  "5m",
    "M15": "15m",
    "H1":  "60m",
    "H4":  "60m",
    "D1":  "1d",
    "W1":  "1wk",
}

# How many days of data to request via direct API
_YF_API_RANGE = {
    "M1":  "1d",
    "M5":  "5d",
    "M15": "5d",
    "H1":  "30d",
    "H4":  "60d",
    "D1":  "1y",
    "W1":  "2y",
}


# ══════════════════════════════════════════════════════════════
# STRATEGY 1 — DataFrame Cleaner (yfinance output normaliser)
# ══════════════════════════════════════════════════════════════
def _clean_df(raw: pd.DataFrame, timeframe: str = "H1") -> pd.DataFrame:
    """Normalise any yfinance DataFrame regardless of MultiIndex, case, etc."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    df = raw.copy()

    # Flatten MultiIndex (yfinance >= 0.2.38)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]).strip() if isinstance(c, tuple) else str(c).strip()
                      for c in df.columns]

    df.columns = [c.lower().strip() for c in df.columns]
    df = df.rename(columns={"adj close":"close","adj_close":"close","adjclose":"close"})

    needed = ["open","high","low","close"]
    if any(c not in df.columns for c in needed):
        return pd.DataFrame()

    keep = needed + (["volume"] if "volume" in df.columns else [])
    df   = df[keep].copy()
    df   = df.dropna(subset=needed, how="all")
    df   = df[df["close"].notna() & (df["close"] > 0)]

    if df.empty:
        return pd.DataFrame()

    # Resample 1h → 4h
    if timeframe == "H4":
        agg = {"open":"first","high":"max","low":"min","close":"last"}
        if "volume" in df.columns:
            agg["volume"] = "sum"
        try:
            df = df.resample("4h").agg(agg).dropna(subset=["close"])
        except Exception:
            pass

    # Timezone
    try:
        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(COLOMBO_TZ)
    except Exception:
        pass

    for col in keep:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["close"])


# ══════════════════════════════════════════════════════════════
# STRATEGY 2 — Yahoo Finance v8 API Direct
# ══════════════════════════════════════════════════════════════
def _fetch_yf_api(ticker: str, timeframe: str) -> pd.DataFrame:
    """
    Directly call Yahoo Finance v8 chart API with browser headers.
    Works even when yfinance library is rate-limited on shared IPs.
    """
    interval = _YF_API_INTERVAL.get(timeframe, "1h")
    rng      = _YF_API_RANGE.get(timeframe, "30d")

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval={interval}&range={rng}"
        f"&includePrePost=false&events=div%2Csplit"
    )

    try:
        session = requests.Session()
        # First visit Yahoo Finance to get cookies
        session.get("https://finance.yahoo.com", headers=_YF_HEADERS, timeout=5)
        time.sleep(0.3)

        resp = session.get(url, headers=_YF_HEADERS, timeout=10)
        if resp.status_code != 200:
            return pd.DataFrame()

        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return pd.DataFrame()

        r         = result[0]
        ts        = r.get("timestamp", [])
        quote     = r.get("indicators", {}).get("quote", [{}])[0]

        if not ts or not quote.get("close"):
            return pd.DataFrame()

        df = pd.DataFrame({
            "open":   quote.get("open",   [None]*len(ts)),
            "high":   quote.get("high",   [None]*len(ts)),
            "low":    quote.get("low",    [None]*len(ts)),
            "close":  quote.get("close",  [None]*len(ts)),
            "volume": quote.get("volume", [0]*len(ts)),
        }, index=pd.to_datetime(ts, unit="s", utc=True))

        return _clean_df(df, timeframe)

    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# STRATEGY 3 — Yahoo Finance v7 API (Legacy)
# ══════════════════════════════════════════════════════════════
def _fetch_yf_v7(ticker: str, timeframe: str) -> pd.DataFrame:
    """Yahoo Finance v7 download API — legacy fallback."""
    interval = _YF_API_INTERVAL.get(timeframe, "1d")
    rng      = _YF_API_RANGE.get(timeframe, "1y")

    url = (
        f"https://query2.finance.yahoo.com/v7/finance/chart/{ticker}"
        f"?interval={interval}&range={rng}"
    )
    try:
        resp = requests.get(url, headers=_YF_HEADERS, timeout=10)
        if resp.status_code != 200:
            return pd.DataFrame()

        data   = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return pd.DataFrame()

        r     = result[0]
        ts    = r.get("timestamp", [])
        quote = r.get("indicators", {}).get("quote", [{}])[0]

        if not ts:
            return pd.DataFrame()

        df = pd.DataFrame({
            "open":   quote.get("open",   [None]*len(ts)),
            "high":   quote.get("high",   [None]*len(ts)),
            "low":    quote.get("low",    [None]*len(ts)),
            "close":  quote.get("close",  [None]*len(ts)),
            "volume": quote.get("volume", [0]*len(ts)),
        }, index=pd.to_datetime(ts, unit="s", utc=True))

        return _clean_df(df, timeframe)

    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# MAIN OHLCV FETCHER — Tries all 4 strategies
# ══════════════════════════════════════════════════════════════
@st.cache_data(ttl=30, show_spinner=False)   # 30s — near-live for analysis
def get_ohlcv(symbol: str, timeframe: str = "H1",
              period_override: str = None) -> pd.DataFrame:
    """
    Fetch OHLCV with 4 fallback strategies:
    1. yf.download()
    2. yf.Ticker.history()
    3. Yahoo Finance v8 API (direct, with browser headers)
    4. Yahoo Finance v7 API (legacy)
    """
    ticker   = SYMBOL_MAP.get(symbol, symbol)
    interval, default_period = TIMEFRAME_MAP.get(timeframe, ("1h", "30d"))
    period   = period_override or default_period

    # ── Strategy 1: yf.download ──────────────────────────────
    try:
        raw = yf.download(
            ticker, period=period, interval=interval,
            progress=False, auto_adjust=True, threads=False,
        )
        df = _clean_df(raw, timeframe)
        if not df.empty and len(df) >= 10:
            return df
    except Exception:
        pass

    # ── Strategy 2: yf.Ticker.history ────────────────────────
    try:
        raw = yf.Ticker(ticker).history(
            period=period, interval=interval, auto_adjust=True,
        )
        df = _clean_df(raw, timeframe)
        if not df.empty and len(df) >= 10:
            return df
    except Exception:
        pass

    # ── Strategy 3: Yahoo v8 API direct ──────────────────────
    df = _fetch_yf_api(ticker, timeframe)
    if not df.empty and len(df) >= 10:
        return df

    # ── Strategy 4: Yahoo v7 API legacy ──────────────────────
    df = _fetch_yf_v7(ticker, timeframe)
    if not df.empty:
        return df

    return pd.DataFrame()


def inject_live_price(df: pd.DataFrame, symbol: str) -> tuple:
    """
    Update the last candle of df with the current live price.
    Returns (updated_df, live_price, fetch_time_str).
    Last candle close/high/low get updated so EW & SMC use fresh price.
    """
    import pytz
    from datetime import datetime

    if df is None or df.empty:
        return df, None, None

    live  = get_live_price(symbol)
    price = live.get("price")

    if not price:
        return df, None, None

    df = df.copy()
    df.iloc[-1, df.columns.get_loc("close")] = float(price)
    # Update high/low of last candle too
    if float(price) > float(df.iloc[-1]["high"]):
        df.iloc[-1, df.columns.get_loc("high")] = float(price)
    if float(price) < float(df.iloc[-1]["low"]):
        df.iloc[-1, df.columns.get_loc("low")] = float(price)

    now_lkt = datetime.now(pytz.timezone("Asia/Colombo")).strftime("%H:%M:%S LKT")
    return df, float(price), now_lkt


# ══════════════════════════════════════════════════════════════
# LIVE PRICE FETCHER
# ══════════════════════════════════════════════════════════════
@st.cache_data(ttl=15, show_spinner=False)   # 15s live price cache
def get_live_price(symbol: str) -> dict:
    """Get current live price with multiple fallbacks."""
    ticker = SYMBOL_MAP.get(symbol, symbol)
    base   = {"symbol": symbol, "price": None, "change": None,
               "change_pct": None, "volume": None, "high": None, "low": None}

    # Try fast price via v8 API first (most reliable on shared hosting)
    try:
        url  = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        resp = requests.get(url, headers=_YF_HEADERS, timeout=8)
        if resp.status_code == 200:
            data   = resp.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                r      = result[0]
                meta   = r.get("meta", {})
                price  = meta.get("regularMarketPrice") or meta.get("previousClose")
                prev   = meta.get("chartPreviousClose") or meta.get("previousClose", price)
                if price:
                    change = price - prev if prev else 0
                    pct    = (change / prev * 100) if prev else 0
                    return {
                        "symbol":     symbol,
                        "price":      round(float(price), 5),
                        "change":     round(float(change), 5),
                        "change_pct": round(float(pct), 3),
                        "volume":     int(meta.get("regularMarketVolume", 0) or 0),
                        "high":       round(float(meta.get("regularMarketDayHigh", price)), 5),
                        "low":        round(float(meta.get("regularMarketDayLow",  price)), 5),
                    }
    except Exception:
        pass

    # Fallback: yfinance Ticker
    for interval, period in [("5m","2d"), ("1h","5d"), ("1d","30d")]:
        try:
            raw = yf.Ticker(ticker).history(
                period=period, interval=interval, auto_adjust=True
            )
            df = _clean_df(raw)
            if df.empty or len(df) < 2:
                continue
            current = float(df["close"].iloc[-1])
            prev    = float(df["close"].iloc[-2])
            change  = current - prev
            pct     = (change / prev * 100) if prev else 0
            return {
                "symbol":     symbol,
                "price":      round(current, 5),
                "change":     round(change, 5),
                "change_pct": round(pct, 3),
                "volume":     int(df["volume"].iloc[-1]) if "volume" in df.columns else 0,
                "high":       round(float(df["high"].max()), 5),
                "low":        round(float(df["low"].min()), 5),
            }
        except Exception:
            continue

    return base


@st.cache_data(ttl=30, show_spinner=False)
def get_all_live_prices(symbols: list = None) -> list:
    return [get_live_price(s) for s in (symbols or MAJOR_PAIRS)]


# ══════════════════════════════════════════════════════════════
# SESSION STATUS
# ══════════════════════════════════════════════════════════════
def get_session_status() -> dict:
    t = datetime.now(pytz.UTC)
    h = t.hour + t.minute / 60
    sessions = {
        "Sydney":   {"open":22.0,"close":7.0, "color":"#4ECDC4","utc_label":"22:00–07:00 UTC"},
        "Tokyo":    {"open":0.0, "close":9.0, "color":"#45B7D1","utc_label":"00:00–09:00 UTC"},
        "London":   {"open":8.0, "close":17.0,"color":"#FFA07A","utc_label":"08:00–17:00 UTC"},
        "New York": {"open":13.0,"close":22.0,"color":"#98D8C8","utc_label":"13:00–22:00 UTC"},
    }
    result = {}
    for name, info in sessions.items():
        o, c   = info["open"], info["close"]
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

