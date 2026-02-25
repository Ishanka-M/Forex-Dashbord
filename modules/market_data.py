"""
modules/market_data.py
Live Market Data Fetcher using yfinance — 50+ pairs
"""

import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime
import pytz

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

# ── Symbol Map ───────────────────────────────────────────────────────────────
SYMBOL_MAP = {
    # Major Pairs
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X",
    "USDCAD": "USDCAD=X",
    # Cross Pairs
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
    # Exotic Pairs
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
    "M5":  ("5m",  "1d"),
    "M15": ("15m", "5d"),
    "H1":  ("1h",  "30d"),
    "H4":  ("1h",  "60d"),
    "D1":  ("1d",  "365d"),
}


def _empty_price(symbol):
    return {"symbol": symbol, "price": None, "change": None,
            "change_pct": None, "volume": None, "high": None, "low": None}


@st.cache_data(ttl=60)
def get_live_price(symbol: str) -> dict:
    ticker = SYMBOL_MAP.get(symbol, symbol)
    try:
        hist = yf.Ticker(ticker).history(period="2d", interval="5m")
        if hist.empty:
            return _empty_price(symbol)
        current = float(hist["Close"].iloc[-1])
        prev    = float(hist["Close"].iloc[0])
        change  = current - prev
        pct     = (change / prev * 100) if prev else 0
        vol     = int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0
        return {
            "symbol":     symbol,
            "price":      round(current, 5),
            "change":     round(change, 5),
            "change_pct": round(pct, 3),
            "volume":     vol,
            "high":       round(float(hist["High"].max()), 5),
            "low":        round(float(hist["Low"].min()), 5),
        }
    except Exception:
        return _empty_price(symbol)


@st.cache_data(ttl=180)
def get_ohlcv(symbol: str, timeframe: str = "H1", period_override: str = None) -> pd.DataFrame:
    ticker = SYMBOL_MAP.get(symbol, symbol)
    interval, default_period = TIMEFRAME_MAP.get(timeframe, ("1h", "30d"))
    period = period_override or default_period
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]

        df = df.rename(columns={"Open":"open","High":"high","Low":"low",
                                 "Close":"close","Volume":"volume"})
        cols = [c for c in ["open","high","low","close","volume"] if c in df.columns]
        df = df[cols].dropna(subset=["open","close"])

        if timeframe == "H4":
            agg = {"open":"first","high":"max","low":"min","close":"last"}
            if "volume" in df.columns:
                agg["volume"] = "sum"
            df = df.resample("4h").agg(agg).dropna(subset=["open","close"])

        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(COLOMBO_TZ)
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30)
def get_all_live_prices(symbols: list = None) -> list:
    return [get_live_price(s) for s in (symbols or MAJOR_PAIRS)]


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
