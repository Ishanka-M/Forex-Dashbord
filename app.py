import streamlit as st
import yfinance as yf
import pandas as pd
import puter  # Puter AI for Fallback
import google.generativeai as genai  # Gemini AI
import groq  # Groq AI
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import re
import numpy as np
import requests
import xml.etree.ElementTree as ET
import pytz  # For Timezone handling

# ==================== UNIFIED RATE LIMITER (50 req/min total) ====================
import threading

class UnifiedRateLimiter:
    """
    Single shared token bucket that enforces a COMBINED 50 requests/minute
    across ALL external APIs (Google Sheets + yfinance).

    Design:
    - One global queue of timestamps (thread-safe via Lock)
    - Sliding 60-second window
    - Hard cap: 50 calls per window
    - Per-source soft caps prevent one source starving the other:
        • Google Sheets: max 28 per window  (≈56% of 50)
        • yfinance      : max 22 per window  (≈44% of 50)
    - Exponential back-off on repeated consecutive waits
    - Non-blocking dry-run mode for quota checks
    """
    WINDOW       = 60.0   # seconds
    TOTAL_CAP    = 50     # hard cap — combined across all sources
    GS_CAP       = 28     # soft cap — Google Sheets
    YF_CAP       = 22     # soft cap — yfinance
    MIN_INTERVAL = 0.25   # minimum gap between any two calls (250 ms) → smoothing

    def __init__(self):
        self._lock       = threading.Lock()
        self._timestamps = []           # (epoch_float, source_str)
        self._last_call  = 0.0          # epoch of last call (any source)
        self._wait_streak = 0           # consecutive waits counter (for back-off)

    # ── internal helpers ────────────────────────────────────────────────
    def _prune(self, now):
        cutoff = now - self.WINDOW
        self._timestamps = [(t, s) for (t, s) in self._timestamps if t > cutoff]

    def _count(self, source=None):
        if source is None:
            return len(self._timestamps)
        return sum(1 for (_, s) in self._timestamps if s == source)

    # ── public interface ─────────────────────────────────────────────────
    def wait_if_needed(self, source: str = "gs"):
        """
        Block until it is safe to make one API call of the given source.
        source: "gs"  (Google Sheets)  or  "yf"  (yfinance)
        """
        per_source_cap = self.GS_CAP if source == "gs" else self.YF_CAP

        while True:
            with self._lock:
                now = time.time()
                self._prune(now)

                total_used      = self._count()
                source_used     = self._count(source)
                time_since_last = now - self._last_call

                # All caps satisfied AND minimum spacing met?
                if (total_used  < self.TOTAL_CAP and
                        source_used < per_source_cap and
                        time_since_last >= self.MIN_INTERVAL):
                    # Approved — record the call
                    self._timestamps.append((now, source))
                    self._last_call  = now
                    self._wait_streak = 0
                    return  # ← caller can proceed immediately

                # Need to wait — calculate how long
                wait_for = 0.0

                # Hard total cap hit?
                if total_used >= self.TOTAL_CAP:
                    oldest_any = self._timestamps[0][0]
                    wait_for = max(wait_for, self.WINDOW - (now - oldest_any) + 0.05)

                # Source soft cap hit?
                if source_used >= per_source_cap:
                    src_times = sorted(t for (t, s) in self._timestamps if s == source)
                    if src_times:
                        wait_for = max(wait_for, self.WINDOW - (now - src_times[0]) + 0.05)

                # Minimum spacing?
                if time_since_last < self.MIN_INTERVAL:
                    wait_for = max(wait_for, self.MIN_INTERVAL - time_since_last + 0.01)

                # Exponential back-off guard (max 2 s extra)
                self._wait_streak += 1
                back_off = min(0.1 * (2 ** min(self._wait_streak, 4)), 2.0)
                wait_for = max(wait_for, back_off)

            # Sleep OUTSIDE the lock so other threads can progress
            time.sleep(max(0.05, wait_for))

    def can_call(self, source: str = "gs") -> bool:
        """Non-blocking check — returns True if a call would be allowed right now."""
        per_source_cap = self.GS_CAP if source == "gs" else self.YF_CAP
        with self._lock:
            now = time.time()
            self._prune(now)
            return (self._count() < self.TOTAL_CAP and
                    self._count(source) < per_source_cap and
                    now - self._last_call >= self.MIN_INTERVAL)

    def usage_stats(self) -> dict:
        """Return current window usage — for Admin Panel display."""
        with self._lock:
            now = time.time()
            self._prune(now)
            return {
                "total_used"    : self._count(),
                "total_cap"     : self.TOTAL_CAP,
                "gs_used"       : self._count("gs"),
                "gs_cap"        : self.GS_CAP,
                "yf_used"       : self._count("yf"),
                "yf_cap"        : self.YF_CAP,
                "window_sec"    : self.WINDOW,
                "pct_used"      : round(self._count() / self.TOTAL_CAP * 100, 1),
            }


# ── Singleton — lives for the entire Streamlit session ────────────────────────
_api_limiter = UnifiedRateLimiter()

# Back-compat aliases so the rest of the code can call the old names
class _BackCompatLimiter:
    """Thin wrapper that forwards to the unified limiter with the correct source tag."""
    def __init__(self, source):
        self._source = source
    def wait_if_needed(self):
        _api_limiter.wait_if_needed(self._source)

_gsheets_limiter = _BackCompatLimiter("gs")
_yfinance_limiter = _BackCompatLimiter("yf")

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite Algo Terminal v32.0 (50 req/min | EW+ICT+SMC+Fib)", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes pulse-green { 0% { box-shadow: 0 0 0 0 rgba(0, 255, 0, 0.7); } 70% { box-shadow: 0 0 15px 15px rgba(0, 255, 0, 0); } 100% { box-shadow: 0 0 0 0 rgba(0, 255, 0, 0); } }
    @keyframes pulse-red { 0% { box-shadow: 0 0 0 0 rgba(255, 75, 75, 0.7); } 70% { box-shadow: 0 0 15px 15px rgba(255, 75, 75, 0); } 100% { box-shadow: 0 0 0 0 rgba(255, 75, 75, 0); } }
    @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    @keyframes shimmer { 0% { background-position: -1000px 0; } 100% { background-position: 1000px 0; } }
    @keyframes float { 0% { transform: translateY(0px); } 50% { transform: translateY(-5px); } 100% { transform: translateY(0px); } }
    @keyframes glow { 0% { box-shadow: 0 0 5px #00ff99; } 50% { box-shadow: 0 0 20px #00ff99; } 100% { box-shadow: 0 0 5px #00ff99; } }
    .loading-icon { display: inline-block; animation: rotate 2s linear infinite; font-size: 24px; }
    .stApp { animation: fadeIn 0.8s ease-out forwards; }
    .high-prob-alert { background: linear-gradient(135deg, #1a1a1a, #2d2d2d); border: 2px solid #00ff99; border-radius: 15px; padding: 20px; margin-bottom: 20px; text-align: center; animation: glow 2s infinite; }
    .price-up { color: #00ff00; font-size: 26px; font-weight: 800; text-shadow: 0 0 10px rgba(0, 255, 0, 0.5); }
    .price-down { color: #ff4b4b; font-size: 26px; font-weight: 800; text-shadow: 0 0 10px rgba(255, 75, 75, 0.5); }
    .entry-box { background: rgba(0, 255, 153, 0.1); border: 2px solid #00ff99; padding: 20px; border-radius: 15px; margin-top: 15px; color: white; backdrop-filter: blur(10px); box-shadow: 0 0 20px rgba(0, 255, 153, 0.2); transition: transform 0.3s, box-shadow 0.3s; animation: float 4s ease-in-out infinite; }
    .entry-box:hover { transform: scale(1.02); box-shadow: 0 0 30px rgba(0, 255, 153, 0.5); }
    .trade-metric { background: linear-gradient(145deg, #1e1e1e, #2a2a2a); border: 1px solid #444; border-radius: 12px; padding: 15px; text-align: center; transition: all 0.3s ease; }
    .trade-metric:hover { transform: translateY(-5px) scale(1.02); box-shadow: 0 10px 20px rgba(0,0,0,0.5); border-color: #00ff99; }
    .trade-metric h4 { margin: 0; color: #aaa; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }
    .trade-metric h2 { margin: 5px 0 0 0; color: #fff; font-size: 22px; font-weight: bold; }
    .news-card { background: #1e1e1e; padding: 12px; margin-bottom: 10px; border-radius: 8px; transition: all 0.3s ease; border-right: 1px solid #333; animation: fadeIn 0.5s; position: relative; }
    .news-card:hover { transform: translateX(5px); background: #252525; box-shadow: -5px 0 10px rgba(0,0,0,0.3); }
    .news-positive { border-left: 5px solid #00ff00; }
    .news-negative { border-left: 5px solid #ff4b4b; }
    .news-neutral { border-left: 5px solid #00ff99; }
    .news-time { font-size: 10px; color: #888; position: absolute; bottom: 2px; right: 8px; }
    .sig-box { padding: 12px; border-radius: 8px; font-size: 13px; text-align: center; font-weight: bold; border: 1px solid #444; margin-bottom: 8px; box-shadow: inset 0 0 10px rgba(0,0,0,0.2); transition: all 0.3s; animation: fadeIn 0.6s; }
    .sig-box:hover { transform: scale(1.02); box-shadow: 0 0 15px currentColor; }
    .bull { background: linear-gradient(90deg, #004d40, #00695c); color: #00ff00; border-color: #00ff00; }
    .bear { background: linear-gradient(90deg, #4a1414, #7f0000); color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background: #262626; color: #888; }
    .notif-container { padding: 20px; border-radius: 12px; margin-bottom: 25px; border-left: 8px solid; background: #121212; font-size: 18px; animation: fadeIn 0.8s; }
    .notif-buy { border-color: #00ff00; color: #00ff00; animation: pulse-green 2s infinite; }
    .notif-sell { border-color: #ff4b4b; color: #ff4b4b; animation: pulse-red 2s infinite; }
    .notif-wait { border-color: #555; color: #aaa; }
    .confirm-card { background: #1e1e1e; border-left: 5px solid; border-radius: 8px; padding: 10px 15px; margin: 10px 0; font-size: 14px; display: flex; align-items: center; gap: 10px; }
    .confirm-approve { border-color: #00ff00; }
    .confirm-reject { border-color: #ff4b4b; }
    .confirm-icon { font-size: 20px; }
    .admin-table { font-size: 14px; width: 100%; border-collapse: collapse; }
    .admin-table th, .admin-table td { border: 1px solid #444; padding: 8px; text-align: left; }
    .admin-table th { background-color: #333; color: #00ff99; }
    .forecast-loading { text-align: center; padding: 20px; background: #1e1e1e; border-radius: 10px; border: 1px solid #00ff99; margin: 10px 0; animation: glow 1.5s infinite; }
    .forecast-loading span { font-size: 20px; color: #00ff99; }
    .scan-card { animation: slideInUp 0.5s ease-out; }
    @keyframes slideInUp { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
    .stButton>button { border-radius: 8px; font-weight: 600; transition: all 0.2s; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 5px 10px rgba(0,255,153,0.3); }
    .scan-header { background: linear-gradient(90deg, #1e3c3f, #0a1f2e); padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 5px solid #00ff99; }
    .main-title { text-align: center; background: linear-gradient(135deg, #0a1f2e, #1e3c3f); padding: 20px; border-radius: 15px; margin-bottom: 25px; border: 1px solid #00ff99; box-shadow: 0 0 30px rgba(0,255,153,0.2); }
    .main-title h1 { color: #00ff99; font-weight: 700; letter-spacing: 2px; margin: 0; }
    .main-title p { color: #ccc; margin: 5px 0 0; }
    .footer { text-align: center; margin-top: 40px; padding: 15px; background: #0e0e0e; border-radius: 10px; font-size: 12px; color: #666; border-top: 1px solid #333; }
    .stSlider label { color: #00ff99 !important; font-weight: 600; }
    .stSelectbox label { color: #00ff99 !important; font-weight: 600; }
    .stRadio label { color: #00ff99 !important; }
    .stCheckbox label { color: #00ff99 !important; }
    hr { border-color: #333; }
    .session-card { background: #0e0e0e; border: 1px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 15px; font-size: 13px; border-left: 3px solid #00ff99; }
    .session-card span { color: #00ff99; font-weight: 600; }
    .ai-badge { display: inline-block; padding: 4px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; margin-left: 8px; }
    .ai-approve { background-color: #00ff0022; color: #00ff00; border: 1px solid #00ff00; }
    .ai-reject { background-color: #ff4b4b22; color: #ff4b4b; border: 1px solid #ff4b4b; }
    .dashboard-card { background: linear-gradient(145deg, #1e1e1e, #2a2a2a); border-radius: 15px; padding: 20px; margin-bottom: 20px; border: 1px solid #444; box-shadow: 0 10px 20px rgba(0,0,0,0.5); transition: all 0.3s ease; }
    .dashboard-card:hover { transform: translateY(-5px); border-color: #00ff99; box-shadow: 0 15px 30px rgba(0,255,153,0.2); }
    .dashboard-card h3 { color: #00ff99; margin-top: 0; border-bottom: 1px solid #333; padding-bottom: 10px; }
    .metric-value { font-size: 24px; font-weight: bold; color: #fff; }
    .metric-label { color: #aaa; font-size: 14px; }
    .live-price-table { width: 100%; border-collapse: collapse; }
    .live-price-table th { background-color: #333; color: #00ff99; padding: 8px; text-align: left; }
    .live-price-table td { padding: 8px; border-bottom: 1px solid #444; }
    .system-engine-card { background: linear-gradient(145deg, #0a1f2e, #1e3c3f); border: 2px solid #00ff99; border-radius: 20px; padding: 25px; margin-bottom: 20px; text-align: center; box-shadow: 0 0 30px rgba(0,255,153,0.3); animation: glow 2s infinite; }
    .system-engine-card h2 { color: #00ff99; margin-bottom: 15px; font-weight: 700; letter-spacing: 2px; }
    .engine-icon { font-size: 60px; animation: rotate 3s linear infinite; display: inline-block; margin-bottom: 15px; color: #00ff99; }
    .engine-text { color: white; font-size: 20px; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 10px; border: 1px solid #00ff99; backdrop-filter: blur(5px); }
    body { font-family: 'Noto Sans Sinhala', 'Iskoola Pota', 'Arial Unicode MS', sans-serif; }
    .theory-badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 4px; }
    .theory-bull { background: #004d40; color: #00ff00; border: 1px solid #00ff00; }
    .theory-bear { background: #4a1414; color: #ff4b4b; border: 1px solid #ff4b4b; }
    .theory-neutral { background: #333; color: #ccc; border: 1px solid #666; }
    .mtf-box { background: linear-gradient(135deg, #0a1f2e, #1a2a3a); border: 1px solid #00ff99; border-radius: 10px; padding: 12px; margin: 8px 0; font-size: 13px; }
    .mtf-bull { border-left: 4px solid #00ff00; }
    .mtf-bear { border-left: 4px solid #ff4b4b; }
    .mtf-neutral { border-left: 4px solid #888; }
    .score-box { background: #0e0e0e; border: 2px solid #00ff99; border-radius: 12px; padding: 15px; text-align: center; margin: 10px 0; }
    .score-high { border-color: #00ff00; }
    .score-medium { border-color: #ffaa00; }
    .score-low { border-color: #ff4b4b; }
    /* NEW: Rejected trade card */
    .rejected-card { background: #1a0a0a; border: 1px solid #ff4b4b44; border-left: 5px solid #ff4b4b; border-radius: 8px; padding: 10px 15px; margin-bottom: 8px; font-size: 13px; opacity: 0.75; }
    .rejected-card:hover { opacity: 1; }
    .rejected-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold; background: #ff4b4b22; color: #ff4b4b; border: 1px solid #ff4b4b; margin-left: 6px; }
    .gate-fail-badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; background: #33000a; color: #ff8888; border: 1px solid #ff4b4b66; margin-right: 4px; }
    /* Risk Badges */
    .risk-badge-safe { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; background: #003300; color: #00ff00; border: 1px solid #00ff00; margin-left: 6px; }
    .risk-badge-danger { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; background: #330000; color: #ff4444; border: 1px solid #ff4444; margin-left: 6px; }
    .risk-badge-moderate { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; background: #332200; color: #ffaa00; border: 1px solid #ffaa00; margin-left: 6px; }
    .entry-zone-badge { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: bold; background: #003344; color: #00ccff; border: 1px solid #00ccff; margin-left: 4px; }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "active_provider" not in st.session_state: st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A", "FORECAST": "N/A"}
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "rejected_trades" not in st.session_state: st.session_state.rejected_trades = []  # NEW: store rejected trades
if "forecast_chart" not in st.session_state: st.session_state.forecast_chart = None
if "selected_trade" not in st.session_state: st.session_state.selected_trade = None
if "deep_analysis_result" not in st.session_state: st.session_state.deep_analysis_result = None
if "deep_analysis_provider" not in st.session_state: st.session_state.deep_analysis_provider = None
if "deep_forecast_chart" not in st.session_state: st.session_state.deep_forecast_chart = None
if "selected_market" not in st.session_state: st.session_state.selected_market = "All"
if "min_accuracy" not in st.session_state: st.session_state.min_accuracy = 40
if "last_activity" not in st.session_state: st.session_state.last_activity = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
if "login_time" not in st.session_state: st.session_state.login_time = None
if "ai_confirmations" not in st.session_state: st.session_state.ai_confirmations = {}
if "tracked_trades" not in st.session_state: st.session_state.tracked_trades = set()
if "dashboard_forecast" not in st.session_state: st.session_state.dashboard_forecast = None
if "dashboard_forecast_provider" not in st.session_state: st.session_state.dashboard_forecast_provider = None
if "news_impact_analysis" not in st.session_state: st.session_state.news_impact_analysis = None
if "news_impact_provider" not in st.session_state: st.session_state.news_impact_provider = None
if "tech_chart" not in st.session_state: st.session_state.tech_chart = None
if "theory_chart" not in st.session_state: st.session_state.theory_chart = None
if "total_api_requests" not in st.session_state: st.session_state.total_api_requests = 0
if "historical_data_cache" not in st.session_state: st.session_state.historical_data_cache = {}
if "beginner_mode" not in st.session_state: st.session_state.beginner_mode = False
if "backtest_results" not in st.session_state: st.session_state.backtest_results = None
if "price_cache" not in st.session_state: st.session_state.price_cache = {}

# ==================== HELPER FUNCTIONS ====================

def get_yf_symbol(display_symbol):
    if display_symbol.endswith("-USDT"):
        return display_symbol.replace("-USDT", "-USD")
    if display_symbol in ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]:
        return display_symbol + "=X"
    return display_symbol

def clean_pair_to_yf_symbol(clean_pair):
    if clean_pair in ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]:
        return clean_pair + "=X"
    if clean_pair.endswith("USDT"):
        base = clean_pair[:-4]
        return base + "-USD"
    return clean_pair + "=X"

def get_live_price(clean_pair):
    current_time = time.time()
    cache_duration = 60
    if clean_pair in st.session_state.price_cache:
        price, timestamp = st.session_state.price_cache[clean_pair]
        if current_time - timestamp < cache_duration and price is not None:
            return price
    yf_sym = clean_pair_to_yf_symbol(clean_pair)
    price = None
    try:
        _yfinance_limiter.wait_if_needed()
        ticker = yf.Ticker(yf_sym)
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
        else:
            if hasattr(ticker, 'fast_info') and ticker.fast_info:
                try:
                    price = ticker.fast_info['lastPrice']
                except:
                    pass
            if price is None:
                info = ticker.info
                price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('ask')
        if price is not None:
            st.session_state.price_cache[clean_pair] = (price, current_time)
            return price
        return None
    except Exception as e:
        print(f"Error fetching price for {clean_pair}: {e}")
        return None

def get_cached_historical_data(symbol, interval, period=None, start=None, end=None):
    """
    Smart historical data fetcher with Google Sheets persistent cache.

    Strategy:
    1. Check in-memory session cache (fastest, expires by TF)
    2. Check Google Sheets persistent cache (survives restarts)
    3. If cache exists → only fetch NEW candles since last saved timestamp
    4. If no cache → full download, save to Sheets
    5. Merge old + new data, return complete DataFrame

    All API calls routed through _api_limiter (50 req/min combined).
    """
    if period:
        key = f"{symbol}_{interval}_{period}"
    else:
        key = f"{symbol}_{interval}_{start}_{end}"

    current_time = time.time()

    # --- Memory cache expiry per timeframe ---
    mem_cache_ttl = {
        "1m": 60, "5m": 300, "15m": 600,
        "1h": 1800, "4h": 3600, "1d": 7200, "1wk": 14400
    }
    ttl = mem_cache_ttl.get(interval, 3600)

    # --- 1. Check in-memory cache ---
    cache_entry = st.session_state.historical_data_cache.get(key)
    if cache_entry:
        df, timestamp = cache_entry
        if current_time - timestamp < ttl:
            return df

    # --- 2. Try Google Sheets persistent cache ---
    gs_df = load_history_from_sheets(symbol, interval)

    if gs_df is not None and len(gs_df) >= 50:
        # Cache hit: only download new candles since last timestamp
        last_ts = gs_df.index[-1]
        try:
            # Convert to timezone-naive for comparison
            if hasattr(last_ts, 'tzinfo') and last_ts.tzinfo is not None:
                last_ts_naive = last_ts.tz_convert(None)
            else:
                last_ts_naive = last_ts

            # Download only recent data (incremental update)
            # Periods must match get_period_for_tf to avoid missing candles
            incremental_period = {
                "1m": "5d", "5m": "1mo",
                "15m": "3mo", "1h": "6mo",
                "4h": "1y", "1d": "2y", "1wk": "5y"
            }.get(interval, "1mo")
            _api_limiter.wait_if_needed("yf")
            new_df = yf.download(symbol, period=incremental_period, interval=interval, progress=False)

            if new_df is not None and not new_df.empty:
                if isinstance(new_df.columns, pd.MultiIndex):
                    new_df.columns = new_df.columns.get_level_values(0)

                # Timezone normalize new_df index
                if hasattr(new_df.index, 'tz') and new_df.index.tz is not None:
                    new_df.index = new_df.index.tz_convert(None)

                # Timezone normalize gs_df index
                if hasattr(gs_df.index, 'tz') and gs_df.index.tz is not None:
                    gs_df.index = gs_df.index.tz_convert(None)

                # Find truly new rows (after last saved timestamp)
                new_rows = new_df[new_df.index > last_ts_naive]

                if len(new_rows) > 0:
                    # Merge: old saved data + new rows
                    merged = pd.concat([gs_df, new_rows])
                    merged = merged[~merged.index.duplicated(keep='last')]
                    merged = merged.sort_index()

                    # Save updated data back to Sheets (only new rows)
                    save_history_to_sheets(symbol, interval, new_rows)
                else:
                    merged = gs_df
            else:
                merged = gs_df

            # Store in memory cache
            st.session_state.historical_data_cache[key] = (merged, current_time)
            return merged

        except Exception as e:
            print(f"Incremental update error for {symbol}/{interval}: {e}")
            # Fall through to full download

    # --- 3. Full download (no cache or cache failed) ---
    try:
        _api_limiter.wait_if_needed("yf")
        if period:
            df = yf.download(symbol, period=period, interval=interval, progress=False)
        else:
            df = yf.download(symbol, start=start, end=end, interval=interval, progress=False)

        if df is None or df.empty or len(df) < 10:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Normalize timezone
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_convert(None)

        # Save full history to Google Sheets
        save_history_to_sheets(symbol, interval, df)

        # Store in memory cache
        st.session_state.historical_data_cache[key] = (df, current_time)
        return df

    except Exception as e:
        print(f"Error downloading {symbol} {interval}: {e}")
        return None


# ==================== GOOGLE SHEETS CLIENT CACHE ====================
# Reuse a single authorized gspread client per Streamlit session.
# Opening a new OAuth connection on every call wastes ~1 API request + latency.

def _get_gspread_client():
    """
    Return a cached gspread client + spreadsheet handle.
    The client is stored in st.session_state so it survives reruns
    but is re-created if the token expires (>60 min).
    """
    now = time.time()
    cached = st.session_state.get("_gs_client_cache")
    if cached and now - cached["created_at"] < 3000:   # 50-min lifetime
        return cached["client"], cached["spreadsheet"]

    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds        = Credentials.from_service_account_info(
                           st.secrets["gcp_service_account"], scopes=scope)
        client       = gspread.authorize(creds)
        spreadsheet  = client.open("Forex_User_DB")
        st.session_state["_gs_client_cache"] = {
            "client"       : client,
            "spreadsheet"  : spreadsheet,
            "created_at"   : now,
        }
        return client, spreadsheet
    except Exception as e:
        print(f"gspread client error: {e}")
        return None, None


def _get_spreadsheet():
    """Shortcut — returns just the spreadsheet handle."""
    _, ss = _get_gspread_client()
    return ss


# ── Worksheet handle cache ─────────────────────────────────────────────────────
# Avoid repeated worksheet-lookup calls (each one costs an API request).

def _get_ws_cache():
    if "_gs_ws_cache" not in st.session_state:
        st.session_state["_gs_ws_cache"] = {}
    return st.session_state["_gs_ws_cache"]


def _tf_sheet_name(symbol: str, interval: str) -> str:
    """
    Canonical worksheet name for a (symbol, interval) pair.
    Format: H_{SYMBOL}_{INTERVAL}   e.g.  H_EURUSD_4h
    Sanitized and capped at 50 chars (Sheets tab-name limit).
    """
    safe = (symbol.replace("=X","").replace("-","").replace("/","")
                  .replace(".","").replace(" ","").upper()[:20])
    return f"H_{safe}_{interval}"[:50]


# ==================== GOOGLE SHEETS HISTORY CACHE ====================

def get_history_sheet(symbol: str, interval: str):
    """
    Return (or lazily create) the worksheet for this (symbol, interval).
    Uses a session-level worksheet cache so we pay the lookup cost only once.
    One API call used: worksheet lookup or creation.

    Sheet layout per timeframe:
        Col A: Timestamp | B: Open | C: High | D: Low | E: Close | F: Volume | G: SavedAt
    Header row is always row 1.
    """
    sheet_name = _tf_sheet_name(symbol, interval)
    ws_cache   = _get_ws_cache()

    if sheet_name in ws_cache:
        return ws_cache[sheet_name]

    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return None

    try:
        _api_limiter.wait_if_needed("gs")
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        try:
            _api_limiter.wait_if_needed("gs")
            ws = spreadsheet.add_worksheet(
                title=sheet_name,
                rows=6000,
                cols=7,
            )
            _api_limiter.wait_if_needed("gs")
            ws.update("A1:G1", [["Timestamp","Open","High","Low","Close","Volume","SavedAt"]])
        except Exception as e:
            print(f"Cannot create sheet {sheet_name}: {e}")
            return None
    except Exception as e:
        print(f"get_history_sheet error ({symbol}/{interval}): {e}")
        return None

    ws_cache[sheet_name] = ws
    return ws


def save_history_to_sheets(symbol: str, interval: str, df) -> bool:
    """
    Persist OHLCV data to the per-timeframe Google Sheet.

    Strategy — write-mode:
    • If the sheet already has data: APPEND only rows newer than the last
      saved timestamp (incremental / delta write).
    • If the sheet is empty: batch-write the full df (up to max_rows limit).

    Deduplication: we track the last known timestamp in session state so
    we never append a row twice even if this function is called repeatedly.

    API cost: 2 calls for incremental (read last row + append batch)
              2 calls for full write  (clear + append batch)
    """
    if df is None or df.empty:
        return False

    ws = get_history_sheet(symbol, interval)
    if ws is None:
        return False

    # Rows-per-timeframe limit (keeps sheets from blowing up)
    max_rows_map = {
        "1m":  700,  "5m": 1000, "15m": 1500,
        "1h": 1500, "4h": 1200,  "1d": 1000, "1wk": 600,
    }
    limit    = max_rows_map.get(interval, 1000)
    save_df  = df.tail(limit).copy()

    # Normalize index to timezone-naive
    if hasattr(save_df.index, 'tz') and save_df.index.tz is not None:
        save_df.index = save_df.index.tz_convert(None)

    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Determine which rows are truly new ────────────────────────────────
    last_ts_key = f"_gs_last_ts_{_tf_sheet_name(symbol, interval)}"
    last_saved  = st.session_state.get(last_ts_key)

    if last_saved is None:
        # Try to read last data row from sheet to find last timestamp.
        # NOTE: ws.row_count returns ALLOCATED rows (6000), not actual data rows.
        # We must find the last non-empty row using get_all_values.
        try:
            _api_limiter.wait_if_needed("gs")
            all_vals = ws.get_all_values()
            # Find last non-empty row (skip header row 0)
            last_row = None
            for row in reversed(all_vals[1:]):
                if row and row[0] not in ("", "Timestamp"):
                    last_row = row
                    break
            if last_row:
                last_saved = pd.to_datetime(last_row[0])
                st.session_state[last_ts_key] = last_saved
        except Exception:
            last_saved = None

    if last_saved is not None:
        try:
            last_saved_naive = (last_saved.tz_convert(None)
                                if hasattr(last_saved, 'tzinfo') and last_saved.tzinfo
                                else last_saved)
            new_rows_df = save_df[save_df.index > last_saved_naive]
        except Exception:
            new_rows_df = save_df
    else:
        new_rows_df = save_df   # first-time full write

    if new_rows_df.empty:
        return True   # nothing new to write

    # ── Build rows list ───────────────────────────────────────────────────
    rows_to_append = []
    for ts, row in new_rows_df.iterrows():
        try:
            ts_str = str(ts)[:19]
            o  = round(float(row.get('Open',  0)), 8)
            h  = round(float(row.get('High',  0)), 8)
            lo = round(float(row.get('Low',   0)), 8)
            c  = round(float(row.get('Close', 0)), 8)
            v  = int(float(row.get('Volume', 0))) if 'Volume' in row else 0
            rows_to_append.append([ts_str, o, h, lo, c, v, saved_at])
        except Exception:
            continue

    if not rows_to_append:
        return True

    # ── Batch-append in one API call ─────────────────────────────────────
    # Split into chunks of 500 to stay within Sheets payload limits
    CHUNK = 500
    try:
        for i in range(0, len(rows_to_append), CHUNK):
            chunk = rows_to_append[i : i + CHUNK]
            _api_limiter.wait_if_needed("gs")
            ws.append_rows(chunk, value_input_option='RAW')

        # Update session-state last-saved pointer
        last_new_ts = new_rows_df.index[-1]
        if hasattr(last_new_ts, 'tzinfo') and last_new_ts.tzinfo is not None:
            last_new_ts = last_new_ts.tz_convert(None)
        st.session_state[last_ts_key] = last_new_ts
        return True

    except Exception as e:
        print(f"save_history_to_sheets error ({symbol}/{interval}): {e}")
        return False


def load_history_from_sheets(symbol: str, interval: str):
    """
    Load OHLCV history from the per-timeframe Google Sheet.

    Optimisations vs v30/v31:
    • Uses cached worksheet handle (no repeated open() calls)
    • get_all_values() fetched in ONE API call
    • Skips parsing if row count is too small (saves CPU)
    • Stores loaded df in session state keyed by sheet name so
      subsequent calls within the same rerun return instantly

    Returns DataFrame with DatetimeIndex, or None.
    """
    sheet_name = _tf_sheet_name(symbol, interval)
    # Fast in-session cache (avoids a Sheets read if already loaded this rerun)
    mem_key = f"_gs_loaded_{sheet_name}"
    cached  = st.session_state.get(mem_key)
    if cached is not None and isinstance(cached, tuple):
        df_cached, loaded_at = cached
        # Use mem cache for up to 90 seconds (avoids thundering-herd on first scan)
        if time.time() - loaded_at < 90:
            return df_cached

    ws = get_history_sheet(symbol, interval)
    if ws is None:
        return None

    try:
        _api_limiter.wait_if_needed("gs")
        all_rows = ws.get_all_values()
    except Exception as e:
        print(f"load_history_from_sheets read error ({symbol}/{interval}): {e}")
        return None

    if len(all_rows) < 3:      # header + at least 2 data rows
        st.session_state[mem_key] = (None, time.time())
        return None

    data_rows = all_rows[1:]   # skip header
    records   = []
    for row in data_rows:
        try:
            if len(row) < 5 or row[0] in ("", "Timestamp"):
                continue
            ts = pd.to_datetime(row[0])
            o  = float(row[1]); h  = float(row[2])
            lo = float(row[3]); c  = float(row[4])
            v  = float(row[5]) if len(row) > 5 and row[5] else 0
            records.append({"Timestamp": ts, "Open": o, "High": h,
                             "Low": lo, "Close": c, "Volume": v})
        except Exception:
            continue

    if len(records) < 10:
        st.session_state[mem_key] = (None, time.time())
        return None

    df = pd.DataFrame(records).set_index("Timestamp")
    df = df[~df.index.duplicated(keep='last')].sort_index()

    if hasattr(df.index, 'tz') and df.index.tz is not None:
        df.index = df.index.tz_convert(None)

    st.session_state[mem_key] = (df, time.time())
    return df


def clear_history_cache_for_symbol(symbol: str, interval=None) -> list:
    """
    Admin utility: wipe history sheets for a symbol (all TFs or one TF).
    Returns list of sheet names that were cleared.
    """
    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return []

    tfs      = [interval] if interval else ["1m","5m","15m","1h","4h","1d","1wk"]
    cleared  = []
    ws_cache = _get_ws_cache()

    for tf in tfs:
        sheet_name = _tf_sheet_name(symbol, tf)
        try:
            _api_limiter.wait_if_needed("gs")
            ws = spreadsheet.worksheet(sheet_name)
            # Keep header row, delete all data rows by resizing
            _api_limiter.wait_if_needed("gs")
            ws.resize(rows=1)
            _api_limiter.wait_if_needed("gs")
            ws.resize(rows=6000)
            cleared.append(sheet_name)
            # Evict caches
            if sheet_name in ws_cache:
                del ws_cache[sheet_name]
            for k in list(st.session_state.keys()):
                if sheet_name in str(k):
                    del st.session_state[k]
        except gspread.WorksheetNotFound:
            pass
        except Exception as e:
            print(f"clear_history error ({sheet_name}): {e}")

    # Also clear in-memory historical data cache
    sym_clean = symbol.replace("=X","").replace("-","").upper()
    for k in list(st.session_state.historical_data_cache.keys()):
        if sym_clean in k.upper():
            del st.session_state.historical_data_cache[k]

    return cleared


def get_history_cache_stats() -> list:
    """
    Admin display: returns stats about all H_* worksheets.
    Single API call via spreadsheet.worksheets().
    """
    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return []
    try:
        _api_limiter.wait_if_needed("gs")
        worksheets = spreadsheet.worksheets()
    except Exception:
        return []

    stats = []
    for ws in worksheets:
        if not ws.title.startswith("H_"):
            continue
        parts  = ws.title.split("_")
        sym    = parts[1] if len(parts) > 1 else "?"
        tf     = parts[2] if len(parts) > 2 else "?"
        try:
            _api_limiter.wait_if_needed("gs")
            all_vals = ws.get_all_values()
            # Count real data rows (exclude header)
            data_rows = [r for r in all_vals[1:] if r and r[0] not in ("", "Timestamp")]
            rows   = len(data_rows)
            last_ts = data_rows[-1][0] if data_rows else "N/A"
        except Exception:
            rows   = 0
            last_ts = "N/A"
        stats.append({"Symbol": sym, "TF": tf, "Rows": rows, "Last Update": last_ts})
    return stats

def get_period_for_tf(tf):
    # Extended periods for better Elliott Wave + ICT structure identification
    period_map = {
        "1m":  "5d",   # 1d -> 5d  (~1950 candles, enough for intraday wave structure)
        "5m":  "1mo",  # 5d -> 1mo (~2600 candles, multi-day swing structure)
        "15m": "3mo",  # 1mo-> 3mo (~3900 candles, clear wave cycles)
        "1h":  "6mo",  # 3mo-> 6mo (~1080 candles, weekly structure visible)
        "4h":  "1y",   # 6mo-> 1y  (~540 candles, multi-month waves)
        "1d":  "2y",   # 1y -> 2y  (~500 candles, full bull/bear cycles)
        "1wk": "5y"    # already optimal (~260 candles)
    }
    return period_map.get(tf, "3mo")

# --- Google Sheets Functions (use cached client) ---
def get_user_sheet():
    try:
        _, spreadsheet = _get_gspread_client()
        if spreadsheet is None:
            return None, None
        _api_limiter.wait_if_needed("gs")
        sheet = spreadsheet.sheet1
        _, client = _get_gspread_client()
        return sheet, client
    except Exception as e:
        print(f"get_user_sheet error: {e}")
        return None, None

def get_ongoing_sheet():
    try:
        client, spreadsheet = _get_gspread_client()
        if spreadsheet is None:
            return None, None
        try:
            _api_limiter.wait_if_needed("gs")
            sheet = spreadsheet.worksheet("Ongoing_Trades")
        except gspread.WorksheetNotFound:
            _api_limiter.wait_if_needed("gs")
            sheet = spreadsheet.add_worksheet(title="Ongoing_Trades", rows=100, cols=13)
            headers = ["User", "Timestamp", "Pair", "Direction", "Entry", "SL", "TP", "Confidence", "Status", "ClosedDate", "Notes", "Forecast", "Timeframe"]
            _api_limiter.wait_if_needed("gs")
            sheet.append_row(headers)
        return sheet, client
    except Exception as e:
        st.error(f"Ongoing Trades sheet error: {e}")
        return None, None

def save_trade_to_ongoing(trade, username, timeframe, forecast):
    """
    FIX: Properly handle tp key - trade dict uses tp1/tp2/tp3, not tp.
    We save tp1 as the main TP in the sheet.
    """
    sheet, _ = get_ongoing_sheet()
    if sheet:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # FIX: use tp1 if tp not present
            tp_value = trade.get('tp1', trade.get('tp', 0))
            row = [
                username,
                now,
                trade['pair'],
                trade['dir'],
                trade['entry'],
                trade['sl'],
                tp_value,          # FIX: was trade['tp'] which caused KeyError
                trade['conf'],
                "Active",
                "",
                "",
                forecast,
                timeframe
            ]
            _gsheets_limiter.wait_if_needed()
            sheet.append_row(row)
            return True
        except Exception as e:
            st.error(f"Error saving trade: {e}")
            return False
    return False

def load_user_trades(username, status=None):
    sheet, _ = get_ongoing_sheet()
    if sheet:
        try:
            _gsheets_limiter.wait_if_needed()
            all_records = sheet.get_all_records()
            user_trades = []
            for idx, record in enumerate(all_records):
                if record.get('User') == username:
                    if status is None or record.get('Status') == status or (isinstance(status, list) and record.get('Status') in status):
                        record['row_num'] = idx + 2
                        if 'Forecast' not in record: record['Forecast'] = 'N/A'
                        if 'Timeframe' not in record: record['Timeframe'] = 'N/A'
                        user_trades.append(record)
            return user_trades
        except Exception as e:
            st.error(f"Error loading trades: {e}")
            return []
    return []

def update_trade_status_by_row(row_index, new_status, closed_date=""):
    sheet, _ = get_ongoing_sheet()
    if sheet:
        try:
            headers = sheet.row_values(1)
            status_col = headers.index("Status") + 1
            closed_col = headers.index("ClosedDate") + 1
            _gsheets_limiter.wait_if_needed()
            sheet.update_cell(row_index + 2, status_col, new_status)
            if closed_date:
                _gsheets_limiter.wait_if_needed()
                sheet.update_cell(row_index + 2, closed_col, closed_date)
            return True
        except Exception as e:
            st.error(f"Error updating trade: {e}")
            return False
    return False

def delete_trade_by_row_number(row_number):
    sheet, _ = get_ongoing_sheet()
    if not sheet:
        return False
    try:
        row_values = sheet.row_values(row_number)
        headers = sheet.row_values(1)
        if len(row_values) >= len(headers):
            trade_dict = dict(zip(headers, row_values))
            pair = trade_dict.get('Pair', '')
            direction = trade_dict.get('Direction', '')
            entry_str = trade_dict.get('Entry', '0').replace(',', '')
            timeframe = trade_dict.get('Timeframe', '')
            try:
                entry = float(entry_str)
                trade_id = f"{pair}_{timeframe}_{direction}_{entry:.5f}"
                if trade_id in st.session_state.tracked_trades:
                    st.session_state.tracked_trades.remove(trade_id)
            except:
                pass
        sheet.delete_rows(row_number)
        return True
    except Exception as e:
        st.error(f"Error deleting trade: {e}")
        return False

def check_and_update_trades(username):
    sheet, _ = get_ongoing_sheet()
    if not sheet:
        return []
    try:
        _gsheets_limiter.wait_if_needed()
        all_records = sheet.get_all_records()
        for idx, record in enumerate(all_records):
            if record.get('User') == username and record.get('Status') == 'Active':
                pair = record['Pair']
                live = get_live_price(pair)
                if live is None:
                    continue
                try:
                    entry = float(str(record['Entry']).replace(',', ''))
                    sl = float(str(record['SL']).replace(',', ''))
                    tp = float(str(record['TP']).replace(',', ''))
                except:
                    continue
                direction = record['Direction']
                hit = False
                new_status = ""
                if direction == "BUY":
                    if live <= sl: new_status = "SL Hit"; hit = True
                    elif live >= tp: new_status = "TP Hit"; hit = True
                else:
                    if live >= sl: new_status = "SL Hit"; hit = True
                    elif live <= tp: new_status = "TP Hit"; hit = True
                if hit:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    update_trade_status_by_row(idx, new_status, now)
        return load_user_trades(username, status='Active')
    except Exception as e:
        st.error(f"Error checking trades: {e}")
        return []

def is_trade_tracked(scan_trade, active_trades):
    for active in active_trades:
        if active['Pair'] != scan_trade['pair']: continue
        if active['Direction'] != scan_trade['dir']: continue
        try:
            active_entry = float(active['Entry'])
            scan_entry = scan_trade['entry']
            diff_percent = abs(active_entry - scan_entry) / scan_entry
            if diff_percent < 0.001: return True
        except: pass
    return False

def get_current_date_str():
    tz = pytz.timezone('Asia/Colombo')
    return datetime.now(tz).strftime("%Y-%m-%d")

def check_login(username, password):
    if username == "admin" and password == "admin123":
        return {"Username": "Admin", "Role": "Admin", "HybridLimit": 9999, "UsageCount": 0, "LastLogin": get_current_date_str()}
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            _gsheets_limiter.wait_if_needed()
            records = sheet.get_all_records()
            user = next((i for i in records if str(i.get("Username")) == username), None)
            if user and str(user.get("Password")) == password:
                current_date = get_current_date_str()
                last_login_date = str(user.get("LastLogin", ""))
                if last_login_date != current_date:
                    try:
                        _gsheets_limiter.wait_if_needed()
                        cell = sheet.find(username)
                        headers = sheet.row_values(1)
                        if "UsageCount" in headers:
                            _gsheets_limiter.wait_if_needed()
                            sheet.update_cell(cell.row, headers.index("UsageCount") + 1, 0)
                            user["UsageCount"] = 0
                        if "HybridLimit" in headers:
                            _gsheets_limiter.wait_if_needed()
                            sheet.update_cell(cell.row, headers.index("HybridLimit") + 1, 100)
                            user["HybridLimit"] = 100
                        if "LastLogin" in headers:
                            _gsheets_limiter.wait_if_needed()
                            sheet.update_cell(cell.row, headers.index("LastLogin") + 1, current_date)
                            user["LastLogin"] = current_date
                    except Exception as e:
                        print(f"Daily Reset Error: {e}")
                if "HybridLimit" not in user: user["HybridLimit"] = 100
                if "UsageCount" not in user: user["UsageCount"] = 0
                return user
        except: return None
    return None

def update_usage_in_db(username, new_usage):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            _gsheets_limiter.wait_if_needed()
            cell = sheet.find(username)
            if cell:
                headers = sheet.row_values(1)
                if "UsageCount" in headers:
                    col_idx = headers.index("UsageCount") + 1
                    _gsheets_limiter.wait_if_needed()
                    sheet.update_cell(cell.row, col_idx, new_usage)
        except Exception as e: print(f"DB Update Error: {e}")

def update_user_limit_in_db(username, new_limit):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell:
                headers = sheet.row_values(1)
                if "HybridLimit" in headers:
                    col_idx = headers.index("HybridLimit") + 1
                    sheet.update_cell(cell.row, col_idx, new_limit)
            return True
        except Exception as e: return False
    return False

def add_new_user_to_db(username, password, limit):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell: return False, "User already exists!"
            if limit is None: limit = 100
            sheet.append_row([username, password, "User", limit, 0, get_current_date_str()])
            return True, f"User {username} created successfully!"
        except Exception as e:
            return False, f"Error creating user: {e}"
    return False, "Database connection failed"

def get_sentiment_class(title):
    title_lower = title.lower()
    negative_words = ['crash', 'drop', 'fall', 'plunge', 'loss', 'down', 'bear', 'weak', 'inflation', 'war', 'crisis', 'retreat', 'slump', 'missed']
    positive_words = ['surge', 'rise', 'jump', 'gain', 'bull', 'up', 'strong', 'growth', 'profit', 'record', 'soar', 'rally', 'beat', 'positive']
    if any(word in title_lower for word in negative_words): return "news-negative"
    elif any(word in title_lower for word in positive_words): return "news-positive"
    else: return "news-neutral"

def get_market_news(symbol):
    news_list = []
    clean_sym = symbol.replace("=X", "").replace("-USD", "").replace("-USDT", "")
    tz = pytz.timezone('Asia/Colombo')
    try:
        url = f"https://news.google.com/rss/search?q={clean_sym}+finance+market&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for item in root.findall('.//item')[:4]:
                title = item.find('title').text
                link = item.find('link').text
                pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ""
                try:
                    if pubDate:
                        dt = datetime.strptime(pubDate, '%a, %d %b %Y %H:%M:%S %Z')
                        dt_utc = pytz.utc.localize(dt)
                        dt_colombo = dt_utc.astimezone(tz)
                        time_str = dt_colombo.strftime('%H:%M %d/%m')
                    else:
                        time_str = ""
                except:
                    time_str = ""
                news_list.append({"title": title, "link": link, "time": time_str})
    except: pass
    if not news_list:
        try:
            ticker = yf.Ticker(get_yf_symbol(symbol))
            yf_news = ticker.news
            if yf_news:
                for item in yf_news[:4]:
                    title = item.get('title')
                    link = item.get('link')
                    pub_time = item.get('providerPublishTime')
                    if pub_time:
                        dt_utc = datetime.fromtimestamp(pub_time, tz=pytz.utc)
                        dt_colombo = dt_utc.astimezone(tz)
                        time_str = dt_colombo.strftime('%H:%M %d/%m')
                    else:
                        time_str = ""
                    news_list.append({"title": title, "link": link, "time": time_str})
        except: pass
    return news_list

def calculate_news_impact(news_list):
    impact_score = 50
    high_impact_keywords = ['cpi', 'nfp', 'fomc', 'rate', 'gdp', 'fed', 'war', 'crisis']
    for news in news_list:
        title = news['title'].lower()
        if any(kw in title for kw in high_impact_keywords):
            impact_score += 10
        cls = get_sentiment_class(title)
        if cls == "news-positive": impact_score += 5
        elif cls == "news-negative": impact_score -= 5
    return min(max(impact_score, 0), 100)

def calculate_news_score(news_items):
    score = 0
    for news in news_items:
        s_class = get_sentiment_class(news['title'])
        if s_class == "news-positive": score += 10
        elif s_class == "news-negative": score -= 10
    return max(min(score, 20), -20)

def get_data_period(tf):
    # Aligned with get_period_for_tf to ensure consistency
    if tf in ["1m"]: return "5d"
    elif tf == "5m": return "1mo"
    elif tf == "15m": return "3mo"
    elif tf == "1h": return "6mo"
    elif tf == "4h": return "1y"
    elif tf == "1d": return "2y"
    elif tf == "1wk": return "5y"
    return "3mo"

# ==================== RISK ASSESSMENT BADGE ENGINE ====================
def assess_trade_risk(trade):
    """
    Assess trade risk level and return a badge label.
    Returns: ("SAFE" | "MODERATE" | "DANGEROUS", reason_string, badge_class)
    
    Risk factors:
    - RR ratio (higher = safer)
    - MTF score (lower = more dangerous)
    - News impact (high-impact news = more dangerous)
    - Market regime (ranging = more dangerous for trend trades)
    - Wave position (Wave 5 / Wave C End = exhaustion = dangerous)
    - Entry source quality (no OB/Fib = weak entry = dangerous)
    - EW+ICT confidence (low conf = dangerous)
    """
    risk_score = 0  # higher = more dangerous
    reasons = []

    # --- RR Ratio ---
    rr = trade.get('rr_ratio', 0)
    try: rr = float(rr)
    except: rr = 0
    if rr < 1.5: risk_score += 30; reasons.append(f"Low RR ({rr:.1f})")
    elif rr < 2.0: risk_score += 10
    # RR >= 2 is good

    # --- MTF Score ---
    mtf = trade.get('mtf_score', 50)
    try: mtf = float(mtf)
    except: mtf = 50
    if mtf < 45: risk_score += 25; reasons.append(f"Weak MTF ({mtf:.0f}%)")
    elif mtf < 55: risk_score += 10

    # --- EW+ICT Confidence ---
    ew_conf = trade.get('ew_ict_conf', 50)
    if ew_conf < 35: risk_score += 20; reasons.append(f"Low EW/ICT conf ({ew_conf}%)")
    elif ew_conf < 50: risk_score += 8

    # --- Market Regime ---
    regime = trade.get('regime', '')
    if regime == "ranging": risk_score += 15; reasons.append("Ranging market")
    elif regime == "transitioning": risk_score += 7

    # --- Wave Position ---
    ew_label = trade.get('ew_label', '')
    if 'Exhaustion' in ew_label or 'Wave 5' in ew_label or 'Avoid' in ew_label.upper():
        risk_score += 20; reasons.append("Wave 5 exhaustion zone")
    if 'Reversal Watch' in ew_label or 'Invalidated' in ew_label:
        risk_score += 15; reasons.append("Wave invalidation risk")

    # --- Entry Source Quality ---
    entry_src = trade.get('entry_source', '')
    if 'WEAK' in entry_src.upper() or 'No OB' in entry_src:
        risk_score += 15; reasons.append("Weak entry — no OB/Fib")
    elif 'Confluence ⭐' in entry_src:
        risk_score -= 10  # strong entry reduces risk

    # --- Combined Confidence ---
    conf = trade.get('conf', 50)
    if conf < 45: risk_score += 15; reasons.append(f"Low confidence ({conf}%)")

    # --- Classification ---
    if risk_score <= 15:
        return "SAFE", "All risk factors clear", "risk-badge-safe"
    elif risk_score <= 35:
        reason_str = ", ".join(reasons) if reasons else "Minor caution flags"
        return "MODERATE", reason_str, "risk-badge-moderate"
    else:
        reason_str = ", ".join(reasons[:3]) if reasons else "Multiple risk factors"
        return "DANGEROUS", reason_str, "risk-badge-danger"


# ==================== MULTI-TIMEFRAME ANALYSIS (STRICT) ====================
def get_multi_timeframe_analysis(symbol, primary_tf, news_items=None):
    tf_hierarchy = {
        "1m": ["5m", "15m", "1h"], "5m": ["15m", "1h", "4h"],
        "15m": ["1h", "4h", "1d"], "1h": ["4h", "1d", "1wk"],
        "4h": ["1d", "1wk"], "1d": ["1wk"], "1wk": ["1wk"]
    }
    timeframes_to_check = tf_hierarchy.get(primary_tf, ["1h", "4h", "1d"])
    all_tfs = [primary_tf] + timeframes_to_check
    mtf_details = {}
    bull_count = 0
    bear_count = 0
    total_weight = 0
    tf_weights = {"1m": 1, "5m": 2, "15m": 3, "1h": 4, "4h": 5, "1d": 6, "1wk": 7}
    for tf in all_tfs:
        period = get_period_for_tf(tf)
        df_tf = get_cached_historical_data(symbol, tf, period=period)
        if df_tf is None or len(df_tf) < 50: continue
        sigs, _, conf, _, _ = calculate_advanced_signals(df_tf, tf, news_items=None)
        if sigs is None: continue
        weight = tf_weights.get(tf, 3)
        direction = "bull" if conf > 0 else ("bear" if conf < 0 else "neutral")
        mtf_details[tf] = {"direction": direction, "confidence": abs(conf), "trend": sigs['TREND'][0], "weight": weight}
        if direction == "bull": bull_count += weight
        elif direction == "bear": bear_count += weight
        total_weight += weight
    if total_weight == 0:
        return 0, "neutral", mtf_details
    bull_pct = (bull_count / total_weight) * 100
    bear_pct = (bear_count / total_weight) * 100
    if bull_pct >= 60: mtf_direction = "bull"; mtf_score = bull_pct
    elif bear_pct >= 60: mtf_direction = "bear"; mtf_score = bear_pct
    else: mtf_direction = "neutral"; mtf_score = 50
    return mtf_score, mtf_direction, mtf_details

# ==================== SIGNAL QUALITY FILTERS ====================
def validate_signal_confluence(theory_signals, direction):
    if not theory_signals: return 0, False, {}
    dir_key = "bull" if direction == "BUY" else "bear"
    # Theory weights - primary theories get higher weight per user spec
    weighted_signals = {
        'ELLIOTT': 3.5,  # Elliott Wave — PRIMARY (swing direction)
        'ICT':     3.0,  # ICT — PRIMARY (swing direction + FVG/BOS)
        'SMC':     3.0,  # SMC — PRIMARY (structure + OB)
        'FIB':     2.5,  # Fibonacci — PRIMARY (entry + TP)
        'TREND':   2.0,  # Trend direction
        'LIQ':     1.5,  # Liquidity grabs
        'PATT':    1.5,  # Candlestick patterns
        'BB':      1.0,
        'STOCH':   1.0,
        'CCI':     1.0,
        'VOL':     1.0,
        'ADX':     0.5,
    }
    bull_weight = 0; bear_weight = 0; total_weight = 0; conflict_details = {}
    for sig_name, sig_val in theory_signals.items():
        w = weighted_signals.get(sig_name, 1.0)
        if sig_val == "bull": bull_weight += w
        elif sig_val == "bear": bear_weight += w
        total_weight += w
        conflict_details[sig_name] = sig_val
    if total_weight == 0: return 0, False, {}
    dir_weight = bull_weight if dir_key == "bull" else bear_weight
    confluence_pct = (dir_weight / total_weight) * 100
    is_valid = confluence_pct >= 65
    return round(confluence_pct, 1), is_valid, conflict_details

def calculate_signal_quality_score(theory_signals, score_breakdown, direction):
    dir_key = "bull" if direction == "BUY" else "bear"
    agreements = sum(1 for v in theory_signals.values() if v == dir_key)
    conflicts = sum(1 for v in theory_signals.values() if v != dir_key and v != "neutral")
    neutrals = sum(1 for v in theory_signals.values() if v == "neutral")
    total = len(theory_signals)
    if total == 0: return 0
    base = (agreements / total) * 100
    penalty = (conflicts / total) * 30
    neutral_bonus = (neutrals / total) * 5
    quality = base - penalty + neutral_bonus
    return max(0, min(100, round(quality, 1)))

def detect_market_regime(df):
    if df is None or len(df) < 50: return "unknown", 0
    try:
        high_s = df['High'].diff(); low_s = -df['Low'].diff()
        plus_dm = high_s.where((high_s > low_s) & (high_s > 0), 0)
        minus_dm = low_s.where((low_s > high_s) & (low_s > 0), 0)
        tr = pd.concat([df['High'] - df['Low'], (df['High'] - df['Close'].shift()).abs(), (df['Low'] - df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / (atr14 + 1e-10))
        minus_di = 100 * (minus_dm.rolling(14).mean() / (atr14 + 1e-10))
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx_val = dx.rolling(14).mean().iloc[-1]
    except: adx_val = 20
    try:
        sma20 = df['Close'].rolling(20).mean(); std20 = df['Close'].rolling(20).std()
        bb_width = ((sma20 + 2*std20) - (sma20 - 2*std20)) / sma20
        bb_w_val = bb_width.iloc[-1]; bb_w_avg = bb_width.rolling(50).mean().iloc[-1]
        bb_squeeze = bb_w_val < bb_w_avg * 0.8
    except: bb_squeeze = False
    if adx_val >= 25 and not bb_squeeze: return "trending", round(adx_val, 1)
    elif adx_val < 20 or bb_squeeze: return "ranging", round(adx_val, 1)
    else: return "transitioning", round(adx_val, 1)

# ==================== ADVANCED SIGNAL ENGINE ====================
def calculate_advanced_signals(df, tf, news_items=None):
    if df is None or len(df) < 50: return None, 0, 0, {}, {}
    signals = {}; score_breakdown = {}; theory_signals = {}
    c = df['Close'].iloc[-1]; h = df['High'].iloc[-1]; l = df['Low'].iloc[-1]

    ma_50 = df['Close'].rolling(50).mean().iloc[-1]
    ma_200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) > 200 else ma_50
    y_vals = df['Close'].tail(20).values; x_vals = np.arange(len(y_vals))
    slope, intercept = np.polyfit(x_vals, y_vals, 1) if len(y_vals) > 1 else (0, c)
    trend_dir = "neutral"; trend_score = 0
    if c > ma_50 and c > ma_200 and slope > 0: trend_dir = "bull"; trend_score = 20
    elif c < ma_50 and c < ma_200 and slope < 0: trend_dir = "bear"; trend_score = -20
    signals['TREND'] = (f"Trend {trend_dir.upper()} (Slope {slope:.2f})", trend_dir)
    theory_signals['TREND'] = trend_dir; score_breakdown['Trend'] = trend_score

    ema12 = df['Close'].ewm(span=12, adjust=False).mean(); ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26; signal_line = macd.ewm(span=9, adjust=False).mean()
    macd_val = macd.iloc[-1]; sig_val = signal_line.iloc[-1]
    macd_signal = "neutral"; macd_score = 0
    if macd_val > sig_val and macd_val > 0: macd_signal = "bull"; macd_score = 10
    elif macd_val < sig_val and macd_val < 0: macd_signal = "bear"; macd_score = -10
    score_breakdown['MACD'] = macd_score

    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    last_candles = df.tail(5)
    is_bullish_ob = (last_candles['Close'].iloc[-3] < last_candles['Open'].iloc[-3]) and (last_candles['Close'].iloc[-1] > last_candles['High'].iloc[-3])
    is_bearish_ob = (last_candles['Close'].iloc[-3] > last_candles['Open'].iloc[-3]) and (last_candles['Close'].iloc[-1] < last_candles['Low'].iloc[-3])
    smc_signal = "neutral"; smc_score = 0
    if c > highs.iloc[-2] or is_bullish_ob: smc_signal = "bull"; smc_score = 20
    elif c < lows.iloc[-2] or is_bearish_ob: smc_signal = "bear"; smc_score = -20
    signals['SMC'] = (f"{smc_signal.upper()} Structure/OB", smc_signal)
    theory_signals['SMC'] = smc_signal; score_breakdown['SMC'] = smc_score

    fvg_bull = df['Low'].iloc[-1] > df['High'].iloc[-3]
    fvg_bear = df['High'].iloc[-1] < df['Low'].iloc[-3]
    ict_signal = "bull" if fvg_bull else ("bear" if fvg_bear else "neutral")
    ict_score = 10 if ict_signal == "bull" else (-10 if ict_signal == "bear" else 0)
    signals['ICT'] = (f"{ict_signal.upper()} FVG", ict_signal)
    theory_signals['ICT'] = ict_signal; score_breakdown['ICT'] = ict_score

    liq_signal = "neutral"; liq_text = "Holding"
    recent_low = df['Low'].tail(30).min(); recent_high = df['High'].tail(30).max()
    is_at_support = abs(c - recent_low) < (c * 0.002); is_at_resistance = abs(c - recent_high) < (c * 0.002)
    liq_score = 0
    if l < df['Low'].iloc[-10:-1].min() or is_at_support: liq_signal = "bull"; liq_text = "Liq Grab / Support"; liq_score = 15
    elif h > df['High'].iloc[-10:-1].max() or is_at_resistance: liq_signal = "bear"; liq_text = "Liq Grab / Resist"; liq_score = -15
    signals['LIQ'] = (liq_text, liq_signal); theory_signals['LIQ'] = liq_signal; score_breakdown['Liquidity'] = liq_score

    patt_signal = "neutral"; patt_text = "No Pattern"; patt_score = 0
    if (df['Close'].iloc[-1] > df['Open'].iloc[-1] and df['Close'].iloc[-1] > df['Open'].iloc[-2] and df['Open'].iloc[-1] < df['Close'].iloc[-2]):
        patt_signal = "bull"; patt_text = "Bull Engulfing"; patt_score = 15
    elif (df['Close'].iloc[-1] < df['Open'].iloc[-1] and df['Close'].iloc[-1] < df['Open'].iloc[-2] and df['Open'].iloc[-1] > df['Close'].iloc[-2]):
        patt_signal = "bear"; patt_text = "Bear Engulfing"; patt_score = -15
    signals['PATT'] = (patt_text, patt_signal); theory_signals['PATT'] = patt_signal; score_breakdown['Patterns'] = patt_score

    sma_20 = df['Close'].rolling(20).mean(); std_20 = df['Close'].rolling(20).std()
    upper_bb = sma_20 + (std_20 * 2); lower_bb = sma_20 - (std_20 * 2)
    bb_status = "neutral"; bb_text = "Normal Vol"; bb_score = 0
    if c > upper_bb.iloc[-1]: bb_status = "bear"; bb_text = "Overextended"; bb_score = -10
    elif c < lower_bb.iloc[-1]: bb_status = "bull"; bb_text = "Oversold"; bb_score = 10
    signals['VOLATILITY'] = (bb_text, bb_status); theory_signals['BB'] = bb_status; score_breakdown['Bollinger'] = bb_score

    delta = df['Close'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean(); rs = gain / loss
    rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
    signals['RSI'] = (f"RSI: {int(rsi_val)}", "neutral")
    rsi_score = 0
    if rsi_val < 30: rsi_score = 10 if trend_dir == "bull" else -5
    elif rsi_val > 70: rsi_score = -10 if trend_dir == "bear" else 5
    score_breakdown['RSI'] = rsi_score

    ph_fib = df['High'].rolling(50).max().iloc[-1]; pl_fib = df['Low'].rolling(50).min().iloc[-1]
    fib_range = ph_fib - pl_fib; fib_618 = ph_fib - (fib_range * 0.618)
    fib_score = 10 if abs(c - fib_618) < (c * 0.001) else 0
    fib_signal = "bull" if abs(c - fib_618) < (c * 0.001) else "neutral"
    signals['FIB'] = ("Golden Zone", fib_signal) if fib_signal=="bull" else ("Ranging", "neutral")
    theory_signals['FIB'] = fib_signal; score_breakdown['Fibonacci'] = fib_score

    last_50 = df['Close'].tail(50); max_50, min_50 = last_50.max(), last_50.min()
    current_pos = (c - min_50) / (max_50 - min_50) if (max_50 - min_50) != 0 else 0.5
    ew_status = "Wave Analysis"; ew_col = "neutral"; ew_score = 0
    if trend_dir == "bull":
        if current_pos > 0.8: ew_status, ew_col = "Wave 5 (Top)", "bear"; ew_score = -5
        elif 0.4 < current_pos <= 0.8: ew_status, ew_col = "Wave 3 (Impulse)", "bull"; ew_score = 10
        else: ew_status, ew_col = "Wave 1 (Start)", "bull"; ew_score = 5
    else:
        if current_pos < 0.2: ew_status, ew_col = "Wave C (Drop)", "bull"; ew_score = 10
        elif 0.2 <= current_pos < 0.6: ew_status, ew_col = "Wave A (Corr)", "bear"; ew_score = -10
        else: ew_status, ew_col = "Wave B (Rally)", "neutral"; ew_score = 0
    signals['ELLIOTT'] = (ew_status, ew_col); theory_signals['ELLIOTT'] = ew_col; score_breakdown['Elliott'] = ew_score

    stoch_score = 0
    try:
        low_14 = df['Low'].rolling(14).min(); high_14 = df['High'].rolling(14).max()
        stoch_k = 100 * (df['Close'] - low_14) / (high_14 - low_14 + 1e-10)
        stoch_d = stoch_k.rolling(3).mean(); sk = stoch_k.iloc[-1]; sd = stoch_d.iloc[-1]
        if sk < 20 and sd < 20 and sk > sd: stoch_score = 10
        elif sk > 80 and sd > 80 and sk < sd: stoch_score = -10
        theory_signals['STOCH'] = "bull" if stoch_score > 0 else ("bear" if stoch_score < 0 else "neutral")
        score_breakdown['Stochastic'] = stoch_score
    except: score_breakdown['Stochastic'] = 0

    cci_score = 0
    try:
        tp_cci = (df['High'] + df['Low'] + df['Close']) / 3; cci_sma = tp_cci.rolling(20).mean()
        cci_mad = tp_cci.rolling(20).apply(lambda x: np.mean(np.abs(x - np.mean(x))))
        cci_val = (tp_cci - cci_sma) / (0.015 * cci_mad + 1e-10); cv = cci_val.iloc[-1]
        if cv < -100: cci_score = 8
        elif cv > 100: cci_score = -8
        theory_signals['CCI'] = "bull" if cci_score > 0 else ("bear" if cci_score < 0 else "neutral")
        score_breakdown['CCI'] = cci_score
    except: score_breakdown['CCI'] = 0

    vol_score = 0
    try:
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            avg_vol = df['Volume'].rolling(20).mean().iloc[-1]; curr_vol = df['Volume'].iloc[-1]
            vol_ratio = curr_vol / (avg_vol + 1e-10)
            last_close = df['Close'].iloc[-1]; prev_close = df['Close'].iloc[-2]; price_up = last_close > prev_close
            if vol_ratio > 1.5:
                if price_up: vol_score = 8
                else: vol_score = -8
            theory_signals['VOL'] = "bull" if vol_score > 0 else ("bear" if vol_score < 0 else "neutral")
            score_breakdown['Volume'] = vol_score
    except: score_breakdown['Volume'] = 0

    adx_filter = 1.0
    try:
        high_s = df['High'].diff(); low_s = -df['Low'].diff()
        plus_dm = high_s.where((high_s > low_s) & (high_s > 0), 0)
        minus_dm = low_s.where((low_s > high_s) & (low_s > 0), 0)
        tr = pd.concat([df['High'] - df['Low'], (df['High'] - df['Close'].shift()).abs(), (df['Low'] - df['Close'].shift()).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / (atr14 + 1e-10))
        minus_di = 100 * (minus_dm.rolling(14).mean() / (atr14 + 1e-10))
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(14).mean().iloc[-1]
        adx_filter = 1.2 if adx > 25 else (0.8 if adx < 20 else 1.0)
        score_breakdown['ADX_filter'] = round(adx, 1)
        theory_signals['ADX'] = "bull" if plus_di.iloc[-1] > minus_di.iloc[-1] and adx > 25 else ("bear" if minus_di.iloc[-1] > plus_di.iloc[-1] and adx > 25 else "neutral")
    except: adx_filter = 1.0

    if news_items: news_score = calculate_news_score(news_items); score_breakdown['News'] = news_score
    else: news_score = 0

    MAX_POSSIBLE_SCORE = 160.0
    raw_score = (trend_score + macd_score + smc_score + ict_score + liq_score + patt_score +
                 bb_score + rsi_score + fib_score + ew_score + stoch_score + cci_score + vol_score + news_score)
    normalized_score = (raw_score / MAX_POSSIBLE_SCORE) * 100
    normalized_score *= adx_filter
    normalized_score = max(-100, min(100, normalized_score))

    direction_for_check = "BUY" if normalized_score > 0 else "SELL"
    confluence_pct, confluence_valid, _ = validate_signal_confluence(theory_signals, direction_for_check)
    score_breakdown['Confluence_%'] = confluence_pct; score_breakdown['Confluence_Valid'] = confluence_valid

    quality_score = calculate_signal_quality_score(theory_signals, score_breakdown, direction_for_check)
    score_breakdown['Quality_Score'] = quality_score

    regime, adx_strength = detect_market_regime(df)
    score_breakdown['Market_Regime'] = regime; score_breakdown['ADX_Strength'] = adx_strength

    if regime == "ranging": normalized_score *= 0.70
    elif regime == "transitioning": normalized_score *= 0.85

    if not confluence_valid:
        normalized_score *= 0.40; score_breakdown['Confluence_Gate'] = 'FAILED (dampened)'
    else:
        score_breakdown['Confluence_Gate'] = 'PASSED'

    confidence = int(normalized_score)
    final_signal = "neutral"
    if confidence > 10: final_signal = "bull"
    elif confidence < -10: final_signal = "bear"
    signals['SK'] = (f"CONFIDENCE: {abs(confidence)}%", final_signal)

    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    return signals, atr, confidence, score_breakdown, theory_signals


# ==================== THEORY ENGINE v3: ELLIOTT WAVE + ICT DIRECTION (PRECISION) ====================

def find_swing_points(df, window=5):
    """
    Identify proper swing highs and swing lows using a rolling window approach.
    A swing high at i: high[i] is the highest in [i-window, i+window]
    A swing low  at i: low[i]  is the lowest  in [i-window, i+window]
    Returns lists of (index_pos, price) tuples for highs and lows.
    """
    highs_list = []
    lows_list  = []
    h = df['High'].values
    l = df['Low'].values
    for i in range(window, len(df) - window):
        if h[i] == max(h[i-window:i+window+1]):
            highs_list.append((i, h[i]))
        if l[i] == min(l[i-window:i+window+1]):
            lows_list.append((i, l[i]))
    return highs_list, lows_list


def detect_smc_structure(df, swing_highs, swing_lows):
    """
    SMC market structure analysis:
    - BOS (Break of Structure): price closes beyond the last significant swing high/low
    - CHoCH (Change of Character): price reverses after a BOS — signals trend change
    Returns: (structure_bias "bull"/"bear"/"neutral", bos_type, choch_detected, description)
    """
    if not swing_highs or not swing_lows:
        return "neutral", "", False, "Insufficient swing data"

    c = df['Close'].iloc[-1]
    # Last confirmed swing high / low
    last_sh = swing_highs[-1][1]
    last_sl = swing_lows[-1][1]
    prev_sh = swing_highs[-2][1] if len(swing_highs) > 1 else last_sh
    prev_sl = swing_lows[-2][1]  if len(swing_lows) > 1 else last_sl

    bos_bull  = c > last_sh   # Break above last swing high → bullish BOS
    bos_bear  = c < last_sl   # Break below last swing low  → bearish BOS
    choch_bull = bos_bull and prev_sh > last_sh  # Higher high after lower highs = CHoCH bullish
    choch_bear = bos_bear and prev_sl < last_sl  # Lower low after higher lows  = CHoCH bearish

    desc_parts = []
    if bos_bull:
        bias = "bull"
        bos_type = "BOS Bullish"
        if choch_bull: desc_parts.append("CHoCH Bull (Trend Flip)")
        else: desc_parts.append("BOS Bullish")
    elif bos_bear:
        bias = "bear"
        bos_type = "BOS Bearish"
        if choch_bear: desc_parts.append("CHoCH Bear (Trend Flip)")
        else: desc_parts.append("BOS Bearish")
    else:
        bias = "neutral"
        bos_type = ""
        desc_parts.append("Inside Structure (No BOS)")

    # Higher Highs / Higher Lows check (classic market structure)
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        hh = swing_highs[-1][1] > swing_highs[-2][1]
        hl = swing_lows[-1][1]  > swing_lows[-2][1]
        lh = swing_highs[-1][1] < swing_highs[-2][1]
        ll = swing_lows[-1][1]  < swing_lows[-2][1]
        if hh and hl: desc_parts.append("HH+HL (Uptrend)")
        elif lh and ll: desc_parts.append("LH+LL (Downtrend)")

    choch = choch_bull or choch_bear
    return bias, bos_type, choch, " | ".join(desc_parts)


def detect_elliott_wave_ict_direction(df, tf):
    """
    PRECISION Elliott Wave + ICT Direction Engine v3.
    
    Elliott Wave: Uses real swing points to identify wave position.
    ICT: BOS, CHoCH, FVG, Inducement (Liquidity Sweep), OTE zone.
    SMC: Structure bias from higher highs/lows.
    
    Returns: (direction "BUY"/"SELL"/"NEUTRAL", wave_label, ict_context, confidence_pct)
    """
    if df is None or len(df) < 100:
        return "NEUTRAL", "Insufficient Data", "N/A", 0

    c   = df['Close'].iloc[-1]
    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]

    # ── 1. Swing Points (window varies by timeframe) ─────────────────────
    sw_window = 3 if tf in ["1m","5m"] else (4 if tf in ["15m","1h"] else 5)
    swing_highs, swing_lows = find_swing_points(df, window=sw_window)

    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return "NEUTRAL", "Insufficient Swing Data", "N/A", 0

    # ── 2. Higher-timeframe macro structure ───────────────────────────────
    high_100 = df['High'].tail(100).max()
    low_100  = df['Low'].tail(100).min()
    high_50  = df['High'].tail(50).max()
    low_50   = df['Low'].tail(50).min()
    range_100 = high_100 - low_100
    if range_100 < atr * 2:
        return "NEUTRAL", "Flat / Choppy Market", "N/A", 0

    # Price position in macro range (0=bottom, 1=top)
    current_pos = (c - low_100) / range_100

    # ── 3. Trend via MAs + slope ──────────────────────────────────────────
    ma_20 = df['Close'].rolling(20).mean().iloc[-1]
    ma_50 = df['Close'].rolling(50).mean().iloc[-1]
    ma_100 = df['Close'].rolling(100).mean().iloc[-1] if len(df) >= 100 else ma_50
    # Linear regression slope (20-bar)
    y20 = df['Close'].tail(20).values
    slope20 = (y20[-1] - y20[0]) / (len(y20) * atr + 1e-10)  # normalised by ATR

    # ── 4. Elliott Wave identification via swing structure ────────────────
    # Recent 5 swing points for wave counting
    recent_sh = swing_highs[-5:]  # last 5 swing highs (idx, price)
    recent_sl = swing_lows[-5:]   # last 5 swing lows  (idx, price)

    ew_direction = "NEUTRAL"; ew_label = "Wave Unknown"; ew_score = 0

    if slope20 > 0.5 and c > ma_50:  # ── UPTREND ──────────────────
        # Last swing low is the most recent pullback
        last_low_price  = swing_lows[-1][1]
        last_high_price = swing_highs[-1][1]
        prev_low_price  = swing_lows[-2][1] if len(swing_lows) > 1 else low_50

        retracement = (last_high_price - c) / max(last_high_price - last_low_price, atr)
        pullback_deep = last_low_price < swing_lows[-2][1] if len(swing_lows) >= 2 else False

        if current_pos < 0.20:
            ew_label = "Wave 1 (Impulse Start)"; ew_direction = "BUY"; ew_score = 65
        elif 0.20 <= current_pos < 0.42 and c < last_high_price:
            # Price is pulling back — classic Wave 2 entry zone
            # Wave 2 CANNOT break Wave 1 start (Elliott Rule)
            if c > low_100:  # rule: Wave 2 doesn't go below Wave 1 start
                ew_label = "Wave 2 (Correction — BEST BUY)"; ew_direction = "BUY"; ew_score = 92
            else:
                ew_label = "Wave 2 Invalidated"; ew_direction = "NEUTRAL"; ew_score = 15
        elif 0.42 <= current_pos < 0.72:
            ew_label = "Wave 3 (Strong Impulse — BUY)"; ew_direction = "BUY"; ew_score = 80
        elif 0.72 <= current_pos < 0.87 and c < last_high_price:
            ew_label = "Wave 4 (Pullback — BUY)"; ew_direction = "BUY"; ew_score = 70
        elif current_pos >= 0.87:
            ew_label = "Wave 5 (Exhaustion — CAUTION)"; ew_direction = "NEUTRAL"; ew_score = 18
        else:
            ew_label = "Uptrend — Wave Position Unclear"; ew_direction = "BUY"; ew_score = 40

    elif slope20 < -0.5 and c < ma_50:  # ── DOWNTREND ──────────────
        last_high_price = swing_highs[-1][1]
        last_low_price  = swing_lows[-1][1]

        if current_pos > 0.80:
            ew_label = "Wave A (Impulse Drop Start)"; ew_direction = "SELL"; ew_score = 65
        elif 0.58 <= current_pos <= 0.80 and c > last_low_price:
            # Wave B: corrective rally — best sell zone
            if c < high_100:  # rule: Wave B doesn't exceed Wave A start
                ew_label = "Wave B (Correction — BEST SELL)"; ew_direction = "SELL"; ew_score = 92
            else:
                ew_label = "Wave B Invalidated"; ew_direction = "NEUTRAL"; ew_score = 15
        elif 0.28 <= current_pos < 0.58:
            ew_label = "Wave C (Strong Drop — SELL)"; ew_direction = "SELL"; ew_score = 80
        elif current_pos < 0.28:
            ew_label = "Wave C End (Reversal Watch)"; ew_direction = "NEUTRAL"; ew_score = 20
        else:
            ew_label = "Downtrend — Wave Position Unclear"; ew_direction = "SELL"; ew_score = 40

    else:  # Sideways / transitioning
        ew_label = "Corrective Structure (No Clear Wave)"; ew_direction = "NEUTRAL"; ew_score = 20

    # ── 5. SMC Structure ──────────────────────────────────────────────────
    smc_bias, bos_type, choch, smc_desc = detect_smc_structure(df, swing_highs, swing_lows)
    smc_score = 0
    if smc_bias == "bull": smc_score = 25 if choch else 15
    elif smc_bias == "bear": smc_score = 25 if choch else 15

    # ── 6. ICT Concepts ───────────────────────────────────────────────────
    ict_direction = "NEUTRAL"; ict_label = "No ICT Setup"; ict_score = 0

    # Fair Value Gaps (3-candle imbalance)
    fvg_bull = df['Low'].iloc[-1] > df['High'].iloc[-3]
    fvg_bear = df['High'].iloc[-1] < df['Low'].iloc[-3]
    # Multi-candle FVG check (stronger signal)
    fvg_bull_strong = fvg_bull and df['Low'].iloc[-2] > df['High'].iloc[-4] if len(df) >= 4 else fvg_bull
    fvg_bear_strong = fvg_bear and df['High'].iloc[-2] < df['Low'].iloc[-4] if len(df) >= 4 else fvg_bear

    # Liquidity Sweeps (Inducement)
    # Swept equal lows (sell-side taken, now bullish)
    lows_10 = df['Low'].tail(11).values[:-1]  # last 10 bars excluding current
    highs_10 = df['High'].tail(11).values[:-1]
    equal_lows_swept = (df['Low'].iloc[-1] < lows_10.min()) and (c > df['Low'].iloc[-1] + atr * 0.3)
    equal_highs_swept = (df['High'].iloc[-1] > highs_10.max()) and (c < df['High'].iloc[-1] - atr * 0.3)

    # OTE Zone (Optimal Trade Entry: 61.8% – 78.6% retracement)
    impulse_range = high_50 - low_50
    ote_bull_lo = high_50 - impulse_range * 0.786
    ote_bull_hi = high_50 - impulse_range * 0.618
    ote_bear_lo = low_50  + impulse_range * 0.618
    ote_bear_hi = low_50  + impulse_range * 0.786
    in_ote_bull = ote_bull_lo <= c <= ote_bull_hi
    in_ote_bear = ote_bear_lo <= c <= ote_bear_hi

    # Market Structure Shift (MSS) on recent bars (stronger signal)
    last_sh_price = swing_highs[-1][1]
    last_sl_price = swing_lows[-1][1]
    mss_bull = c > last_sh_price  # price is above last swing high
    mss_bear = c < last_sl_price  # price is below last swing low

    ict_parts = []
    bull_ict = (bos_type == "BOS Bullish") or fvg_bull or equal_lows_swept or in_ote_bull or (smc_bias == "bull")
    bear_ict = (bos_type == "BOS Bearish") or fvg_bear or equal_highs_swept or in_ote_bear or (smc_bias == "bear")

    if bull_ict and not (bear_ict and not bull_ict):
        ict_score = sum([
            20 if (bos_type == "BOS Bullish") else 0,
            18 if fvg_bull_strong else (10 if fvg_bull else 0),
            28 if equal_lows_swept else 0,
            22 if in_ote_bull else 0,
            15 if (smc_bias == "bull") else 0,
        ])
        ict_direction = "BUY"
        if bos_type == "BOS Bullish": ict_parts.append("BOS↑")
        if fvg_bull: ict_parts.append("FVG↑" + ("⭐" if fvg_bull_strong else ""))
        if equal_lows_swept: ict_parts.append("Liq Sweep↑")
        if in_ote_bull: ict_parts.append("OTE Zone")
        if smc_bias == "bull": ict_parts.append(f"SMC({smc_desc[:20]})")
        ict_label = " + ".join(ict_parts) if ict_parts else "ICT Bullish"
    elif bear_ict:
        ict_score = sum([
            20 if (bos_type == "BOS Bearish") else 0,
            18 if fvg_bear_strong else (10 if fvg_bear else 0),
            28 if equal_highs_swept else 0,
            22 if in_ote_bear else 0,
            15 if (smc_bias == "bear") else 0,
        ])
        ict_direction = "SELL"
        if bos_type == "BOS Bearish": ict_parts.append("BOS↓")
        if fvg_bear: ict_parts.append("FVG↓" + ("⭐" if fvg_bear_strong else ""))
        if equal_highs_swept: ict_parts.append("Liq Sweep↓")
        if in_ote_bear: ict_parts.append("OTE Zone")
        if smc_bias == "bear": ict_parts.append(f"SMC({smc_desc[:20]})")
        ict_label = " + ".join(ict_parts) if ict_parts else "ICT Bearish"

    # ── 7. Combined Signal ────────────────────────────────────────────────
    if ew_direction == ict_direction and ew_direction != "NEUTRAL":
        final_direction = ew_direction
        combined_conf = min(95, int((ew_score * 0.55 + ict_score * 0.45)))
        if smc_bias == ("bull" if ew_direction == "BUY" else "bear"):
            combined_conf = min(95, combined_conf + 5)  # bonus for 3-way agreement
    elif ew_direction != "NEUTRAL" and ict_direction == "NEUTRAL":
        final_direction = ew_direction
        combined_conf = int(ew_score * 0.65)
    elif ict_direction != "NEUTRAL" and ew_direction == "NEUTRAL":
        final_direction = ict_direction
        combined_conf = int(ict_score * 0.65)
    elif ew_direction != "NEUTRAL" and ict_direction != "NEUTRAL" and ew_direction != ict_direction:
        # Direct conflict → low confidence
        final_direction = "NEUTRAL"
        combined_conf = 15
    else:
        final_direction = "NEUTRAL"
        combined_conf = 15

    ict_context = f"EW: {ew_label} | ICT: {ict_label}"
    return final_direction, ew_label, ict_context, combined_conf


# ==================== SMC + FIBONACCI ENTRY ENGINE (PRECISION v2) ====================
def calculate_smc_fibonacci_entry(df, direction, current_price, atr):
    """
    Short Trade Entry: SMC Order Block + Fibonacci confluence — PRECISION v2.
    
    Key improvements over v1:
    - OB must be validated by proper impulse move (≥1.5× ATR next candle)  
    - Fibonacci levels use ACTUAL swing high/low (not rolling window max/min)
    - Rejects entry if price is MORE than 0.3% away from OB or Fib zone (no chasing)
    - Returns confidence_bonus reflecting entry quality
    """
    if df is None or len(df) < 30:
        return current_price, "Current Price (no data)", 0

    # Proper swing high/low (last 50 bars, window=3)
    sw = min(3, len(df) // 10)
    swing_highs_raw, swing_lows_raw = find_swing_points(df.tail(80), window=sw)

    if swing_highs_raw and swing_lows_raw:
        # Use last valid swing high and low
        recent_high = swing_highs_raw[-1][1]
        recent_low  = swing_lows_raw[-1][1]
        # Ensure high > low; fall back to rolling if inverted
        if recent_high <= recent_low:
            recent_high = df['High'].tail(50).max()
            recent_low  = df['Low'].tail(50).min()
    else:
        recent_high = df['High'].tail(50).max()
        recent_low  = df['Low'].tail(50).min()

    fib_range = recent_high - recent_low
    if fib_range < atr * 0.5:  # market is flat — no reliable Fib
        return current_price, "Current Price (flat market)", 0

    # Fibonacci levels
    if direction == "BUY":
        fib_618 = recent_high - fib_range * 0.618
        fib_705 = recent_high - fib_range * 0.705
        fib_786 = recent_high - fib_range * 0.786
        fib_500 = recent_high - fib_range * 0.500
        golden_lo, golden_hi = fib_786, fib_618
    else:  # SELL
        fib_618 = recent_low + fib_range * 0.618
        fib_705 = recent_low + fib_range * 0.705
        fib_786 = recent_low + fib_range * 0.786
        fib_500 = recent_low + fib_range * 0.500
        golden_lo, golden_hi = fib_618, fib_786

    # In golden zone?
    in_golden = golden_lo <= current_price <= golden_hi
    golden_bonus = 18 if in_golden else 0

    # SMC Order Block Detection — validated OB only
    ob_entry = None; ob_source = None; ob_conf = 0
    scan_start = max(1, len(df) - 60)  # scan last 60 bars

    if direction == "BUY":
        for i in range(scan_start, len(df) - 2):
            is_bearish = df['Close'].iloc[i] < df['Open'].iloc[i]
            body = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
            if not is_bearish or body < atr * 0.30:
                continue  # only meaningful bearish candles
            ob_lo = df['Low'].iloc[i]
            ob_hi = df['High'].iloc[i]
            # Validated: at least one of next 2 candles breaks above OB high with ATR momentum
            validated = False
            for ni in range(i+1, min(i+3, len(df))):
                if df['Close'].iloc[ni] > ob_hi and (df['Close'].iloc[ni] - df['Open'].iloc[ni]) > atr * 0.5:
                    validated = True; break
            if not validated:
                continue
            # Mitigation check: price has NOT yet revisited below OB low (OB still fresh)
            if df['Low'].tail(len(df)-i-1).min() < ob_lo * 0.9985:
                continue
            ob_50pct = (ob_lo + ob_hi) / 2
            ob_75pct = ob_lo + (ob_hi - ob_lo) * 0.75
            # Price is approaching OB from above (pullback)
            if ob_lo - atr * 0.3 <= current_price <= ob_hi + atr * 0.3:
                ob_entry = ob_50pct  # OTE entry at 50% of OB
                ob_source = f"Bull OB@{ob_50pct:.5f} (SMC)"
                ob_conf = 35
                break  # most recent valid OB takes priority

    else:  # SELL
        for i in range(scan_start, len(df) - 2):
            is_bullish = df['Close'].iloc[i] > df['Open'].iloc[i]
            body = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
            if not is_bullish or body < atr * 0.30:
                continue
            ob_lo = df['Low'].iloc[i]
            ob_hi = df['High'].iloc[i]
            validated = False
            for ni in range(i+1, min(i+3, len(df))):
                if df['Close'].iloc[ni] < ob_lo and (df['Open'].iloc[ni] - df['Close'].iloc[ni]) > atr * 0.5:
                    validated = True; break
            if not validated:
                continue
            if df['High'].tail(len(df)-i-1).max() > ob_hi * 1.0015:
                continue
            ob_50pct = (ob_lo + ob_hi) / 2
            if ob_lo - atr * 0.3 <= current_price <= ob_hi + atr * 0.3:
                ob_entry = ob_50pct
                ob_source = f"Bear OB@{ob_50pct:.5f} (SMC)"
                ob_conf = 35
                break

    # Fibonacci proximity check (within 0.3% — tighter than v1's 0.4%)
    fib_entry = None; fib_source = None; fib_conf = 0
    fib_levels = [
        (fib_618, "Fib 0.618 Golden", 28),
        (fib_705, "Fib 0.705", 22),
        (fib_786, "Fib 0.786", 16),
        (fib_500, "Fib 0.500 Mid", 10),
    ]
    for fv, fl, fc in fib_levels:
        if abs(fv - current_price) / max(current_price, 1e-8) < 0.003:
            fib_entry = fv; fib_source = fl; fib_conf = fc
            break

    # Build entry decision
    if ob_entry and fib_entry and abs(ob_entry - fib_entry) / max(fib_entry, 1e-8) < 0.005:
        entry = (ob_entry + fib_entry) / 2
        source = f"OB + {fib_source} Confluence ⭐⭐"
        conf_bonus = ob_conf + fib_conf + golden_bonus + 12
    elif ob_entry:
        entry = ob_entry
        source = ob_source + (" + Golden Zone" if in_golden else "")
        conf_bonus = ob_conf + golden_bonus
    elif fib_entry:
        entry = fib_entry
        source = fib_source + (" + Golden Zone" if in_golden else "")
        conf_bonus = fib_conf + golden_bonus
    elif in_golden:
        entry = current_price
        source = "Current Price (Golden Zone)"
        conf_bonus = golden_bonus
    else:
        # No OB, no Fib proximity, not in golden zone → entry at current price with LOW confidence
        entry = current_price
        source = "Current Price (No OB/Fib — WEAK ENTRY)"
        conf_bonus = 0  # zero bonus → lower overall confidence

    # Hard cap: reject entry if price would chase more than 1.2% away
    if abs(entry - current_price) / max(current_price, 1e-8) > 0.012:
        entry = current_price
        source = "Current Price (OB/Fib too far)"
        conf_bonus = golden_bonus

    return entry, source, conf_bonus


# ==================== THEORY-BASED SL/TP ENGINE (PRECISION v2) ====================
def calculate_theory_sl_tp(df, direction, entry, atr, trade_type, ew_label, theory_signals):
    """
    PRECISION SL/TP Engine v2.
    
    SWING TRADE (Elliott Wave + SMC):
    - SL: BEYOND the ACTUAL Wave 2/B extreme identified by swing points
          Plus SMC Order Block zone invalidation level
          Buffer: ATR × 0.5 (structural buffer — not too tight)
    - TP1: Wave 3 = 1.618 × Wave 1 (Elliott extension)
    - TP2: Wave 3 extended = 2.618 extension
    - TP3: Wave 5 projection = 4.236 extension OR liquidity pool
    
    SHORT TRADE (SMC + Fibonacci):
    - SL: Beyond nearest validated Order Block OR recent swing point + buffer
          Minimum RR: 1.5:1 enforced
    - TP1: First FVG fill (imbalance) or Fib 1.272
    - TP2: Fib 1.618 or next S/R
    - TP3: Fib 2.0 or liquidity pool
    
    SL ANTI-HUNT LOGIC:
    - Minimum SL distance = ATR × 0.8 (no scalping SLs that get hunted)
    - Maximum SL distance = ATR × 4.0 (no oversized stops)
    - SL placed at structural level, not at arbitrary ATR multiple
    """
    if df is None or len(df) < 50:
        sl  = entry - atr * 2.0 if direction == "BUY" else entry + atr * 2.0
        tp1 = entry + atr * 3.0 if direction == "BUY" else entry - atr * 3.0
        tp2 = entry + atr * 5.0 if direction == "BUY" else entry - atr * 5.0
        tp3 = entry + atr * 8.0 if direction == "BUY" else entry - atr * 8.0
        return sl, tp1, tp2, tp3

    high_50 = df['High'].tail(50).max()
    low_50  = df['Low'].tail(50).min()
    structure_range = high_50 - low_50

    supports, resistances = find_key_levels(df)

    # Swing points for structural SL
    sw_window = 3 if len(df) < 100 else 5
    swing_highs, swing_lows = find_swing_points(df.tail(100), window=sw_window)

    def nearest_swing_low_below(price, swings, buffer=0):
        """Find the nearest swing low that is below price"""
        candidates = [sl for (_, sl) in swings if sl < price - buffer]
        return max(candidates) if candidates else None

    def nearest_swing_high_above(price, swings, buffer=0):
        """Find the nearest swing high that is above price"""
        candidates = [sh for (_, sh) in swings if sh > price + buffer]
        return min(candidates) if candidates else None

    if trade_type == "SWING":
        # ─── SWING TRADE: Elliott Wave + SMC SL/TP ──────────────────────────────
        # SL buffer: wider for swing trades (min ATR×0.5 to avoid hunts)
        sl_buf = max(atr * 0.5, structure_range * 0.01)

        if direction == "BUY":
            # SL: Below the most recent CONFIRMED swing low (Wave 2 low)
            # Wave 2 in EW must be above Wave 1 start (low_50 reference)
            struct_sl_level = nearest_swing_low_below(entry, swing_lows, buffer=atr * 0.2)
            if struct_sl_level is None:
                struct_sl_level = low_50

            # Additional checks:
            # 1. SMC: below any nearby bullish OB low
            ob_low = df['Low'].tail(20).min()
            # 2. ICT: below the last swing low (liquidity resting level)
            last_swing_low = swing_lows[-1][1] if swing_lows else low_50

            sl_candidates = [
                struct_sl_level - sl_buf,
                ob_low - sl_buf,
                last_swing_low - sl_buf,
            ]
            # Filter: SL must be below entry but not too far
            valid_sls = [s for s in sl_candidates if 0 < s < entry - atr * 0.8]
            sl = max(valid_sls) if valid_sls else entry - atr * 2.0

            # TP: Elliott Wave extensions from the move
            wave1_estimate = structure_range * 0.38  # conservative wave 1 estimate
            # Use actual entry-to-sl distance to scale wave projections (removes outliers)
            sl_dist = abs(entry - sl)
            ew_tp1 = entry + wave1_estimate * 1.618   # Wave 3 = 1.618×Wave 1
            ew_tp2 = entry + wave1_estimate * 2.618   # Extended Wave 3
            ew_tp3 = entry + wave1_estimate * 4.236   # Wave 5

            # ICT liquidity + FVG targets
            liq_pools   = find_liquidity_pools(df, "BUY", entry, atr)
            fvg_targets = find_fvg_levels(df, "BUY", entry)
            res_above   = sorted([r for r in resistances if r > entry + atr * 0.5])

            # TP1: minimum 2.0× risk
            min_tp1 = entry + sl_dist * 2.0
            tp1_pool = sorted(set([ew_tp1] + fvg_targets[:3] + res_above[:3] + liq_pools[:3]))
            tp1_pool = [t for t in tp1_pool if t >= min_tp1]
            tp1 = tp1_pool[0] if tp1_pool else min_tp1

            # TP2: minimum 3.5× risk
            min_tp2 = entry + sl_dist * 3.5
            tp2_pool = sorted(set([ew_tp2] + res_above + liq_pools))
            tp2_pool = [t for t in tp2_pool if t >= min_tp2 and t > tp1 + atr * 0.5]
            tp2 = tp2_pool[0] if tp2_pool else tp1 + sl_dist * 1.8

            # TP3: minimum 6× risk
            min_tp3 = entry + sl_dist * 6.0
            tp3_pool = sorted(set([ew_tp3] + liq_pools))
            tp3_pool = [t for t in tp3_pool if t >= min_tp3 and t > tp2 + atr * 0.5]
            tp3 = tp3_pool[-1] if tp3_pool else tp2 + sl_dist * 2.5

        else:  # SELL
            sl_buf = max(atr * 0.5, structure_range * 0.01)
            struct_sl_level = nearest_swing_high_above(entry, swing_highs, buffer=atr * 0.2)
            if struct_sl_level is None:
                struct_sl_level = high_50

            ob_high = df['High'].tail(20).max()
            last_swing_high = swing_highs[-1][1] if swing_highs else high_50

            sl_candidates = [
                struct_sl_level + sl_buf,
                ob_high + sl_buf,
                last_swing_high + sl_buf,
            ]
            valid_sls = [s for s in sl_candidates if s > entry + atr * 0.8]
            sl = min(valid_sls) if valid_sls else entry + atr * 2.0

            wave1_estimate = structure_range * 0.38
            sl_dist = abs(sl - entry)
            ew_tp1 = entry - wave1_estimate * 1.618
            ew_tp2 = entry - wave1_estimate * 2.618
            ew_tp3 = entry - wave1_estimate * 4.236

            liq_pools   = find_liquidity_pools(df, "SELL", entry, atr)
            fvg_targets = find_fvg_levels(df, "SELL", entry)
            sup_below   = sorted([s for s in supports if s < entry - atr * 0.5], reverse=True)

            min_tp1 = entry - sl_dist * 2.0
            tp1_pool = sorted(set([ew_tp1] + fvg_targets[:3] + sup_below[:3] + liq_pools[:3]), reverse=True)
            tp1_pool = [t for t in tp1_pool if t <= min_tp1]
            tp1 = tp1_pool[0] if tp1_pool else min_tp1

            min_tp2 = entry - sl_dist * 3.5
            tp2_pool = sorted(set([ew_tp2] + sup_below + liq_pools), reverse=True)
            tp2_pool = [t for t in tp2_pool if t <= min_tp2 and t < tp1 - atr * 0.5]
            tp2 = tp2_pool[0] if tp2_pool else tp1 - sl_dist * 1.8

            min_tp3 = entry - sl_dist * 6.0
            tp3_pool = sorted(set([ew_tp3] + liq_pools), reverse=True)
            tp3_pool = [t for t in tp3_pool if t <= min_tp3 and t < tp2 - atr * 0.5]
            tp3 = tp3_pool[-1] if tp3_pool else tp2 - sl_dist * 2.5

    else:
        # ─── SHORT TRADE: SMC + Fibonacci SL/TP ────────────────────────────────
        tight_buf  = max(atr * 0.2, structure_range * 0.005)
        normal_buf = max(atr * 0.4, structure_range * 0.008)

        if direction == "BUY":
            # SL: Below nearest confirmed Order Block low OR recent swing low
            ob_lo = df['Low'].tail(15).min()
            struct_sl = nearest_swing_low_below(entry, swing_lows, buffer=0)
            if struct_sl is None: struct_sl = low_50

            fib_786_sl = high_50 - (high_50 - low_50) * 0.886  # deep fib as absolute last resort

            sl_candidates = [
                ob_lo - tight_buf,
                struct_sl - tight_buf,
                fib_786_sl,
                entry - atr * 1.2,
            ]
            valid_sls = [s for s in sl_candidates if 0 < s < entry - atr * 0.8]
            sl = max(valid_sls) if valid_sls else entry - atr * 1.5

            # FVG + Fib extensions for TP
            fvg_targets = find_fvg_levels(df, "BUY", entry)
            high_50_ = df['High'].tail(50).max(); low_50_ = df['Low'].tail(50).min()
            fib_range = high_50_ - low_50_
            fib_127 = low_50_ + fib_range * 1.272
            fib_162 = low_50_ + fib_range * 1.618
            fib_200 = low_50_ + fib_range * 2.000
            liq_pools   = find_liquidity_pools(df, "BUY", entry, atr)
            res_above   = sorted([r for r in resistances if r > entry])

            sl_dist = abs(entry - sl)
            min_tp1 = entry + sl_dist * 1.8
            tp1_pool = sorted(set(fvg_targets + res_above[:3] + [fib_127]))
            tp1_pool = [t for t in tp1_pool if t >= min_tp1]
            tp1 = tp1_pool[0] if tp1_pool else min_tp1

            min_tp2 = entry + sl_dist * 3.0
            tp2_pool = sorted(set(res_above + liq_pools + [fib_162]))
            tp2_pool = [t for t in tp2_pool if t >= min_tp2 and t > tp1 + atr * 0.3]
            tp2 = tp2_pool[0] if tp2_pool else tp1 + sl_dist * 1.5

            min_tp3 = entry + sl_dist * 5.0
            tp3_pool = sorted(set(liq_pools + [fib_200]))
            tp3_pool = [t for t in tp3_pool if t >= min_tp3 and t > tp2 + atr * 0.5]
            tp3 = tp3_pool[-1] if tp3_pool else tp2 + sl_dist * 2.0

        else:  # SELL
            ob_hi = df['High'].tail(15).max()
            struct_sl = nearest_swing_high_above(entry, swing_highs, buffer=0)
            if struct_sl is None: struct_sl = high_50

            fib_786_sl = low_50 + (high_50 - low_50) * 0.886

            sl_candidates = [
                ob_hi + tight_buf,
                struct_sl + tight_buf,
                fib_786_sl,
                entry + atr * 1.2,
            ]
            valid_sls = [s for s in sl_candidates if s > entry + atr * 0.8]
            sl = min(valid_sls) if valid_sls else entry + atr * 1.5

            fvg_targets = find_fvg_levels(df, "SELL", entry)
            high_50_ = df['High'].tail(50).max(); low_50_ = df['Low'].tail(50).min()
            fib_range = high_50_ - low_50_
            fib_127 = high_50_ - fib_range * 1.272
            fib_162 = high_50_ - fib_range * 1.618
            fib_200 = high_50_ - fib_range * 2.000
            liq_pools   = find_liquidity_pools(df, "SELL", entry, atr)
            sup_below   = sorted([s for s in supports if s < entry], reverse=True)

            sl_dist = abs(sl - entry)
            min_tp1 = entry - sl_dist * 1.8
            tp1_pool = sorted(set(fvg_targets + sup_below[:3] + [fib_127]), reverse=True)
            tp1_pool = [t for t in tp1_pool if t <= min_tp1]
            tp1 = tp1_pool[0] if tp1_pool else min_tp1

            min_tp2 = entry - sl_dist * 3.0
            tp2_pool = sorted(set(sup_below + liq_pools + [fib_162]), reverse=True)
            tp2_pool = [t for t in tp2_pool if t <= min_tp2 and t < tp1 - atr * 0.3]
            tp2 = tp2_pool[0] if tp2_pool else tp1 - sl_dist * 1.5

            min_tp3 = entry - sl_dist * 5.0
            tp3_pool = sorted(set(liq_pools + [fib_200]), reverse=True)
            tp3_pool = [t for t in tp3_pool if t <= min_tp3 and t < tp2 - atr * 0.5]
            tp3 = tp3_pool[-1] if tp3_pool else tp2 - sl_dist * 2.0

    # ── Final SL Safety Checks ────────────────────────────────────────────
    sl_dist = abs(entry - sl)
    # Anti-hunt: minimum SL distance
    min_sl = atr * (1.0 if trade_type == "SWING" else 0.8)
    # Reasonable maximum
    max_sl = atr * (4.0 if trade_type == "SWING" else 2.5)

    if sl_dist < min_sl:
        sl = (entry - min_sl) if direction == "BUY" else (entry + min_sl)
    if sl_dist > max_sl:
        sl = (entry - max_sl) if direction == "BUY" else (entry + max_sl)

    # TP sanity: TP must be beyond minimum RR
    sl_dist = abs(entry - sl)
    min_rr  = 2.0 if trade_type == "SWING" else 1.8
    if direction == "BUY":
        if tp1 < entry + sl_dist * min_rr: tp1 = entry + sl_dist * min_rr
        if tp2 <= tp1: tp2 = tp1 + sl_dist * 1.5
        if tp3 <= tp2: tp3 = tp2 + sl_dist * 2.0
    else:
        if tp1 > entry - sl_dist * min_rr: tp1 = entry - sl_dist * min_rr
        if tp2 >= tp1: tp2 = tp1 - sl_dist * 1.5
        if tp3 >= tp2: tp3 = tp2 - sl_dist * 2.0

    return sl, tp1, tp2, tp3


# ==================== TRADE TYPE CLASSIFIER ====================
def classify_trade_type(tf, ew_label="", ict_conf=0):
    """
    Classify trade as SWING or SHORT based on timeframe and Elliott Wave context.
    
    SWING: 4h, 1d, 1wk → use Elliott Wave + ICT for direction and SL/TP
    SHORT: 1m, 5m, 15m, 1h → use SMC + Fibonacci for entry and SL/TP
    
    Exception: if strong Elliott Wave signal detected on lower TF, treat as swing.
    """
    swing_tfs = ["4h", "1d", "1wk"]
    short_tfs = ["1m", "5m", "15m", "1h"]
    if tf in swing_tfs:
        return "SWING"
    elif tf in short_tfs:
        # If high ICT confidence on lower TF with clear wave structure, treat as swing
        if ict_conf >= 70 and ew_label not in ["Wave Unknown", "Insufficient Data", "Corrective Structure"]:
            return "SWING"
        return "SHORT"
    return "SHORT"  # default

# ==================== SL/TP CALCULATION (PRECISION ENGINE v2) ====================
def find_key_levels(df, lookback=100):
    """
    Identify significant support/resistance levels using swing highs/lows,
    volume clusters, and liquidity pool detection.
    Returns sorted lists of support and resistance levels.
    """
    highs = df['High'].values[-lookback:]
    lows  = df['Low'].values[-lookback:]
    closes = df['Close'].values[-lookback:]
    supports = []
    resistances = []
    # Swing points with multi-window confirmation
    for window in [3, 5, 8, 13]:
        for i in range(window, len(lows) - window):
            if all(lows[i] <= lows[i-j] for j in range(1, window+1)) and                all(lows[i] <= lows[i+j] for j in range(1, window+1)):
                supports.append(lows[i])
        for i in range(window, len(highs) - window):
            if all(highs[i] >= highs[i-j] for j in range(1, window+1)) and                all(highs[i] >= highs[i+j] for j in range(1, window+1)):
                resistances.append(highs[i])
    # Cluster nearby levels within 0.1% of each other
    def cluster_levels(levels, tol=0.001):
        if not levels: return []
        levels = sorted(set(levels))
        clustered = [levels[0]]
        for l in levels[1:]:
            if abs(l - clustered[-1]) / max(clustered[-1], 1e-10) > tol:
                clustered.append(l)
            else:
                clustered[-1] = (clustered[-1] + l) / 2  # average cluster
        return clustered
    supports = cluster_levels(supports)
    resistances = cluster_levels(resistances)
    return supports, resistances

def find_fvg_levels(df, direction, entry):
    """Fair Value Gaps — SMC imbalance zones"""
    fvg_targets = []
    for i in range(max(0, len(df)-50), len(df)-2):
        try:
            if direction == "BUY":
                # Bullish FVG: gap between candle[i] low and candle[i+2] high (impulse up)
                if df['Low'].iloc[i+2] > df['High'].iloc[i]:
                    gap_top = df['Low'].iloc[i+2]
                    gap_bot = df['High'].iloc[i]
                    mid = (gap_top + gap_bot) / 2
                    if mid > entry: fvg_targets.append(gap_top)  # target top of gap
            else:
                # Bearish FVG: gap between candle[i] high and candle[i+2] low
                if df['High'].iloc[i+2] < df['Low'].iloc[i]:
                    gap_top = df['Low'].iloc[i]
                    gap_bot = df['High'].iloc[i+2]
                    mid = (gap_top + gap_bot) / 2
                    if mid < entry: fvg_targets.append(gap_bot)  # target bottom of gap
        except: continue
    return fvg_targets

def find_liquidity_pools(df, direction, entry, atr):
    """Equal highs/lows = liquidity pools above/below price"""
    pools = []
    tol = atr * 0.3
    highs = df['High'].values[-80:]
    lows  = df['Low'].values[-80:]
    if direction == "BUY":
        # Equal highs above entry = sell-side liquidity to sweep
        for i in range(len(highs)-1):
            for j in range(i+1, len(highs)):
                if abs(highs[i] - highs[j]) < tol and highs[i] > entry:
                    pools.append(highs[i] + tol * 0.5)
    else:
        for i in range(len(lows)-1):
            for j in range(i+1, len(lows)):
                if abs(lows[i] - lows[j]) < tol and lows[i] < entry:
                    pools.append(lows[i] - tol * 0.5)
    return list(set(round(p, 6) for p in pools))

def calculate_advanced_sl_tp(df, direction, entry, atr, tf_type, signals, theory_signals):
    """
    Precision SL/TP engine v2:
    - SL: placed BELOW the true structural invalidation point (not just ATR)
    - TP1/2/3: key S/R levels, FVG tops, liquidity pools, Fibonacci extensions
    - Partial TP spacing ensures realistic targets traders actually use
    """
    # ── helpers ──────────────────────────────────────────────
    def find_swing_low(df_data, window=5):
        lows = df_data['Low'].values
        for i in range(len(lows)-1, window-1, -1):
            if all(lows[i] <= lows[i-j] for j in range(1, window+1) if i-j >= 0): return lows[i]
        return df_data['Low'].tail(window*2).min()

    def find_swing_high(df_data, window=5):
        highs = df_data['High'].values
        for i in range(len(highs)-1, window-1, -1):
            if all(highs[i] >= highs[i-j] for j in range(1, window+1) if i-j >= 0): return highs[i]
        return df_data['High'].tail(window*2).max()

    # ── market structure ──────────────────────────────────────
    swing_window = 3 if tf_type == 'scalp' else 7
    swing_low  = find_swing_low(df, swing_window)
    swing_high = find_swing_high(df, swing_window)

    # Multi-timeframe structural lows/highs (last 20, 50, 100 bars)
    struct_low_20  = df['Low'].tail(20).min()
    struct_low_50  = df['Low'].tail(50).min()
    struct_high_20 = df['High'].tail(20).max()
    struct_high_50 = df['High'].tail(50).max()
    structure_range = struct_high_50 - struct_low_50

    # ── key S/R levels ────────────────────────────────────────
    supports, resistances = find_key_levels(df)

    # ── RSI / pattern context ────────────────────────────────
    rsi_val_str = signals.get('RSI', ("RSI: 50", "neutral"))[0]
    rsi_num = 50
    rsi_match = re.search(r'RSI:\s*(\d+)', rsi_val_str)
    if rsi_match: rsi_num = int(rsi_match.group(1))
    pattern = signals.get('PATT', ("No Pattern", "neutral"))[0]
    ew_status = signals.get('ELLIOTT', ("", "neutral"))[0]

    # ── SL Calculation ────────────────────────────────────────
    # Philosophy: SL must be BEYOND a significant structure point.
    # If price goes there, the setup is truly invalidated.
    tight_buffer  = atr * 0.15   # small wick buffer
    normal_buffer = atr * 0.30   # standard buffer
    wide_buffer   = atr * 0.50   # volatile pairs buffer

    if direction == "BUY":
        # SL candidates (all below entry):
        sl_cands = []
        # 1) Recent swing low (most important)
        sl_cands.append(swing_low - normal_buffer)
        # 2) The lowest wick of last 3 candles (body+wick invalidation)
        last3_low = df['Low'].tail(3).min()
        sl_cands.append(last3_low - tight_buffer)
        # 3) Nearest support level below entry
        supports_below = [s for s in supports if s < entry - atr * 0.5]
        if supports_below: sl_cands.append(max(supports_below) - tight_buffer)
        # 4) Structure low (20-bar) for tighter scalp safety
        sl_cands.append(struct_low_20 - tight_buffer)
        # 5) ATR-based fallback
        base_atr_sl = 1.0 if tf_type == 'scalp' else 1.5
        sl_cands.append(entry - atr * base_atr_sl)
        # 6) Bullish pattern wick invalidation
        if "Engulfing" in pattern or "Hammer" in pattern:
            sl_cands.append(df['Low'].iloc[-1] - tight_buffer)
        # RSI oversold: tighter SL allowed
        if rsi_num < 35: sl_cands.append(entry - atr * 0.8)
        # Filter: must be below entry and positive
        valid_sls = [s for s in sl_cands if 0 < s < entry]
        # Pick the HIGHEST valid SL (tightest stop that is still structural)
        sl = max(valid_sls) if valid_sls else entry - atr * 1.5
        # Safety: don't let SL be too wide (max 3 ATR for scalp, 4 ATR for swing)
        max_sl_dist = atr * (3.0 if tf_type == 'scalp' else 4.0)
        if (entry - sl) > max_sl_dist: sl = entry - max_sl_dist
        # Safety: don't let SL be too tight (min 0.5 ATR)
        if (entry - sl) < atr * 0.5: sl = entry - atr * 0.5

    else:  # SELL
        sl_cands = []
        sl_cands.append(swing_high + normal_buffer)
        last3_high = df['High'].tail(3).max()
        sl_cands.append(last3_high + tight_buffer)
        resistances_above = [r for r in resistances if r > entry + atr * 0.5]
        if resistances_above: sl_cands.append(min(resistances_above) + tight_buffer)
        sl_cands.append(struct_high_20 + tight_buffer)
        base_atr_sl = 1.0 if tf_type == 'scalp' else 1.5
        sl_cands.append(entry + atr * base_atr_sl)
        if "Engulfing" in pattern or "Shooting Star" in pattern:
            sl_cands.append(df['High'].iloc[-1] + tight_buffer)
        if rsi_num > 65: sl_cands.append(entry + atr * 0.8)
        valid_sls = [s for s in sl_cands if s > entry]
        sl = min(valid_sls) if valid_sls else entry + atr * 1.5
        max_sl_dist = atr * (3.0 if tf_type == 'scalp' else 4.0)
        if (sl - entry) > max_sl_dist: sl = entry + max_sl_dist
        if (sl - entry) < atr * 0.5: sl = entry + atr * 0.5

    sl_distance = abs(entry - sl)

    # ── TP Calculation ────────────────────────────────────────
    # TP1 = first key level (partial exit 40% position)
    # TP2 = next major level (partial exit 40% position)
    # TP3 = maximum extension — liquidity pool / major fib (20% position)
    #
    # Min RR ratios (generous enough to be realistic):
    min_rr_tp1 = 1.3 if tf_type == 'scalp' else 1.8
    min_rr_tp2 = 2.2 if tf_type == 'scalp' else 3.0
    min_rr_tp3 = 3.5 if tf_type == 'scalp' else 5.0

    if direction == "BUY":
        # Fibonacci extensions from swing low to swing high
        fib_ext_1272 = struct_low_50 + structure_range * 1.272
        fib_ext_1618 = struct_low_50 + structure_range * 1.618
        fib_ext_2000 = struct_low_50 + structure_range * 2.000
        fib_ext_2618 = struct_low_50 + structure_range * 2.618
        fib_ext_3618 = struct_low_50 + structure_range * 3.618

        # Key resistance levels
        recent_high_20 = struct_high_20
        recent_high_50 = struct_high_50

        # Bollinger Band upper (dynamic resistance)
        bb_upper = (df['Close'].rolling(20).mean() + 2 * df['Close'].rolling(20).std()).iloc[-1]

        # Elliott Wave TP hint
        ew_tp_bonus = []
        if "Wave 3" in ew_status:
            ew_tp_bonus = [entry + structure_range * 1.618, entry + structure_range * 2.618]
        elif "Wave 1" in ew_status:
            ew_tp_bonus = [entry + structure_range * 1.0, entry + structure_range * 1.618]

        # Fair Value Gap tops (imbalance fill targets)
        fvg_targets = find_fvg_levels(df, "BUY", entry)
        # Liquidity pools above entry
        liq_pools = find_liquidity_pools(df, "BUY", entry, atr)
        # Resistance levels above entry
        res_above = sorted([r for r in resistances if r > entry])

        # All TP candidates pool
        raw_cands = ([recent_high_20, recent_high_50, bb_upper,
                      fib_ext_1272, fib_ext_1618, fib_ext_2000, fib_ext_2618, fib_ext_3618]
                     + fvg_targets + liq_pools + res_above + ew_tp_bonus)

        valid_cands = sorted(set(round(c, 8) for c in raw_cands if c > entry + atr * 0.3))

        min_tp1 = entry + sl_distance * min_rr_tp1
        min_tp2 = entry + sl_distance * min_rr_tp2
        min_tp3 = entry + sl_distance * min_rr_tp3

        tp1_pool = [c for c in valid_cands if c >= min_tp1]
        tp1 = tp1_pool[0] if tp1_pool else min_tp1

        tp2_pool = [c for c in valid_cands if c >= min_tp2 and c > tp1 + atr * 0.2]
        tp2 = tp2_pool[0] if tp2_pool else max(tp1 + sl_distance * 0.8, min_tp2)

        tp3_pool = [c for c in valid_cands if c >= min_tp3 and c > tp2 + atr * 0.5]
        # For TP3 prefer the HIGHEST major extension (liquidity sweep target)
        if tp3_pool:
            # Pick the candidate that aligns best with a fib extension or liquidity pool
            fib_exts = [fib_ext_1618, fib_ext_2000, fib_ext_2618, fib_ext_3618]
            fib_aligned = [c for c in tp3_pool if any(abs(c - f) < atr for f in fib_exts)]
            tp3 = fib_aligned[-1] if fib_aligned else tp3_pool[-1]  # furthest fib-aligned
        else:
            tp3 = min_tp3

    else:  # SELL
        fib_ext_1272 = struct_high_50 - structure_range * 1.272
        fib_ext_1618 = struct_high_50 - structure_range * 1.618
        fib_ext_2000 = struct_high_50 - structure_range * 2.000
        fib_ext_2618 = struct_high_50 - structure_range * 2.618
        fib_ext_3618 = struct_high_50 - structure_range * 3.618

        recent_low_20 = struct_low_20
        recent_low_50 = struct_low_50
        bb_lower = (df['Close'].rolling(20).mean() - 2 * df['Close'].rolling(20).std()).iloc[-1]

        ew_tp_bonus = []
        if "Wave C" in ew_status:
            ew_tp_bonus = [entry - structure_range * 1.618, entry - structure_range * 2.618]
        elif "Wave A" in ew_status:
            ew_tp_bonus = [entry - structure_range * 1.0, entry - structure_range * 1.618]

        fvg_targets = find_fvg_levels(df, "SELL", entry)
        liq_pools = find_liquidity_pools(df, "SELL", entry, atr)
        sup_below = sorted([s for s in supports if s < entry], reverse=True)

        raw_cands = ([recent_low_20, recent_low_50, bb_lower,
                      fib_ext_1272, fib_ext_1618, fib_ext_2000, fib_ext_2618, fib_ext_3618]
                     + fvg_targets + liq_pools + sup_below + ew_tp_bonus)

        valid_cands = sorted(set(round(c, 8) for c in raw_cands if c < entry - atr * 0.3), reverse=True)

        min_tp1 = entry - sl_distance * min_rr_tp1
        min_tp2 = entry - sl_distance * min_rr_tp2
        min_tp3 = entry - sl_distance * min_rr_tp3

        tp1_pool = [c for c in valid_cands if c <= min_tp1]
        tp1 = tp1_pool[0] if tp1_pool else min_tp1

        tp2_pool = [c for c in valid_cands if c <= min_tp2 and c < tp1 - atr * 0.2]
        tp2 = tp2_pool[0] if tp2_pool else min(tp1 - sl_distance * 0.8, min_tp2)

        tp3_pool = [c for c in valid_cands if c <= min_tp3 and c < tp2 - atr * 0.5]
        if tp3_pool:
            fib_exts = [fib_ext_1618, fib_ext_2000, fib_ext_2618, fib_ext_3618]
            fib_aligned = [c for c in tp3_pool if any(abs(c - f) < atr for f in fib_exts)]
            tp3 = fib_aligned[-1] if fib_aligned else tp3_pool[-1]
        else:
            tp3 = min_tp3

    return sl, tp1, tp2, tp3

def generate_engine_forecast(df, direction, entry, tp1, tp2, tp3, signals):
    current_price = df['Close'].iloc[-1]
    trend = signals.get('TREND', ("Neutral", "neutral"))[0]
    ew_status = signals.get('ELLIOTT', ("Wave Analysis", "neutral"))[0]
    smc_status = signals.get('SMC', ("SMC", "neutral"))[0]
    ict_status = signals.get('ICT', ("ICT", "neutral"))[0]
    fib_status = signals.get('FIB', ("Fib", "neutral"))[0]
    if direction == "BUY":
        dist1 = ((tp1 - current_price) / current_price) * 100
        dist2 = ((tp2 - current_price) / current_price) * 100
        dist3 = ((tp3 - current_price) / current_price) * 100
        forecast = f"📈 Bullish | Target 1: {tp1:.5f} ({dist1:.2f}%), Target 2: {tp2:.5f} ({dist2:.2f}%), Target 3: {tp3:.5f} ({dist3:.2f}%). EW: {ew_status}. SMC: {smc_status}. ICT: {ict_status}."
    else:
        dist1 = ((current_price - tp1) / current_price) * 100
        dist2 = ((current_price - tp2) / current_price) * 100
        dist3 = ((current_price - tp3) / current_price) * 100
        forecast = f"📉 Bearish | Target 1: {tp1:.5f} ({dist1:.2f}%), Target 2: {tp2:.5f} ({dist2:.2f}%), Target 3: {tp3:.5f} ({dist3:.2f}%). EW: {ew_status}. SMC: {smc_status}. ICT: {ict_status}."
    return forecast

# ==================== AI FUNCTIONS ====================
def call_gemini(prompt):
    gemini_keys = []
    for i in range(1, 8):
        k = st.secrets.get(f"GEMINI_API_KEY_{i}")
        if k: gemini_keys.append(k)
    if not gemini_keys: return None
    for idx, key in enumerate(gemini_keys):
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-3-flash-preview')
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Gemini key {idx+1} failed: {e}"); continue
    return None

def call_groq(prompt):
    groq_keys = []
    for i in range(1, 5):
        key = st.secrets.get(f"GROQ_KEYS_{i}")
        if key: groq_keys.append(key)
    if not groq_keys: return None
    for idx, key in enumerate(groq_keys):
        try:
            client = groq.Client(api_key=key)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7, max_tokens=1000
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Groq key {idx+1} failed: {e}"); continue
    return None

def call_ai_with_fallback(prompt, user_info=None, progress_callback=None):
    if user_info:
        current_usage = user_info.get("UsageCount", 0)
        max_limit = user_info.get("HybridLimit", 30)
        if current_usage >= max_limit and user_info.get("Role") != "Admin":
            return None, "Daily limit reached (30 credits). Please try again tomorrow."
    if progress_callback: progress_callback(0.2, "Trying Gemini...")
    response = call_gemini(prompt)
    if response:
        if user_info and user_info.get("Role") != "Admin":
            new_usage = current_usage + 1; user_info["UsageCount"] = new_usage
            st.session_state.user = user_info; update_usage_in_db(user_info["Username"], new_usage)
        if progress_callback: progress_callback(1.0, "Gemini response received")
        st.session_state.total_api_requests += 1
        return response, "Gemini 3.0 Flash"
    if progress_callback: progress_callback(0.4, "Gemini failed, trying Groq...")
    response = call_groq(prompt)
    if response:
        if user_info and user_info.get("Role") != "Admin":
            new_usage = current_usage + 1; user_info["UsageCount"] = new_usage
            st.session_state.user = user_info; update_usage_in_db(user_info["Username"], new_usage)
        if progress_callback: progress_callback(1.0, "Groq response received")
        st.session_state.total_api_requests += 1
        return response, "Groq (llama-3.3-70b-versatile)"
    if progress_callback: progress_callback(0.7, "Groq failed, trying Puter...")
    try:
        puter_resp = puter.ai.chat(prompt)
        if user_info and user_info.get("Role") != "Admin":
            new_usage = current_usage + 1; user_info["UsageCount"] = new_usage
            st.session_state.user = user_info; update_usage_in_db(user_info["Username"], new_usage)
        if progress_callback: progress_callback(1.0, "Puter response received")
        st.session_state.total_api_requests += 1
        return puter_resp.message.content, "Puter AI (Fallback)"
    except:
        if progress_callback: progress_callback(1.0, "All providers failed")
        return None, "All AI providers failed"

def parse_ai_response(text):
    data = {"CONFIDENCE": "N/A", "FORECAST": "N/A", "SINHALA_SUMMARY": "N/A", "CONFIRMATION": "N/A", "REASON": "N/A"}
    try:
        conf_match = re.search(r"CONFIDENCE\s*[:=]\s*(\d+)", text, re.IGNORECASE)
        if conf_match: data["CONFIDENCE"] = conf_match.group(1)
        forecast_match = re.search(r"FORECAST\s*[:=]\s*(.*?)(?=\n[A-Z]|$)", text, re.IGNORECASE | re.DOTALL)
        if forecast_match: data["FORECAST"] = forecast_match.group(1).strip()
        sinhala_match = re.search(r"SINHALA_SUMMARY\s*[:=]\s*(.+)", text, re.IGNORECASE)
        if sinhala_match: data["SINHALA_SUMMARY"] = sinhala_match.group(1).strip()
        confirm_match = re.search(r"CONFIRMATION\s*:\s*(APPROVE|REJECT)", text, re.IGNORECASE)
        if confirm_match: data["CONFIRMATION"] = confirm_match.group(1).upper()
        reason_match = re.search(r"REASON\s*:\s*(.+)", text, re.IGNORECASE)
        if reason_match: data["REASON"] = reason_match.group(1).strip()
    except: pass
    return data

def get_ai_news_confirmation(pair, direction, current_price, df_hist, news_items, user_info, progress_callback=None, mtf_details=None, score_breakdown=None):
    if df_hist is None or df_hist.empty: return None
    if progress_callback: progress_callback(0.1, "Preparing news data...")
    news_str = "\n".join([f"- {n['title']} (Time: {n['time']})" for n in news_items]) if news_items else "No recent news."
    mtf_str = ""
    if mtf_details:
        for tf_key, tf_data in mtf_details.items():
            dir_sym = "🟢" if tf_data['direction'] == "bull" else ("🔴" if tf_data['direction'] == "bear" else "⚪")
            mtf_str += f"  {dir_sym} {tf_key}: {tf_data['direction'].upper()} (Conf: {tf_data['confidence']}%)\n"
    else: mtf_str = "  Multi-timeframe data not available."
    score_str = ""
    if score_breakdown:
        for k, v in score_breakdown.items(): score_str += f"  {k}: {v}\n"
    prompt = f"""Act as a Senior Hedge Fund Risk Manager specializing in Elliott Wave, ICT, and SMC analysis.
Analyze the following recent news headlines for {pair} and determine if they support a {direction} trade.
Current Price: {current_price:.5f}
Trade Type: {"SWING (Elliott Wave + ICT)" if "SWING" in str(mtf_details) else "SHORT (SMC + Fibonacci)"}
Multi-Timeframe Confluence:
{mtf_str}
Indicator Score Breakdown:
{score_str}
Recent News Headlines:
{news_str}
Task:
1. Based on the news headlines AND multi-timeframe confluence, determine if the news sentiment supports {direction}.
2. Check if MTF alignment agrees with the trade direction.
3. Provide a confidence percentage (0-100%) for your assessment.
4. Give a short-term price forecast based on news + MTF (next 5-10 candles).
5. Finally, give a CONFIRMATION decision: APPROVE or REJECT the {direction} trade setup.
6. Provide a very short summary in SINHALA language (1 sentence) of this combined analysis.
REJECT if: News strongly contradicts the trade direction OR MTF alignment is less than 50% OR Risk is too high.
FINAL OUTPUT FORMAT (STRICT):
CONFIDENCE: XX%
FORECAST: [Brief forecast description based on news + MTF]
SINHALA_SUMMARY: [One sentence in Sinhala]
CONFIRMATION: APPROVE/REJECT
REASON: [Short reason]"""
    if progress_callback: progress_callback(0.3, "Calling AI for news analysis...")
    response, provider = call_ai_with_fallback(prompt, user_info, progress_callback)
    default_conf = 50; default_forecast = "No news available for analysis."
    default_sinhala = "ප්‍රවෘත්ති නොමැත."; default_confirmation = "APPROVE"
    default_reason = "No news data; relying on technical analysis."
    if not response:
        if progress_callback: progress_callback(1.0, "AI failed, using default confirmation")
        return {"confidence": default_conf, "forecast": default_forecast, "sinhala_summary": default_sinhala, "confirmation": default_confirmation, "reason": default_reason, "provider": "Fallback"}
    parsed = parse_ai_response(response)
    if parsed["CONFIRMATION"] == "N/A": parsed["CONFIRMATION"] = default_confirmation; parsed["REASON"] = default_reason
    if progress_callback: progress_callback(1.0, "Done")
    return {
        "confidence": int(parsed["CONFIDENCE"]) if parsed["CONFIDENCE"] != "N/A" else default_conf,
        "forecast": parsed["FORECAST"] if parsed["FORECAST"] != "N/A" else default_forecast,
        "sinhala_summary": parsed["SINHALA_SUMMARY"] if parsed["SINHALA_SUMMARY"] != "N/A" else default_sinhala,
        "confirmation": parsed["CONFIRMATION"],
        "reason": parsed["REASON"],
        "provider": provider
    }

# ==================== FULL INTEGRATED TRADE SETUP ====================
def get_ai_trade_setup(pair, primary_tf, direction, current_price, df_hist, news_items, user_info, progress_callback=None, min_accuracy=40):
    """
    Returns (trade_dict, reject_reason) - trade_dict is None if rejected.
    reject_reason explains WHY the trade was rejected (for display).
    min_accuracy controls Gate 1 confluence threshold dynamically.
    """
    if df_hist is None or df_hist.empty:
        return None, "Insufficient historical data"
    tf_clean = primary_tf.split()[0]

    if progress_callback: progress_callback(0.10, "Gate 1: Signal confluence check...")
    sigs, atr, conf, score_breakdown, theory_signals = calculate_advanced_signals(df_hist, tf_clean, news_items)
    if sigs is None:
        return None, "Gate 1 FAILED: Cannot calculate signals (insufficient data)"

    confluence_pct = score_breakdown.get('Confluence_%', 0)
    # Gate 1: Dynamic threshold — if confluence >= min_accuracy, it passes regardless of hardcoded 65% gate
    confluence_valid = score_breakdown.get('Confluence_Gate', '') == 'PASSED' or confluence_pct >= min_accuracy
    if not confluence_valid:
        return None, f"Gate 1 FAILED: Signal confluence {confluence_pct:.1f}% < {min_accuracy}% threshold (your minimum accuracy)"

    if progress_callback: progress_callback(0.20, "Gate 2: Multi-timeframe analysis...")
    yf_sym = clean_pair_to_yf_symbol(pair)
    mtf_score, mtf_direction, mtf_details = get_multi_timeframe_analysis(yf_sym, tf_clean, news_items)
    # STRICT: MTF must agree OR be close to neutral, but not actively conflict
    mtf_agrees = (mtf_direction == ("bull" if direction == "BUY" else "bear"))
    mtf_neutral = mtf_direction == "neutral"
    # Reject if MTF score < 40 AND MTF direction actively opposes trade direction
    if mtf_score < 40 and not mtf_agrees and not mtf_neutral:
        return None, f"Gate 2 FAILED: MTF actively conflicts — MTF score {mtf_score:.1f}% (MTF dir: {mtf_direction.upper()} vs {direction})"
    # Reject if MTF score is very weak (< 30) even if neutral
    if mtf_score < 30:
        return None, f"Gate 2 FAILED: MTF score {mtf_score:.1f}% too weak (< 30% minimum)"

    if progress_callback: progress_callback(0.30, "Gate 3: Market regime check...")
    regime, adx_strength = detect_market_regime(df_hist)
    if regime == "ranging" and abs(conf) < 30:
        return None, f"Gate 3 FAILED: Ranging market (ADX: {adx_strength}) with weak signal ({abs(conf)}%)"

    if progress_callback: progress_callback(0.38, "Gate 4: Elliott Wave + ICT direction analysis...")
    # ── THEORY ENGINE: Direction + Entry + SL/TP ─────────────────────────

    # Step 1: Elliott Wave + ICT — find swing direction
    ew_ict_direction, ew_label, ict_context, ew_ict_conf = detect_elliott_wave_ict_direction(df_hist, tf_clean)

    # Step 2: Classify trade type
    trade_type = classify_trade_type(tf_clean, ew_label, ew_ict_conf)

    # Step 3: Direction validation
    # Primary direction from engine; Elliott+ICT acts as higher-TF filter
    # If EW+ICT strongly disagrees with engine direction, reject
    if ew_ict_conf >= 55 and ew_ict_direction != "NEUTRAL" and ew_ict_direction != direction:
        return None, f"Gate 4 FAILED: Elliott Wave + ICT direction ({ew_ict_direction}) conflicts with engine signal ({direction}). EW/ICT conf: {ew_ict_conf}%"
    # Also reject if EW+ICT is too low confidence (no clear structure)
    if ew_ict_conf < 25 and ew_ict_direction == "NEUTRAL":
        return None, f"Gate 4 FAILED: Elliott Wave + ICT cannot determine direction (conf: {ew_ict_conf}%). No clear wave structure."

    if progress_callback: progress_callback(0.45, f"Gate 4: {trade_type} trade — {'SMC+Fib' if trade_type=='SHORT' else 'EW+ICT'} entry calculation...")

    # Step 4: Entry calculation based on trade type
    if trade_type == "SHORT":
        # Short trade: SMC Order Block + Fibonacci entry
        final_entry, entry_source, entry_conf_bonus = calculate_smc_fibonacci_entry(df_hist, direction, current_price, atr)
    else:
        # Swing trade: ICT Optimal Trade Entry (OTE) zone — 61.8-78.6% retracement
        recent_high = df_hist['High'].tail(50).max()
        recent_low  = df_hist['Low'].tail(50).min()
        fib_range = recent_high - recent_low
        entry_conf_bonus = 0

        if direction == "BUY":
            ote_lo = recent_high - fib_range * 0.786
            ote_hi = recent_high - fib_range * 0.618
            if ote_lo <= current_price <= ote_hi:
                final_entry = current_price
                entry_source = f"ICT OTE Zone (0.618-0.786) | {ew_label}"
                entry_conf_bonus = 20
            else:
                final_entry = current_price
                entry_source = f"Current Price | {ew_label}"
        else:
            ote_lo = recent_low + fib_range * 0.618
            ote_hi = recent_low + fib_range * 0.786
            if ote_lo <= current_price <= ote_hi:
                final_entry = current_price
                entry_source = f"ICT OTE Zone (0.618-0.786) | {ew_label}"
                entry_conf_bonus = 20
            else:
                final_entry = current_price
                entry_source = f"Current Price | {ew_label}"

    if progress_callback: progress_callback(0.50, "Gate 5: Theory-based SL/TP and RR...")

    # Step 5: Theory-based SL/TP
    min_rr_required = 1.8 if trade_type == "SHORT" else 2.0  # Stricter RR minimums
    sl, tp1, tp2, tp3 = calculate_theory_sl_tp(df_hist, direction, final_entry, atr, trade_type, ew_label, theory_signals)

    # Fallback to advanced SL/TP if theory returns invalid levels
    try:
        sl_dist = abs(final_entry - sl)
        if sl_dist <= 0 or sl_dist > atr * 8:
            tf_type_fallback = 'scalp' if tf_clean in ['1m','5m','15m'] else 'swing'
            sl, tp1, tp2, tp3 = calculate_advanced_sl_tp(df_hist, direction, final_entry, atr, tf_type_fallback, sigs, theory_signals)
    except:
        tf_type_fallback = 'scalp' if tf_clean in ['1m','5m','15m'] else 'swing'
        sl, tp1, tp2, tp3 = calculate_advanced_sl_tp(df_hist, direction, final_entry, atr, tf_type_fallback, sigs, theory_signals)
    sl_distance = abs(final_entry - sl); tp1_distance = abs(tp1 - final_entry)
    rr_ratio = round(tp1_distance / sl_distance, 2) if sl_distance > 0 else 0
    if rr_ratio < min_rr_required:
        return None, f"Gate 5 FAILED: R:R ratio 1:{rr_ratio} < minimum 1:{min_rr_required} required (Trade type: {trade_type})"

    if progress_callback: progress_callback(0.65, "Gate 6: AI news confirmation...")
    ai_result = get_ai_news_confirmation(pair, direction, current_price, df_hist, news_items, user_info, progress_callback, mtf_details, score_breakdown)
    if not ai_result:
        return None, "Gate 6 FAILED: AI confirmation unavailable"
    if ai_result['confirmation'] == 'REJECT':
        return None, f"Gate 6 FAILED: AI REJECTED - {ai_result.get('reason', 'News/MTF conflict')}"

    engine_conf = min(100, abs(conf)); ai_conf = ai_result['confidence']
    quality_sc = score_breakdown.get('Quality_Score', 50)
    combined_conf = int(engine_conf * 0.35 + ai_conf * 0.30 + mtf_score * 0.20 + quality_sc * 0.15)
    combined_conf = min(100, max(0, combined_conf))
    if progress_callback: progress_callback(1.0, "Analysis complete.")

    engine_forecast = generate_engine_forecast(df_hist, direction, final_entry, tp1, tp2, tp3, sigs)
    trade = {
        "pair": pair, "tf": primary_tf, "dir": direction,
        "entry": final_entry, "sl": sl,
        "tp": tp1,  # FIX: ensure 'tp' key always present (same as tp1)
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "conf": combined_conf, "engine_conf": engine_conf, "ai_conf": ai_conf,
        "quality_score": quality_sc, "confluence_pct": confluence_pct,
        "mtf_score": mtf_score, "mtf_direction": mtf_direction, "mtf_agrees": mtf_agrees,
        "mtf_details": mtf_details, "rr_ratio": rr_ratio, "regime": regime, "adx_strength": adx_strength,
        "price": current_price, "live_price": get_live_price(pair) or current_price,
        "symbol_orig": clean_pair_to_yf_symbol(pair),
        "forecast": engine_forecast, "ai_forecast": ai_result['forecast'],
        "confirmation": ai_result['confirmation'], "reason": ai_result['reason'],
        "provider": ai_result['provider'], "sinhala_summary": ai_result['sinhala_summary'],
        "entry_source": entry_source, "timeframe": tf_clean,
        "theory_signals": theory_signals, "score_breakdown": score_breakdown,
        # ── NEW: Theory classification & labels ──
        "trade_type": trade_type,           # "SWING" or "SHORT"
        "ew_label": ew_label,               # e.g. "Wave 3 (Strong Impulse)"
        "ict_context": ict_context,         # ICT setup description
        "ew_ict_conf": ew_ict_conf,         # EW+ICT confidence %
        "entry_conf_bonus": entry_conf_bonus,
    }
    return trade, None

# ==================== ENGINE FUNCTIONS ====================
def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr, tf, df, theory_signals):
    if sigs is None: return "Insufficient Data for Analysis"
    confidence = sigs['SK'][0]; signal_dir = sigs['SK'][1]; trend = sigs['TREND'][0]
    if tf in ["1m", "5m"]: trade_mode = "SCALPING (වේගවත්)"; tf_type = 'scalp'
    else: trade_mode = "SWING (දිගු කාලීන)"; tf_type = 'swing'
    action = "WAIT"; status_sinhala = "ප්‍රවේශම් වන්න. වෙළඳපල අවිනිශ්චිතයි."
    sl, tp1, tp2, tp3 = 0, 0, 0, 0
    if signal_dir == "bull":
        action = "BUY"; status_sinhala = "වෙළඳපල ගැනුම්කරුවන් අත. (Market is Bullish)"
        sl, tp1, tp2, tp3 = calculate_advanced_sl_tp(df, "BUY", curr_p, atr, tf_type, sigs, theory_signals)
    elif signal_dir == "bear":
        action = "SELL"; status_sinhala = "වෙළඳපල විකුණුම්කරුවන් අත. (Market is Bearish)"
        sl, tp1, tp2, tp3 = calculate_advanced_sl_tp(df, "SELL", curr_p, atr, tf_type, sigs, theory_signals)
    analysis_text = f"""♾️ **INFINITE ALGO ENGINE V28.0 (AI-POWERED SCANNER)**
📊 **වෙළඳපල විශ්ලේෂණය ({tf}):**
• Trade Type: {trade_mode}
• Signal Confidence: {confidence}
• Action: {action}
• Trend: {trend}
• Liquidity: {sigs['LIQ'][0]}
💡 **නිගමනය:**
{status_sinhala}
DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP1={tp1:.5f} | TP2={tp2:.5f} | TP3={tp3:.5f}"""
    return analysis_text

def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info, tf, df, theory_signals):
    if sigs is None: return "Error: Insufficient Signal Data", "System Error", None, None
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr, tf, df, theory_signals)
    current_usage = user_info.get("UsageCount", 0); max_limit = user_info.get("HybridLimit", 30)
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return algo_result, "Infinite Algo (Limit Reached)", None, None
    news_str = "\n".join([f"- {n['title']}" for n in news_items])
    prompt = f"""Act as a Senior Hedge Fund Risk Manager & Technical Analyst.
Analyze {pair} on {tf} timeframe.
Technical Signals: Trend: {sigs['TREND'][0]}, SMC: {sigs['SMC'][0]}, RSI: {sigs['RSI'][0]}, Algo: {sigs['SK'][1].upper()} ({sigs['SK'][0]}), ICT: {sigs['ICT'][0]}
Recent News: {news_str}
Provide analysis in SINHALA (technical terms in English). Give ENTRY, SL, TP based on ATR ({atr:.5f}).
Output: [Sinhala Analysis]
DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx
FORECAST: [Brief forecast]
CONFIRMATION: APPROVE/REJECT
REASON: [Short reason]"""
    response, provider = call_ai_with_fallback(prompt, user_info)
    if response:
        new_usage = current_usage + 1; user_info["UsageCount"] = new_usage
        st.session_state.user = user_info
        if user_info["Username"] != "Admin": update_usage_in_db(user_info["Username"], new_usage)
        confirm_match = re.search(r"CONFIRMATION\s*:\s*(APPROVE|REJECT)", response, re.IGNORECASE)
        reason_match = re.search(r"REASON\s*:\s*(.+)", response, re.IGNORECASE)
        confirmation = confirm_match.group(1).upper() if confirm_match else "N/A"
        reason = reason_match.group(1).strip() if reason_match else ""
        return response, f"{provider} | Used: {new_usage}/{max_limit}", confirmation, reason
    else:
        return algo_result, "Infinite Algo (Default)", None, None

def get_deep_hybrid_analysis(trade, user_info, df_hist_original):
    pair = trade['pair']; symbol_orig = trade.get('symbol_orig', clean_pair_to_yf_symbol(pair))
    news_items = get_market_news(symbol_orig); news_str = "\n".join([f"- {n['title']}" for n in news_items])
    live_price = trade.get('live_price', trade['price']); tf_display = trade['tf']
    timeframes = ["15m", "1h", "4h", "1d"]; tf_signals = {}
    for tf in timeframes:
        period_map = {"15m": "1mo", "1h": "3mo", "4h": "6mo", "1d": "1y"}
        try:
            df_tf = get_cached_historical_data(get_yf_symbol(symbol_orig), tf, period=period_map[tf])
            if df_tf is not None and len(df_tf) > 50:
                sigs, _, _, _, theory = calculate_advanced_signals(df_tf, tf, news_items=None)
                if sigs:
                    tf_signals[tf] = {"trend": sigs['TREND'][0], "smc": sigs['SMC'][0], "rsi": sigs['RSI'][0], "signal": sigs['SK'][1].upper(), "confidence": sigs['SK'][0], "theory": theory}
        except Exception as e: print(f"Error fetching {tf} data for {pair}: {e}")
    mtf_summary = "".join([f"- {tf}: {sig['signal']} (Conf: {sig['confidence']}), Trend: {sig['trend']}\n" for tf, sig in tf_signals.items()])
    rr_ratio = trade.get('rr_ratio', 'N/A'); engine_conf = trade.get('engine_conf', 'N/A')
    ai_conf = trade.get('ai_conf', 'N/A'); mtf_score_val = trade.get('mtf_score', 'N/A')
    combined_conf = trade.get('conf', 'N/A'); score_bd = trade.get('score_breakdown', {})
    score_str = "\n".join([f"  - {k}: {v}" for k, v in score_bd.items()])
    # FIX: safely get tp1 with fallback to tp
    tp1_val = trade.get('tp1', trade.get('tp', 'N/A'))
    tp2_val = trade.get('tp2', 'N/A'); tp3_val = trade.get('tp3', 'N/A')
    prompt = f"""Act as a Senior Hedge Fund Risk Manager & Technical Analyst.
Asset: {pair} | Timeframe: {tf_display} | Direction: {trade['dir']}
Entry: {trade['entry']:.5f} | SL: {trade['sl']:.5f} | TP1: {tp1_val} | TP2: {tp2_val} | TP3: {tp3_val}
R:R: 1:{rr_ratio} | Combined Conf: {combined_conf}% | Engine: {engine_conf}% | AI News: {ai_conf}% | MTF: {mtf_score_val}%
Live Price: {live_price:.5f}
Indicator Scores:
{score_str}
Multi-Timeframe:
{mtf_summary}
Recent News:
{news_str}
Evaluate RR, theory signal alignment, MTF confluence, news sentiment. Provide analysis in SINHALA.
REJECT if: RR < 1.2 OR MTF < 50% OR News contradicts direction OR Theory signals conflict.
Output:
[Sinhala Analysis]
RISK:REWARD = x:y
FORECAST: [Brief forecast]
CONFIRMATION: APPROVE/REJECT
REASON: [Short reason]"""
    current_usage = user_info.get("UsageCount", 0); max_limit = user_info.get("HybridLimit", 30)
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return "Daily limit reached. Please try again tomorrow.", "Limit Reached", None, None
    response, provider = call_ai_with_fallback(prompt, user_info)
    if response:
        new_usage = current_usage + 1; user_info["UsageCount"] = new_usage
        st.session_state.user = user_info
        if user_info["Username"] != "Admin": update_usage_in_db(user_info["Username"], new_usage)
        confirm_match = re.search(r"CONFIRMATION\s*:\s*(APPROVE|REJECT)", response, re.IGNORECASE)
        reason_match = re.search(r"REASON\s*:\s*(.+)", response, re.IGNORECASE)
        confirmation = confirm_match.group(1).upper() if confirm_match else "N/A"
        reason = reason_match.group(1).strip() if reason_match else ""
        return response, f"{provider} | Used: {new_usage}/{max_limit}", confirmation, reason
    else:
        return "Deep analysis failed.", "Error", None, None

# ==================== BACKTEST ====================
def run_backtest(market_choice, start_date, end_date, min_accuracy, user_info, assets_dict):
    assets_list = []
    if market_choice == "All": assets_list = assets_dict["Forex"] + assets_dict["Crypto"] + assets_dict["Metals"]
    else: assets_list = assets_dict[market_choice]
    interval = "1d"
    start = datetime.combine(start_date, datetime.min.time()); end = datetime.combine(end_date, datetime.max.time())
    results = []; total_trades = 0; winning_trades = 0; total_profit = 0.0
    progress_bar = st.progress(0, text="Running backtest..."); total_assets = len(assets_list)
    for idx, symbol in enumerate(assets_list):
        progress_bar.progress((idx+1)/total_assets, text=f"Backtesting {symbol}...")
        try:
            df = get_cached_historical_data(get_yf_symbol(symbol), interval, start=start, end=end)
            if df is None or len(df) < 10: continue
            df = df.tail(30)
            for i in range(len(df)-1):
                row = df.iloc[i]; current_price = row['Close']
                df_up_to_now = df.iloc[:i+1].copy()
                if len(df_up_to_now) < 50: continue
                sigs, atr, conf, _, theory = calculate_advanced_signals(df_up_to_now, interval, news_items=None)
                if sigs and abs(conf) > min_accuracy:
                    direction = "BUY" if conf > 0 else "SELL"
                    news_items = get_market_news(symbol)
                    clean_sym = symbol.replace("=X","").replace("-USD","").replace("-USDT","")
                    ai_trade, reject_reason = get_ai_trade_setup(clean_sym, interval, direction, current_price, df_up_to_now, news_items, user_info, min_accuracy=min_accuracy)
                    if ai_trade and ai_trade['confirmation'] == "APPROVE":
                        next_row = df.iloc[i+1]; exit_price = next_row['Close']
                        if direction == "BUY": profit = (exit_price - ai_trade['entry']) / ai_trade['entry']
                        else: profit = (ai_trade['entry'] - exit_price) / ai_trade['entry']
                        total_trades += 1
                        if profit > 0: winning_trades += 1
                        total_profit += profit
                        results.append({"symbol": symbol, "date": row.name, "direction": direction, "entry": ai_trade['entry'], "exit": exit_price, "profit_pct": profit * 100, "confidence": ai_trade['conf']})
        except Exception as e: print(f"Backtest error for {symbol}: {e}"); continue
    progress_bar.empty()
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    profit_factor = total_profit / abs(total_profit) if total_profit != 0 else 0
    return {"results": results, "total_trades": total_trades, "winning_trades": winning_trades, "win_rate": win_rate, "total_profit_pct": total_profit * 100, "profit_factor": profit_factor}

def get_current_session():
    now_utc = datetime.now(pytz.utc); hour = now_utc.hour
    if 0 <= hour < 8: return "Asia"
    elif 8 <= hour < 16: return "London"
    elif 16 <= hour < 24: return "New York"
    else: return "Other"

# ==================== ENHANCED SCAN WITH REJECTED TRADES LOGGING ====================
def scan_market_with_ai(assets_list, user_info, timeframes, min_accuracy=40):
    """
    Scan market. Returns (approved_trades, rejected_trades).
    rejected_trades list contains dicts with pair, tf, direction, reject_reason, conf, confluence_pct.
    All 6 accuracy gates enforced. Rejected trades show WHY they failed.
    """
    all_trades = []
    rejected_trades = []  # NEW: collect rejected trades with reasons

    progress_bars = {}
    for tf in timeframes:
        progress_bars[tf] = st.progress(0, text=f"Scanning {tf}...")

    total_assets = len(assets_list)

    for idx, symbol in enumerate(assets_list):
        for tf in timeframes:
            progress_bars[tf].progress((idx+1)/total_assets, text=f"Scanning {symbol} on {tf}...")

        try:
            for tf in timeframes:
                period = get_period_for_tf(tf)
                df = get_cached_historical_data(get_yf_symbol(symbol), tf, period=period)
                if df is None or len(df) < 50:
                    continue

                sigs, atr, conf, score_bd, theory = calculate_advanced_signals(df, tf, news_items=None)
                if sigs is None:
                    continue

                # Pre-filter: must have some signal strength before spending AI credits
                if abs(conf) < max(15, min_accuracy * 0.4):
                    continue

                clean_sym = symbol.replace("=X","").replace("-USD","").replace("-USDT","")
                direction = "BUY" if conf > 0 else "SELL"
                curr_price = df['Close'].iloc[-1]
                confluence_pct = score_bd.get('Confluence_%', 0)
                quality_sc = score_bd.get('Quality_Score', 0)

                # Pre-filter: confluence gate (no AI call if confluence failed)
                # Dynamic: if confluence >= min_accuracy, allow it even if hardcoded 65% gate failed
                confluence_gate_passed = score_bd.get('Confluence_Gate', '') == 'PASSED' or confluence_pct >= min_accuracy
                if not confluence_gate_passed:
                    # Calculate basic SL/TP so we can show levels and allow manual save
                    try:
                        sigs_r, atr_r, _, _, theory_r = calculate_advanced_signals(df, tf, news_items=None)
                        tf_type_r = 'scalp' if tf in ['1m','5m','15m'] else 'swing'
                        sl_r, tp1_r, tp2_r, tp3_r = calculate_advanced_sl_tp(df, direction, curr_price, atr_r, tf_type_r, sigs_r or {}, theory_r or {})
                    except:
                        atr_r = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
                        sl_r  = curr_price - atr_r * 1.5 if direction == "BUY" else curr_price + atr_r * 1.5
                        tp1_r = curr_price + atr_r * 2.0 if direction == "BUY" else curr_price - atr_r * 2.0
                        tp2_r = curr_price + atr_r * 3.0 if direction == "BUY" else curr_price - atr_r * 3.0
                        tp3_r = curr_price + atr_r * 4.5 if direction == "BUY" else curr_price - atr_r * 4.5
                    rejected_trades.append({
                        "pair": clean_sym, "tf": tf, "dir": direction,
                        "price": curr_price,
                        "entry": curr_price, "sl": sl_r, "tp1": tp1_r, "tp2": tp2_r, "tp3": tp3_r,
                        "reject_reason": f"Confluence {confluence_pct:.1f}% < {min_accuracy}% (your minimum accuracy)",
                        "failed_gate": "Gate 1",
                        "engine_conf": abs(conf),
                        "confluence_pct": confluence_pct,
                        "quality_sc": quality_sc,
                        "conf": round(abs(conf)),
                    })
                    continue

                news_items = get_market_news(symbol)

                # Full 6-gate analysis (now returns tuple)
                ai_trade, reject_reason = get_ai_trade_setup(
                    clean_sym, f"{tf} (Auto)", direction,
                    curr_price, df, news_items, user_info, min_accuracy=min_accuracy
                )

                if ai_trade is None:
                    gate = "Unknown Gate"
                    if reject_reason and "Gate" in reject_reason:
                        gate_match = re.search(r"(Gate \d+)", reject_reason)
                        if gate_match: gate = gate_match.group(1)
                    # Calculate levels so user can manually save if desired
                    try:
                        sigs_r2, atr_r2, _, _, theory_r2 = calculate_advanced_signals(df, tf, news_items=None)
                        tf_type_r2 = 'scalp' if tf in ['1m','5m','15m'] else 'swing'
                        sl_r2, tp1_r2, tp2_r2, tp3_r2 = calculate_advanced_sl_tp(df, direction, curr_price, atr_r2, tf_type_r2, sigs_r2 or {}, theory_r2 or {})
                    except:
                        atr_r2 = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
                        sl_r2  = curr_price - atr_r2 * 1.5 if direction == "BUY" else curr_price + atr_r2 * 1.5
                        tp1_r2 = curr_price + atr_r2 * 2.0 if direction == "BUY" else curr_price - atr_r2 * 2.0
                        tp2_r2 = curr_price + atr_r2 * 3.0 if direction == "BUY" else curr_price - atr_r2 * 3.0
                        tp3_r2 = curr_price + atr_r2 * 4.5 if direction == "BUY" else curr_price - atr_r2 * 4.5
                    rejected_trades.append({
                        "pair": clean_sym, "tf": tf, "dir": direction,
                        "price": curr_price,
                        "entry": curr_price, "sl": sl_r2, "tp1": tp1_r2, "tp2": tp2_r2, "tp3": tp3_r2,
                        "reject_reason": reject_reason or "Unknown reason",
                        "failed_gate": gate,
                        "engine_conf": abs(conf),
                        "confluence_pct": confluence_pct,
                        "quality_sc": quality_sc,
                        "conf": round(abs(conf)),
                    })
                    continue

                # Post-filter: combined confidence threshold
                if ai_trade['conf'] < min_accuracy:
                    rejected_trades.append({
                        "pair": clean_sym, "tf": tf, "dir": direction,
                        "price": curr_price,
                        # Full trade data available since ai_trade was computed
                        "entry": ai_trade.get('entry', curr_price),
                        "sl": ai_trade.get('sl', curr_price),
                        "tp1": ai_trade.get('tp1', curr_price),
                        "tp2": ai_trade.get('tp2', curr_price),
                        "tp3": ai_trade.get('tp3', curr_price),
                        "reject_reason": f"Combined confidence {ai_trade['conf']}% < minimum {min_accuracy}%",
                        "failed_gate": "Post-filter",
                        "engine_conf": abs(conf),
                        "confluence_pct": confluence_pct,
                        "quality_sc": quality_sc,
                        "combined_conf": ai_trade['conf'],
                        "conf": ai_trade['conf'],
                        "rr_ratio": ai_trade.get('rr_ratio', 'N/A'),
                        "mtf_score": ai_trade.get('mtf_score', 'N/A'),
                        "mtf_agrees": ai_trade.get('mtf_agrees', True),
                        "regime": ai_trade.get('regime', ''),
                        "sinhala_summary": ai_trade.get('sinhala_summary', ''),
                        "forecast": ai_trade.get('forecast', ''),
                        "timeframe": tf,
                    })
                    continue

                ai_trade['timeframe'] = tf
                trade_id = f"{clean_sym}_{tf}_{direction}_{ai_trade['entry']:.5f}"

                if trade_id not in st.session_state.tracked_trades:
                    if save_trade_to_ongoing(ai_trade, user_info['Username'], tf, ai_trade.get('forecast', 'N/A')):
                        st.session_state.tracked_trades.add(trade_id)
                        all_trades.append(ai_trade)

        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            continue

    for tf in timeframes:
        progress_bars[tf].empty()

    return all_trades, rejected_trades

# ==================== CHART FUNCTIONS ====================
def create_forecast_chart(historical_df, entry_price, sl, tp1, tp2, tp3, forecast_text, sinhala_summary):
    hist = historical_df.tail(30).copy()
    last_date = hist.index[-1]
    if isinstance(last_date, pd.Timestamp):
        if len(hist) > 1:
            deltas = hist.index.to_series().diff().dropna(); median_delta = deltas.median()
            if pd.isna(median_delta) or median_delta.total_seconds() == 0:
                total_seconds = (hist.index[-1] - hist.index[0]).total_seconds()
                avg_seconds = total_seconds / (len(hist)-1) if len(hist) > 1 else 3600
                median_delta = timedelta(seconds=avg_seconds)
        else: median_delta = timedelta(hours=1)
        future_dates = [last_date + (i+1)*median_delta for i in range(15)]
    else: future_dates = list(range(len(hist), len(hist)+15))
    direction = "bullish" if tp1 > entry_price else "bearish"
    forecast_prices = np.linspace(entry_price, tp3, len(future_dates))
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name='Historical', showlegend=True))
    fig.add_trace(go.Scatter(x=future_dates, y=forecast_prices, mode='lines+markers', name=f'Forecast ({direction})', line=dict(color='#00ff99', width=3, dash='dot'), marker=dict(size=5, color='#00ff99', symbol='circle')))
    fig.add_hline(y=entry_price, line_dash="dashdot", line_color="#ffff00", annotation_text="Entry", annotation_position="bottom right")
    fig.add_hline(y=sl, line_dash="dash", line_color="#ff4b4b", annotation_text="SL", annotation_position="bottom right")
    fig.add_hline(y=tp1, line_dash="dash", line_color="#00ff00", annotation_text="TP1", annotation_position="top right")
    fig.add_hline(y=tp2, line_dash="dash", line_color="#00cc00", annotation_text="TP2", annotation_position="top right")
    fig.add_hline(y=tp3, line_dash="dash", line_color="#009900", annotation_text="TP3", annotation_position="top right")
    if forecast_text and forecast_text != 'N/A':
        fig.add_annotation(x=future_dates[-1] if future_dates else hist.index[-1], y=forecast_prices[-1], text=forecast_text, showarrow=True, arrowhead=2, font=dict(size=12, color="white"), bgcolor="#1e1e1e", bordercolor="#00ff99", borderwidth=1, borderpad=4, ax=20, ay=-30)
    fig.add_annotation(x=0.5, y=1.1, xref="paper", yref="paper", text=f"🇱🇰 {sinhala_summary}", showarrow=False, font=dict(size=14, color="#00ff99"), align="center", bgcolor="rgba(30,30,30,0.9)", bordercolor="#00ff99", borderwidth=1, borderpad=8)
    fig.update_layout(title=f"AI Forecast & Partial Close Levels ({direction.capitalize()})", template="plotly_dark", height=500, margin=dict(l=0, r=0, t=80, b=0), xaxis_title="Time", yaxis_title="Price", hovermode="x unified", xaxis=dict(rangeslider=dict(visible=False), type='date' if isinstance(last_date, pd.Timestamp) else 'linear'))
    return fig

def create_mini_chart(df, entry_price, sl, tp1, tp2, tp3):
    hist = df.tail(20).copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist['Close'], mode='lines', line=dict(color='#00ff99', width=2), name='Price'))
    fig.add_hline(y=entry_price, line_dash="dash", line_color="#ffff00", line_width=1)
    fig.add_hline(y=sl, line_dash="dash", line_color="#ff4b4b", line_width=1)
    fig.add_hline(y=tp1, line_dash="dash", line_color="#00ff00", line_width=1)
    fig.add_hline(y=tp2, line_dash="dash", line_color="#00cc00", line_width=1)
    fig.add_hline(y=tp3, line_dash="dash", line_color="#009900", line_width=1)
    fig.update_layout(template="plotly_dark", height=100, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, xaxis=dict(showticklabels=False, showgrid=False), yaxis=dict(showticklabels=False, showgrid=False))
    return fig

def create_technical_chart(df, tf):
    df = df.copy()
    df['MA50'] = df['Close'].rolling(50).mean(); df['MA200'] = df['Close'].rolling(200).mean()
    df['BB_upper'] = df['Close'].rolling(20).mean() + 2*df['Close'].rolling(20).std()
    df['BB_lower'] = df['Close'].rolling(20).mean() - 2*df['Close'].rolling(20).std()
    exp12 = df['Close'].ewm(span=12, adjust=False).mean(); exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26; df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean(); df['MACD_hist'] = df['MACD'] - df['Signal']
    delta = df['Close'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss; df['RSI'] = 100 - (100 / (1 + rs))
    recent_high = float(df['High'].tail(20).max()); recent_low = float(df['Low'].tail(20).min())
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.15, 0.15, 0.2], subplot_titles=('Price & Indicators', 'MACD', 'RSI', 'Volume'))
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='orange', width=1), name='MA50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], line=dict(color='blue', width=1), name='MA200'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_upper'], line=dict(color='gray', width=1, dash='dash'), name='BB Upper'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_lower'], line=dict(color='gray', width=1, dash='dash'), name='BB Lower'), row=1, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=recent_high, y1=recent_high, line=dict(color="red", width=1, dash="dot"), row=1, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=recent_low, y1=recent_low, line=dict(color="green", width=1, dash="dot"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue'), name='MACD'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='orange'), name='Signal'), row=2, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['MACD_hist'], marker_color='gray', name='Histogram'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=3, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=70, y1=70, line=dict(color="red", dash="dash"), row=3, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=30, y1=30, line=dict(color="green", dash="dash"), row=3, col=1)
    colors = ['red' if close < open else 'green' for close, open in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='Volume'), row=4, col=1)
    fig.update_layout(height=800, template='plotly_dark', showlegend=False)
    fig.update_xaxes(rangeslider_visible=False)
    return fig

def create_theory_chart(df, tf):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Price', showlegend=False))
    if isinstance(df.index, pd.DatetimeIndex):
        ts = {idx: idx.timestamp() * 1000 for idx in df.index}
    else:
        ts = {idx: i for i, idx in enumerate(df.index)}
    window = 5; swing_highs = []; swing_lows = []
    for i in range(window, len(df)-window):
        high_window = df['High'].iloc[i-window:i+window+1].tolist()
        low_window = df['Low'].iloc[i-window:i+window+1].tolist()
        current_high = float(df['High'].iloc[i]); current_low = float(df['Low'].iloc[i])
        if np.isclose(current_high, max(high_window)): swing_highs.append((df.index[i], current_high))
        if np.isclose(current_low, min(low_window)): swing_lows.append((df.index[i], current_low))
    if swing_highs: fig.add_trace(go.Scatter(x=[x[0] for x in swing_highs], y=[x[1] for x in swing_highs], mode='markers', marker=dict(color='red', size=5, symbol='triangle-down'), name='Swing High', showlegend=True))
    if swing_lows: fig.add_trace(go.Scatter(x=[x[0] for x in swing_lows], y=[x[1] for x in swing_lows], mode='markers', marker=dict(color='green', size=5, symbol='triangle-up'), name='Swing Low', showlegend=True))
    recent_high = float(df['High'].tail(20).max()); recent_low = float(df['Low'].tail(20).min())
    fig.add_hline(y=recent_high, line_dash="dot", line_color="orange", annotation_text="Resistance", annotation_position="top right")
    fig.add_hline(y=recent_low, line_dash="dot", line_color="blue", annotation_text="Support", annotation_position="bottom right")
    high_50 = df['High'].tail(50).max(); low_50 = df['Low'].tail(50).min()
    if high_50 > low_50:
        for level in [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]:
            price = low_50 + (high_50 - low_50) * level
            fig.add_hline(y=price, line_dash="dash", line_color="purple", opacity=0.3, annotation_text=f"Fib {level*100:.1f}%", annotation_position="right")
    swings = sorted(swing_highs + swing_lows, key=lambda x: x[0])
    if len(swings) > 3:
        labels = ['1', '2', '3', '4', '5']
        for i, (idx, price) in enumerate(swings[-5:]):
            if i < len(labels):
                fig.add_annotation(x=idx, y=price, text=labels[i], showarrow=True, arrowhead=1, ax=0, ay=-20 if i%2==0 else 20, font=dict(color='cyan', size=12))
    for i in range(1, len(df)-1):
        if df['Low'].iloc[i] > df['High'].iloc[i+1]:
            try: fig.add_vrect(x0=ts[df.index[i]], x1=ts[df.index[i+1]], fillcolor="green", opacity=0.1, line_width=0)
            except: pass
        elif df['High'].iloc[i] < df['Low'].iloc[i+1]:
            try: fig.add_vrect(x0=ts[df.index[i]], x1=ts[df.index[i+1]], fillcolor="red", opacity=0.1, line_width=0)
            except: pass
    fig.update_layout(title=f"SMC/ICT Theory Chart ({tf})", template="plotly_dark", height=600, xaxis_title="Time", yaxis_title="Price", hovermode="x unified")
    return fig

# ==================== DASHBOARD FUNCTIONS ====================
def get_major_prices():
    majors = {"EUR/USD": "EURUSD", "GBP/USD": "GBPUSD", "USD/JPY": "USDJPY", "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "XAU/USD": "XAUUSD"}
    prices = {}
    for name, sym in majors.items():
        price = get_live_price(sym)
        prices[name] = f"{price:.4f}" if price else "N/A"
    return prices

def generate_dashboard_forecast(market, pair_display, tf, user_info):
    pair_map = {}
    if market == "Forex":
        pair_map = {p: p.replace("/","")+"=X" for p in ["EUR/USD","GBP/USD","USD/JPY","AUD/USD","USD/CAD","NZD/USD","USD/CHF","USD/SEK","USD/NOK","USD/TRY","USD/ZAR","EUR/TRY","EUR/SEK","EUR/NOK","GBP/SEK","GBP/NOK","AUD/CHF","CAD/CHF","NZD/CHF","CHF/JPY","EUR/HUF","USD/HUF","EUR/PLN","USD/PLN","EUR/CZK","USD/CZK"]}
    elif market == "Crypto":
        pair_map = {p: p.replace("/","-")+"D" for p in ["BTC/US","ETH/US","SOL/US","BNB/US","XRP/US","ADA/US","DOGE/US","MATIC/US","DOT/US","LINK/US","AVAX/US","UNI/US","LTC/US","BCH/US","ALGO/US","VET/US","ICP/US","FIL/US","AAVE/US","AXS/US","SAND/US","MANA/US","EGLD/US","THETA/US"]}
        # Fix crypto pairs
        pair_map = {f"{b}/USD": f"{b}-USD" for b in ["BTC","ETH","SOL","BNB","XRP","ADA","DOGE","MATIC","DOT","LINK","AVAX","UNI","LTC","BCH","ALGO","VET","ICP","FIL","AAVE","AXS","SAND","MANA","EGLD","THETA"]}
    else:
        pair_map = {"XAU/USD": "XAUUSD=X", "XAG/USD": "XAGUSD=X", "XPT/USD": "XPTUSD=X", "XPD/USD": "XPDUSD=X"}
    yf_sym = pair_map.get(pair_display, pair_display)
    clean_pair = yf_sym.replace("=X","").replace("-USD","")
    period = get_period_for_tf(tf)
    progress_bar = st.progress(0, text="Starting forecast generation...")
    def update_progress(progress, text): progress_bar.progress(progress, text=text)
    try:
        update_progress(0.1, "Downloading data...")
        df = get_cached_historical_data(yf_sym, tf, period=period)
        if df is None or len(df) < 50:
            progress_bar.empty(); return None, "Insufficient data", None
        update_progress(0.3, "Calculating signals...")
        current_price = df['Close'].iloc[-1]
        sigs, atr, conf, _, theory = calculate_advanced_signals(df, tf, news_items=None)
        direction = "BUY" if conf > 0 else "SELL" if conf < 0 else "BUY"
        update_progress(0.5, "Fetching news...")
        news_items = get_market_news(yf_sym)
        update_progress(0.7, "Calling AI for news confirmation...")
        ai_trade, reject_reason = get_ai_trade_setup(clean_pair, tf, direction, current_price, df, news_items, user_info, update_progress, min_accuracy=st.session_state.get("min_accuracy", 40))
        if not ai_trade:
            progress_bar.empty(); return None, f"AI analysis failed: {reject_reason}", None
        update_progress(0.9, "Creating forecast chart...")
        # FIX: safely use tp1 for chart
        tp1_val = ai_trade.get('tp1', ai_trade.get('tp', current_price))
        tp2_val = ai_trade.get('tp2', tp1_val); tp3_val = ai_trade.get('tp3', tp2_val)
        chart = create_forecast_chart(df, ai_trade['entry'], ai_trade['sl'], tp1_val, tp2_val, tp3_val, ai_trade.get('forecast',''), ai_trade.get('sinhala_summary',''))
        progress_bar.progress(1.0, "Done"); time.sleep(0.5); progress_bar.empty()
        return chart, ai_trade['provider'], ai_trade
    except Exception as e:
        progress_bar.empty(); return None, str(e), None

def analyze_news_impact(news_items, target_pair, user_info):
    news_titles = "\n".join([f"- {n['title']} (Time: {n['time']})" for n in news_items])
    prompt = f"""Based on the following recent market news headlines (with Colombo times), analyze the impact on {target_pair}.
Provide a brief summary in SINHALA language, indicating whether the news is positive, negative, or neutral for {target_pair}, and why.
Also mention the time of the news that is most relevant.
News:
{news_titles}
Output format:
IMPACT: [positive/negative/neutral]
REASON: [Sinhala reason]
TIME: [most relevant news time]"""
    response, provider = call_ai_with_fallback(prompt, user_info)
    return response, provider

# ==================== MAIN APPLICATION ====================
if not st.session_state.logged_in:
    st.markdown("<div class='main-title'><h1>⚡ INFINITE AI TERMINAL v32.0</h1><p>Elliott Wave + ICT | SMC + Fibonacci | Multi-Timeframe | 50 req/min Rate Engine | Risk Badges</p></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login_form"):
            u, p = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Access Terminal"):
                user = check_login(u, p)
                if user:
                    st.session_state.logged_in = True; st.session_state.user = user
                    st.session_state.login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); st.rerun()
                else: st.error("Invalid Credentials")
else:
    user_info = st.session_state.get('user', {})
    st.session_state.last_activity = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    active_trades = check_and_update_trades(user_info['Username'])

    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    st.sidebar.caption(f"Credits: {user_info.get('UsageCount', 0)}/{user_info.get('HybridLimit', 30)}")
    st.sidebar.checkbox("👶 Beginner Mode", value=st.session_state.beginner_mode, key="beginner_mode_toggle")
    st.session_state.beginner_mode = st.session_state.beginner_mode_toggle
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Session Info")
    st.sidebar.markdown(f"""<div class='session-card'><span>User:</span> {user_info['Username']}<br><span>Login:</span> {st.session_state.login_time or 'N/A'}<br><span>Last Activity:</span> {st.session_state.last_activity}<br><span>Status:</span> ✅ Active</div>""", unsafe_allow_html=True)
    auto_refresh = st.sidebar.checkbox("🔄 Auto-Monitor (60s)", value=False)
    if st.sidebar.button("Logout"): st.session_state.logged_in = False; st.rerun()

    # ── Compact API rate meter in sidebar ─────────────────────────────────
    _usage = _api_limiter.usage_stats()
    _pct   = _usage["pct_used"]
    _mc    = "#00ff00" if _pct < 60 else ("#ffaa00" if _pct < 85 else "#ff4b4b")
    st.sidebar.markdown(f"""<div style='background:#0e0e0e;border:1px solid {_mc}44;border-radius:8px;padding:8px 10px;margin-top:8px;font-size:12px;'>
        <b style='color:{_mc};'>⚡ API Rate</b>
        <div style='background:#222;border-radius:4px;height:5px;margin:4px 0;'>
            <div style='background:{_mc};width:{min(_pct,100):.0f}%;height:5px;border-radius:4px;'></div>
        </div>
        <span style='color:#888;'>GS: {_usage['gs_used']}/{_usage['gs_cap']} &nbsp; YF: {_usage['yf_used']}/{_usage['yf_cap']} &nbsp; Total: {_usage['total_used']}/50</span>
    </div>""", unsafe_allow_html=True)

    nav_options = ["Dashboard", "Market Scanner", "Ongoing Trades"]
    if user_info.get("Role") == "Admin" and not st.session_state.beginner_mode: nav_options.append("Admin Panel")
    if not st.session_state.beginner_mode: nav_options.append("Backtest")
    app_mode = st.sidebar.radio("Navigation", nav_options)

    assets = {
        "Forex": ["EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCHF=X","USDCAD=X","NZDUSD=X","EURJPY=X","GBPJPY=X","EURGBP=X","EURCHF=X","CADJPY=X","AUDJPY=X","NZDJPY=X","GBPAUD=X","GBPCAD=X","EURCAD=X","AUDCAD=X","AUDNZD=X","EURNZD=X","USDSEK=X","USDNOK=X","USDTRY=X","USDZAR=X","EURTRY=X","EURSEK=X","EURNOK=X","GBPSEK=X","GBPNOK=X","AUDCHF=X","CADCHF=X","NZDCHF=X","CHFJPY=X","EURHUF=X","USDHUF=X","EURPLN=X","USDPLN=X","EURCZK=X","USDCZK=X"],
        "Crypto": ["BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD","ADA-USD","DOGE-USD","MATIC-USD","DOT-USD","LINK-USD","AVAX-USD","UNI-USD","LTC-USD","BCH-USD","ALGO-USD","VET-USD","ICP-USD","FIL-USD","AAVE-USD","AXS-USD","SAND-USD","MANA-USD","EGLD-USD","THETA-USD"],
        "Metals": ["XAUUSD=X","XAGUSD=X","XPTUSD=X","XPDUSD=X"]
    }

    if app_mode == "Dashboard":
        st.title("📊 Trading Dashboard")
        st.markdown("""<div class='system-engine-card'><div class='engine-icon'>⚙️</div><h2>SYSTEM ANALYSIS ENGINE</h2><div class='engine-text'>🔴 Real-time Analysis Engine Running • Theory + Indicators + MTF + News • AI Processing</div></div>""", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""<div class='dashboard-card'><h3>👤 User Profile</h3><p><span class='metric-label'>Username:</span> <span class='metric-value'>{user_info['Username']}</span></p><p><span class='metric-label'>Role:</span> {user_info.get('Role', 'User')}</p><p><span class='metric-label'>Credits Used:</span> {user_info.get('UsageCount', 0)} / {user_info.get('HybridLimit', 30)}</p><p><span class='metric-label'>Last Login:</span> {user_info.get('LastLogin', 'N/A')}</p></div>""", unsafe_allow_html=True)
        with col2:
            prices = get_major_prices()
            price_html = "<div class='dashboard-card'><h3>💰 Live Prices</h3><table class='live-price-table'>"
            for name, price in prices.items():
                price_html += f"<tr><td>{name}</td><td><b>{price}</b></td></tr>"
            price_html += "</table></div>"
            st.markdown(price_html, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""<div class='dashboard-card'><h3>📈 Market Pulse</h3><p><span class='metric-label'>Current Session:</span> <b>{get_current_session()}</b></p><p><span class='metric-label'>Active Trades:</span> <b>{len(active_trades)}</b></p><p><span class='metric-label'>Scanner Accuracy Threshold:</span> {st.session_state.min_accuracy}%</p><p><span class='metric-label'>Analysis Engine:</span> Theory + Indicators + MTF + News</p></div>""", unsafe_allow_html=True)

        st.markdown("### 🎯 Trades Near Entry")
        near_entry_trades = []
        for trade in active_trades:
            live = get_live_price(trade['Pair'])
            if live:
                entry = float(trade['Entry']); diff_pct = abs(live - entry) / entry * 100
                if diff_pct < 0.5: near_entry_trades.append((trade, live))
        if near_entry_trades:
            for trade, live in near_entry_trades:
                color = "#00ff00" if trade['Direction'] == "BUY" else "#ff4b4b"
                st.markdown(f"<div style='background:#1e1e1e; padding:10px; border-radius:8px; border-left:5px solid {color}; margin-bottom:5px;'><b>{trade['Pair']} | {trade['Direction']}</b> - Live: {live:.4f} (Entry: {trade['Entry']})</div>", unsafe_allow_html=True)
        else:
            st.info("No trades are near entry price currently.")

        st.markdown("### 📈 Theory Card - AI Forecast")
        col_a, col_b, col_c, col_d, col_e = st.columns([1,2,2,1,1])
        with col_a:
            selected_market = st.selectbox("Market", options=["Forex","Crypto","Metals"], index=0, key="theory_market")
        if selected_market == "Forex":
            pair_options = ["EUR/USD","GBP/USD","USD/JPY","AUD/USD","USD/CAD","NZD/USD","USD/CHF","USD/SEK","USD/NOK","USD/TRY","USD/ZAR","EUR/TRY","EUR/SEK","EUR/NOK","GBP/SEK","GBP/NOK","AUD/CHF","CAD/CHF","NZD/CHF","CHF/JPY","EUR/HUF","USD/HUF","EUR/PLN","USD/PLN","EUR/CZK","USD/CZK"]
        elif selected_market == "Crypto":
            pair_options = ["BTC/USD","ETH/USD","SOL/USD","BNB/USD","XRP/USD","ADA/USD","DOGE/USD","MATIC/USD","DOT/USD","LINK/USD","AVAX/USD","UNI/USD","LTC/USD","BCH/USD","ALGO/USD","VET/USD","ICP/USD","FIL/USD","AAVE/USD","AXS/USD","SAND/USD","MANA/USD","EGLD/USD","THETA/USD"]
        else:
            pair_options = ["XAU/USD","XAG/USD","XPT/USD","XPD/USD"]
        with col_b:
            selected_pair = st.selectbox("Currency Pair", options=pair_options, index=0, key="theory_pair")
        with col_c:
            selected_tf = st.selectbox("Timeframe", options=["15m","1h","4h","1d"], index=1, key="theory_tf")
        with col_d:
            generate_btn = st.button("🔮 Generate Forecast", type="primary", use_container_width=True)
        with col_e:
            if not st.session_state.beginner_mode:
                tech_btn = st.button("📊 Technical Chart", use_container_width=True)
                theory_btn = st.button("📐 Theory Chart", use_container_width=True)

        # Get yf symbol for selected pair
        if selected_market == "Forex":
            yf_sym = selected_pair.replace("/","") + "=X"
        elif selected_market == "Crypto":
            yf_sym = selected_pair.replace("/","-")
        else:
            yf_sym = selected_pair.replace("/","") + "=X"

        if generate_btn:
            with st.spinner("Generating AI forecast with Theory + Indicators + MTF + News..."):
                chart, provider, trade_data = generate_dashboard_forecast(selected_market, selected_pair, selected_tf, user_info)
                if chart and trade_data:
                    st.session_state.dashboard_forecast = chart
                    st.session_state.dashboard_forecast_provider = provider
                    st.session_state.dashboard_forecast_data = trade_data
                else:
                    st.error(f"Failed to generate forecast: {provider}")

        if st.session_state.get("dashboard_forecast") is not None:
            st.plotly_chart(st.session_state.dashboard_forecast, use_container_width=True)
            data = st.session_state.get("dashboard_forecast_data")
            st.caption(f"🤖 AI Provider: {st.session_state.dashboard_forecast_provider}")
            if data:
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                with col_s1:
                    score_color = "score-high" if data.get('conf', 0) >= 70 else ("score-medium" if data.get('conf', 0) >= 50 else "score-low")
                    st.markdown(f"<div class='score-box {score_color}'><b>Combined</b><br>{data.get('conf', 'N/A')}%</div>", unsafe_allow_html=True)
                with col_s2:
                    st.markdown(f"<div class='score-box'><b>Engine</b><br>{data.get('engine_conf', 'N/A')}%</div>", unsafe_allow_html=True)
                with col_s3:
                    st.markdown(f"<div class='score-box'><b>AI News</b><br>{data.get('ai_conf', 'N/A')}%</div>", unsafe_allow_html=True)
                with col_s4:
                    mtf_col = "score-high" if data.get('mtf_score', 0) >= 70 else ("score-medium" if data.get('mtf_score', 0) >= 50 else "score-low")
                    st.markdown(f"<div class='score-box {mtf_col}'><b>MTF</b><br>{data.get('mtf_score', 'N/A')}%</div>", unsafe_allow_html=True)
                if not st.session_state.beginner_mode and data.get('mtf_details'):
                    with st.expander("📊 Multi-Timeframe Details"):
                        for tf_key, tf_data in data['mtf_details'].items():
                            dir_sym = "🟢 BUY" if tf_data['direction'] == "bull" else ("🔴 SELL" if tf_data['direction'] == "bear" else "⚪ NEUTRAL")
                            cls = "mtf-bull" if tf_data['direction'] == "bull" else ("mtf-bear" if tf_data['direction'] == "bear" else "mtf-neutral")
                            st.markdown(f"<div class='mtf-box {cls}'><b>{tf_key}:</b> {dir_sym} | Conf: {tf_data['confidence']}% | {tf_data['trend']}</div>", unsafe_allow_html=True)
                st.markdown(f"**R:R Ratio:** 1:{data.get('rr_ratio', 'N/A')} | **Entry Source:** {data.get('entry_source', 'N/A')}")
                live = get_live_price(data['pair'])
                if live:
                    tp3_v = data.get('tp3', data.get('tp1', data['entry']))
                    if data['dir'] == "BUY": progress = (live - data['entry']) / (tp3_v - data['entry']) if tp3_v != data['entry'] else 0
                    else: progress = (data['entry'] - live) / (data['entry'] - tp3_v) if tp3_v != data['entry'] else 0
                    progress = max(0, min(1, progress))
                    st.progress(progress, text="Progress to Final Target")
                st.markdown(f"**Sinhala Summary:** {data.get('sinhala_summary', 'N/A')}")

        if not st.session_state.beginner_mode:
            if 'tech_btn' in locals() and tech_btn:
                with st.spinner("Generating technical analysis chart..."):
                    period = get_period_for_tf(selected_tf)
                    df_tech = get_cached_historical_data(yf_sym, selected_tf, period=period)
                    if df_tech is not None and len(df_tech) > 50:
                        st.session_state.tech_chart = create_technical_chart(df_tech, selected_tf)
                    else: st.error("Insufficient data for technical chart.")
            if st.session_state.get("tech_chart") is not None:
                st.plotly_chart(st.session_state.tech_chart, use_container_width=True)
            if 'theory_btn' in locals() and theory_btn:
                with st.spinner("Generating theory chart (SMC, ICT, Fibonacci, Elliott)..."):
                    period = get_period_for_tf(selected_tf)
                    df_theory = get_cached_historical_data(yf_sym, selected_tf, period=period)
                    if df_theory is not None and len(df_theory) > 50:
                        st.session_state.theory_chart = create_theory_chart(df_theory, selected_tf)
                    else: st.error("Insufficient data for theory chart.")
            if st.session_state.get("theory_chart") is not None:
                st.plotly_chart(st.session_state.theory_chart, use_container_width=True)

        st.markdown("### 📰 Market News & AI Impact Analysis (Sinhala)")
        if st.button(f"🔍 Analyze Impact for {selected_pair}"):
            with st.spinner(f"Fetching news and analyzing impact on {selected_pair}..."):
                news_items = get_market_news(yf_sym)
                impact_result, provider = analyze_news_impact(news_items, selected_pair, user_info)
                st.session_state.news_impact_analysis = impact_result
                st.session_state.news_impact_provider = provider
        if st.session_state.get("news_impact_analysis"):
            st.subheader("🔍 AI Impact Analysis")
            st.caption(f"Provider: {st.session_state.news_impact_provider}")
            st.markdown(f"<div class='entry-box'>{st.session_state.news_impact_analysis}</div>", unsafe_allow_html=True)

        st.markdown("### 🔔 Trade Notifications — Theory-Based Signals")
        if st.session_state.scan_results:
            trades_by_tf = {}
            for t in st.session_state.scan_results:
                tf = t.get('timeframe', 'Unknown')
                if tf not in trades_by_tf: trades_by_tf[tf] = []
                trades_by_tf[tf].append(t)
            for tf, trades in trades_by_tf.items():
                trades_sorted = sorted(trades, key=lambda x: x.get('conf', 0), reverse=True)
                st.markdown(f"<div style='color:#00ff99;font-weight:bold;margin:8px 0 4px;'>⏰ {tf} Timeframe — {len(trades_sorted)} Signal(s)</div>", unsafe_allow_html=True)
                for t in trades_sorted[:3]:
                    dir_color = "#00ff00" if t['dir'] == "BUY" else "#ff4b4b"
                    notif_cls = "notif-buy" if t['dir'] == "BUY" else "notif-sell"
                    trade_type_v = t.get('trade_type', 'SHORT')
                    tt_color = "#00aaff" if trade_type_v == "SWING" else "#ffaa00"
                    ew_lbl = t.get('ew_label', '')
                    ict_ctx = t.get('ict_context', '')
                    ew_conf = t.get('ew_ict_conf', 0)
                    entry_src = t.get('entry_source', '')

                    # MTF summary for notification
                    mtf_det = t.get('mtf_details', {})
                    mtf_html = ""
                    for mtf_tf, mtf_d in mtf_det.items():
                        ic = "🟢" if mtf_d['direction'] == "bull" else ("🔴" if mtf_d['direction'] == "bear" else "⚪")
                        mtf_html += f"<span style='font-size:11px;margin-right:8px;'>{ic} {mtf_tf}: {mtf_d['direction'].upper()} ({mtf_d['confidence']:.0f}%)</span>"

                    # News info
                    news_smr = t.get('sinhala_summary', '')
                    ai_fcast = t.get('ai_forecast', t.get('forecast', ''))

                    # Risk badge
                    risk_lvl_d, risk_rsn_d, risk_cls_d = assess_trade_risk(t)
                    risk_icon_d = "🛡️" if risk_lvl_d == "SAFE" else ("⚠️" if risk_lvl_d == "MODERATE" else "🚨")
                    risk_badge_d = f"<span class='{risk_cls_d}' style='margin-left:8px;'>{risk_icon_d} {risk_lvl_d}</span>"

                    st.markdown(f"""<div class='notif-container {notif_cls}' style='border-radius:12px;'>
                        <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>
                            <span style='font-size:20px;font-weight:bold;color:{dir_color};'>{'📈' if t['dir']=='BUY' else '📉'} {t['pair']} — {t['dir']}{risk_badge_d}</span>
                            <span style='background:{tt_color}22;color:{tt_color};border:1px solid {tt_color};border-radius:6px;padding:2px 10px;font-size:13px;font-weight:bold;'>⚡ {trade_type_v} TRADE</span>
                        </div>
                        <div style='color:#fff;font-size:14px;margin-bottom:6px;'>
                            📊 <b>Theory:</b> {ew_lbl} | EW+ICT Conf: {ew_conf}%<br>
                            <span style='color:#aaa;font-size:12px;'>{ict_ctx}</span>
                        </div>
                        <div style='background:rgba(0,0,0,0.3);padding:8px 12px;border-radius:8px;margin-bottom:6px;font-size:13px;'>
                            <span style='color:#ffff00;'>Entry:</span> <b>{t['entry']:.5f}</b> &nbsp;|&nbsp;
                            <span style='color:#ff6666;'>SL:</span> <b>{t['sl']:.5f}</b> &nbsp;|&nbsp;
                            <span style='color:#66ff66;'>TP1:</span> <b>{t.get('tp1',0):.5f}</b> &nbsp;|&nbsp;
                            <span style='color:#44cc44;'>TP2:</span> <b>{t.get('tp2',0):.5f}</b> &nbsp;|&nbsp;
                            <span style='color:#228822;'>TP3:</span> <b>{t.get('tp3',0):.5f}</b><br>
                            <span style='color:#aaa;font-size:11px;'>Entry Source: {entry_src} | R:R 1:{t.get('rr_ratio','N/A')} | Combined Conf: {t['conf']}%</span>
                        </div>
                        <div style='margin-bottom:4px;'>{mtf_html}</div>
                        {"<div style='color:#ffcc44;font-size:12px;background:rgba(255,200,0,0.1);padding:6px 10px;border-radius:6px;border-left:3px solid #ffcc44;margin-top:4px;'>📰 AI News Analysis: " + ai_fcast[:120] + "...</div>" if ai_fcast else ""}
                        {"<div style='color:#00ff99;font-size:11px;margin-top:4px;'>🇱🇰 " + news_smr + "</div>" if news_smr else ""}
                        {"<div style='color:#ff8888;font-size:11px;margin-top:4px;'>⚠️ Risk Flags: " + risk_rsn_d + "</div>" if risk_lvl_d != "SAFE" else ""}
                    </div>""", unsafe_allow_html=True)
        else:
            st.info("No recent scans. Run Market Scanner to see signals.")

    elif app_mode == "Market Scanner":
        st.title("📡 Theory-Based Market Scanner (EW + ICT + SMC + Fibonacci)")
        st.markdown("<div class='scan-header'><h3>🔍 Elliott Wave + ICT (Swing) | SMC + Fibonacci (Short) — Multi-Timeframe Analysis</h3></div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            market_choice = st.selectbox("Market", options=["All","Forex","Crypto","Metals"], index=0, key="market_selector")
        with col2:
            available_timeframes = ["1m","5m","15m","1h","4h","1d","1wk"]
            default_timeframes = ["4h","15m"]
            selected_timeframes = st.multiselect("Timeframes", options=available_timeframes, default=default_timeframes)
        if market_choice == "All": scan_assets = assets["Forex"] + assets["Crypto"] + assets["Metals"]
        else: scan_assets = assets[market_choice]
        st.info(f"Selected markets: **{market_choice}** ({len(scan_assets)} assets) | Timeframes: {', '.join(selected_timeframes)}")
        min_acc = st.slider("Minimum Accuracy (%)", min_value=0, max_value=100, value=st.session_state.min_accuracy, step=5)
        st.session_state.min_accuracy = min_acc

        # Show/hide rejected trades toggle
        show_rejected = st.checkbox("👁️ Show Rejected Trades (with reasons)", value=True, help="Show trades that were rejected by the accuracy gates, with the reason why.")

        col1, col2 = st.columns([1,5])
        with col1:
            if st.button("🚀 Start AI Scan", type="primary", use_container_width=True):
                if not selected_timeframes:
                    st.warning("Please select at least one timeframe.")
                else:
                    with st.spinner(f"AI Scanning {market_choice} on {len(selected_timeframes)} timeframe(s)..."):
                        results, rejected = scan_market_with_ai(scan_assets, user_info, selected_timeframes, min_accuracy=min_acc)
                        st.session_state.scan_results = results
                        st.session_state.rejected_trades = rejected
                        if not results and not rejected:
                            st.warning(f"No signals found above {min_acc}% accuracy.")
                        else:
                            approved_count = len(results)
                            rejected_count = len(rejected)
                            st.success(f"Scan Complete! ✅ {approved_count} approved | ❌ {rejected_count} rejected across {len(selected_timeframes)} timeframe(s).")
        with col2:
            if st.button("🗑️ Clear Results", use_container_width=True):
                st.session_state.scan_results = []; st.session_state.rejected_trades = []; st.rerun()

        st.markdown("---")

        # ==================== APPROVED TRADES DISPLAY ====================
        res = st.session_state.scan_results
        current_session = get_current_session()

        # ── Summary Banner ─────────────────────────────────────────────────
        if res or st.session_state.rejected_trades:
            capturable_all   = [s for s in res if s.get('conf', 0) >= min_acc]
            uncapturable_all = [s for s in res if s.get('conf', 0) < min_acc]
            st.markdown(f"""<div style='background:linear-gradient(135deg,#0a1f2e,#1e3c3f);border:1px solid #00ff99;border-radius:12px;padding:12px 20px;margin-bottom:16px;display:flex;gap:24px;align-items:center;flex-wrap:wrap;'>
                <div style='text-align:center;'><div style='color:#aaa;font-size:11px;'>TOTAL APPROVED</div><div style='color:#fff;font-size:20px;font-weight:bold;'>{len(res)}</div></div>
                <div style='text-align:center;'><div style='color:#aaa;font-size:11px;'>✅ CAPTURABLE (≥{min_acc}%)</div><div style='color:#00ff00;font-size:20px;font-weight:bold;'>{len(capturable_all)}</div></div>
                <div style='text-align:center;'><div style='color:#aaa;font-size:11px;'>⚠️ BELOW THRESHOLD</div><div style='color:#ffaa00;font-size:20px;font-weight:bold;'>{len(uncapturable_all)}</div></div>
                <div style='text-align:center;'><div style='color:#aaa;font-size:11px;'>❌ GATE REJECTED</div><div style='color:#ff4b4b;font-size:20px;font-weight:bold;'>{len(st.session_state.rejected_trades)}</div></div>
                <div style='text-align:center;'><div style='color:#aaa;font-size:11px;'>MIN ACCURACY</div><div style='color:#ffaa00;font-size:20px;font-weight:bold;'>{min_acc}%</div></div>
            </div>""", unsafe_allow_html=True)

        if res:
            capturable_trades   = [s for s in res if s.get('conf', 0) >= min_acc]
            uncapturable_trades = [s for s in res if s.get('conf', 0) < min_acc]

            # ══════════════════════════════════════════════════════════════
            # SECTION A — CAPTURABLE (conf >= min_acc)
            # ══════════════════════════════════════════════════════════════
            if capturable_trades:
                st.markdown(f"""<div style='background:linear-gradient(135deg,#0a2010,#0d3020);border:1px solid #00ff99;border-left:5px solid #00ff00;border-radius:10px;padding:10px 16px;margin-bottom:12px;'>
                    <b style='color:#00ff00;font-size:15px;'>✅ CAPTURABLE TRADES — Confidence ≥ {min_acc}%</b>
                    <span style='color:#aaa;font-size:12px;'> — Passed all gates AND meet your minimum accuracy. Safe to trade.</span>
                </div>""", unsafe_allow_html=True)

                cap_by_tf = {}
                for sig in capturable_trades:
                    tf = sig.get('timeframe', 'Unknown')
                    if tf not in cap_by_tf: cap_by_tf[tf] = []
                    cap_by_tf[tf].append(sig)

                for tf, trades in cap_by_tf.items():
                    trades_sorted = sorted(trades, key=lambda x: x.get('conf', 0), reverse=True)
                    with st.expander(f"✅ {tf} — CAPTURABLE ({len(trades_sorted)} trades)", expanded=True):
                        for idx, sig in enumerate(trades_sorted):
                            max_diff = abs(sig['entry'] - sig['sl'])
                            if max_diff > 0: progress = 1 - (abs(sig['live_price'] - sig['entry']) / max_diff)
                            else: progress = 0
                            progress = max(0, min(1, progress))
                            conf_badge = f"<span class='ai-badge ai-approve'>✅ {sig['confirmation']}</span>"
                            conf_val = sig.get('conf', 0)
                            cap_badge = f"<span style='background:#00ff0022;color:#00ff00;border:1px solid #00ff00;border-radius:6px;padding:1px 8px;font-size:11px;font-weight:bold;margin-left:6px;'>✅ {conf_val}% CAPTURABLE</span>"
                            theory = sig.get('theory_signals', {})
                            theory_badges = ""
                            for th, val in theory.items():
                                if th in ['SMC','ICT','FIB','ELLIOTT','STOCH','CCI','VOL','ADX']:
                                    cls = "theory-bull" if val == "bull" else ("theory-bear" if val == "bear" else "theory-neutral")
                                    theory_badges += f"<span class='theory-badge {cls}'>{th}</span> "
                            mtf_agrees = sig.get('mtf_agrees', True)
                            mtf_icon = "✅ MTF OK" if mtf_agrees else "⚠️ MTF Conflict"
                            regime_icon = {"trending":"📈 Trending","ranging":"↔️ Ranging","transitioning":"🔄 Transitioning"}.get(sig.get('regime',''),'')
                            col1, col2, col3, col4 = st.columns([3,1,1,2])
                            with col1:
                                color = "#00ff00" if sig['dir'] == "BUY" else "#ff4b4b"
                                session_tag = f"<span style='color:#00ff99; font-size:0.9em;'> [{current_session}]</span>"
                                # Trade type badge
                                trade_type_val = sig.get('trade_type', 'SHORT')
                                tt_color = "#00aaff" if trade_type_val == "SWING" else "#ffaa00"
                                tt_badge = f"<span style='background:{tt_color}22;color:{tt_color};border:1px solid {tt_color};border-radius:6px;padding:1px 8px;font-size:11px;font-weight:bold;margin-left:4px;'>⚡ {trade_type_val}</span>"
                                # EW + ICT info
                                ew_label_val = sig.get('ew_label', '')
                                ict_ctx = sig.get('ict_context', '')
                                ew_ict_c = sig.get('ew_ict_conf', 0)
                                theory_line = ""
                                if ew_label_val:
                                    ew_color = "#00ff99" if "BUY" in sig['dir'] or "Wave 3" in ew_label_val or "Wave B" in ew_label_val else "#ff8888"
                                    theory_line = f"<div style='color:{ew_color};font-size:11px;margin-top:3px;'>📊 {ew_label_val} | {ict_ctx} (EW+ICT: {ew_ict_c}%)</div>"
                                # Risk badge
                                risk_lvl, risk_reason, risk_cls = assess_trade_risk(sig)
                                risk_icon = "🛡️" if risk_lvl == "SAFE" else ("⚠️" if risk_lvl == "MODERATE" else "🚨")
                                risk_badge_html = f"<span class='{risk_cls}'>{risk_icon} {risk_lvl}</span>"
                                if risk_lvl in ("MODERATE", "DANGEROUS"):
                                    risk_detail = f"<div style='color:#ffaa44;font-size:11px;margin-top:2px;'>⚠️ Risk: {risk_reason}</div>"
                                else:
                                    risk_detail = ""
                                st.markdown(f"""<div style='background:#0d2a1a; padding:10px; border-radius:8px; border-left:5px solid {color}; margin-bottom:10px;'>
                                    <b>{sig['pair']} | {sig['dir']}{session_tag}</b> {conf_badge} {cap_badge} {tt_badge} {risk_badge_html}<br>
                                    Entry: {sig['entry']:.5f} | SL: {sig['sl']:.5f}<br>
                                    TP1: {sig.get('tp1',0):.5f} | TP2: {sig.get('tp2',0):.5f} | TP3: {sig.get('tp3',0):.5f}<br>
                                    Live: {sig['live_price']:.5f}<br>
                                    <b>Combined: {sig['conf']}% | Engine: {sig.get('engine_conf','N/A')}% | AI News: {sig.get('ai_conf','N/A')}% | MTF: {sig.get('mtf_score','N/A')}% | Quality: {sig.get('quality_score','N/A')}%</b><br>
                                    <b>Confluence: {sig.get('confluence_pct','N/A')}% | R:R = 1:{sig.get('rr_ratio','N/A')} | {mtf_icon} | {regime_icon} ADX:{sig.get('adx_strength','N/A')}</b><br>
                                    <small>Entry Source: {sig.get('entry_source','N/A')} | Provider: {sig.get('provider','AI')}</small><br>
                                    <small>🇱🇰 {sig.get('sinhala_summary','')}</small><br>
                                    {theory_badges}{theory_line}{risk_detail}
                                </div>""", unsafe_allow_html=True)
                            with col2:
                                st.progress(progress, text="Approach")
                            with col3:
                                # --- Capture Trade Button ---
                                trade_id = f"{sig['pair']}_{sig.get('timeframe', tf)}_{sig['dir']}_{sig['entry']:.5f}"
                                already_captured = trade_id in st.session_state.tracked_trades
                                if already_captured:
                                    st.markdown("<div style='color:#00ff99;font-size:12px;text-align:center;padding:6px;'>✅ Captured</div>", unsafe_allow_html=True)
                                else:
                                    if st.button("💾 Capture", key=f"capture_cap_{tf}_{idx}", use_container_width=True, type="primary"):
                                        capture_dict = {
                                            "pair": sig['pair'],
                                            "dir":  sig['dir'],
                                            "entry": sig['entry'],
                                            "sl":    sig['sl'],
                                            "tp":    sig.get('tp1', sig['entry']),
                                            "tp1":   sig.get('tp1', sig['entry']),
                                            "tp2":   sig.get('tp2', sig['entry']),
                                            "tp3":   sig.get('tp3', sig['entry']),
                                            "conf":  sig.get('conf', 0),
                                        }
                                        forecast_text = sig.get('forecast', sig.get('sinhala_summary', 'Captured from scanner'))
                                        if save_trade_to_ongoing(capture_dict, user_info['Username'], sig.get('timeframe', tf), forecast_text):
                                            st.session_state.tracked_trades.add(trade_id)
                                            st.success(f"✅ {sig['pair']} captured!")
                                            st.rerun()
                                        else:
                                            st.error("❌ Capture failed. Check Google Sheets connection.")
                                if not st.session_state.beginner_mode:
                                    if st.button("🔍 Deep", key=f"deep_cap_{tf}_{idx}", use_container_width=True):
                                        st.session_state.selected_trade = sig
                                        st.session_state.deep_analysis_result = None
                                        st.session_state.deep_analysis_provider = None
                                        st.session_state.deep_forecast_chart = None
                                        st.session_state.deep_confirmation = None
                                        st.session_state.deep_reason = None
                                        st.rerun()
                            with col4:
                                try:
                                    symbol_orig = sig.get('symbol_orig', sig['pair'])
                                    period = get_period_for_tf(tf)
                                    df_hist = get_cached_historical_data(get_yf_symbol(symbol_orig), tf, period=period)
                                    if df_hist is not None:
                                        tp1_v = sig.get('tp1', sig.get('tp', sig['entry']))
                                        tp2_v = sig.get('tp2', tp1_v); tp3_v = sig.get('tp3', tp2_v)
                                        mini_chart = create_mini_chart(df_hist, sig['entry'], sig['sl'], tp1_v, tp2_v, tp3_v)
                                        st.plotly_chart(mini_chart, use_container_width=True)
                                except: st.write("Chart N/A")
            else:
                st.info(f"No approved signals meet the minimum accuracy of {min_acc}%. Try lowering the slider or running a new scan.")

            # ══════════════════════════════════════════════════════════════
            # SECTION B — CANNOT CAPTURE (passed gates but conf < min_acc)
            # ══════════════════════════════════════════════════════════════
            if uncapturable_trades:
                st.markdown("---")
                with st.expander(f"⚠️ CANNOT CAPTURE — Below {min_acc}% Threshold ({len(uncapturable_trades)} signals)", expanded=False):
                    st.markdown(f"""<div style='background:#1a1200;border:1px solid #ffaa0055;border-left:5px solid #ffaa00;border-radius:10px;padding:10px 16px;margin-bottom:12px;'>
                        <b style='color:#ffaa00;font-size:14px;'>⚠️ These signals PASSED all 6 accuracy gates but their confidence is below your {min_acc}% minimum</b><br>
                        <span style='color:#aaa;font-size:12px;'>Technically valid setups — below your risk threshold. Each trade shows exact reasons why it cannot be captured.</span>
                    </div>""", unsafe_allow_html=True)

                    unc_by_tf = {}
                    for sig in uncapturable_trades:
                        tf = sig.get('timeframe', 'Unknown')
                        if tf not in unc_by_tf: unc_by_tf[tf] = []
                        unc_by_tf[tf].append(sig)

                    for tf, trades in unc_by_tf.items():
                        trades_sorted = sorted(trades, key=lambda x: x.get('conf', 0), reverse=True)
                        st.markdown(f"<div style='color:#ffaa00;font-weight:bold;margin:10px 0 6px;'>📌 {tf} Timeframe — {len(trades_sorted)} signal(s)</div>", unsafe_allow_html=True)
                        for sig in trades_sorted:
                            dir_color = "#00ff00" if sig['dir'] == "BUY" else "#ff4b4b"
                            conf_val  = sig.get('conf', 0)
                            engine    = sig.get('engine_conf', 0)
                            ai_c      = sig.get('ai_conf', 0)
                            mtf_s     = sig.get('mtf_score', 0)
                            gap       = min_acc - conf_val

                            reasons = []
                            reasons.append(f"Confidence {conf_val}% is {gap}% below your minimum accuracy of {min_acc}%")
                            if conf_val < 30:
                                reasons.append("Very low combined confidence — technical indicators are weakly aligned")
                            elif conf_val < 45:
                                reasons.append("Low confidence — signals present but not strongly confluent")
                            else:
                                reasons.append(f"Moderate confidence — consider lowering the slider to {conf_val}% to include this trade")
                            if engine < 40:
                                reasons.append(f"Engine score too low ({engine}%) — technical indicators lack clear direction")
                            if ai_c < 40:
                                reasons.append(f"AI News confidence low ({ai_c}%) — news/sentiment not supporting this direction")
                            if mtf_s < 40:
                                reasons.append(f"Multi-timeframe score weak ({mtf_s}%) — higher timeframes disagree with this setup")
                            if not sig.get('mtf_agrees', True):
                                reasons.append("MTF Conflict — higher timeframe direction opposes this trade")
                            if sig.get('regime') == 'ranging':
                                reasons.append("Market is in ranging mode — trend signals are less reliable in sideways conditions")
                            if sig.get('rr_ratio', 0) < 1.5:
                                reasons.append(f"Low R:R ratio (1:{sig.get('rr_ratio','N/A')}) — risk/reward not favourable enough")

                            reason_html = "".join([f"<li style='color:#ffbb66;margin-bottom:3px;'>⚠️ {r}</li>" for r in reasons])
                            mtf_icon = "✅ MTF OK" if sig.get('mtf_agrees', True) else "⚠️ MTF Conflict"
                            regime_icon = {"trending":"📈 Trending","ranging":"↔️ Ranging","transitioning":"🔄 Transitioning"}.get(sig.get('regime',''),'')

                            unc_col1, unc_col2 = st.columns([5, 1])
                            with unc_col1:
                                st.markdown(f"""<div style='background:#1a1200;border:1px solid #ffaa0033;border-left:4px solid #ffaa00;border-radius:8px;padding:12px 16px;margin-bottom:4px;'>
                                    <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>
                                        <b style='color:{dir_color};font-size:14px;'>{sig['pair']} | {sig['dir']}</b>
                                        <span style='background:#ffaa0022;color:#ffaa00;border:1px solid #ffaa00;border-radius:8px;padding:2px 10px;font-size:12px;font-weight:bold;'>⚠️ CANNOT CAPTURE — {conf_val}%</span>
                                    </div>
                                    <div style='color:#aaa;font-size:12px;margin-bottom:6px;'>
                                        <span style='color:#00ff99;'>Entry:</span> <b>{sig['entry']:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#ff6666;'>SL:</span> <b>{sig['sl']:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP1:</span> <b>{sig.get('tp1',0):.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP2:</span> <b>{sig.get('tp2',0):.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP3:</span> <b>{sig.get('tp3',0):.5f}</b>
                                    </div>
                                    <div style='color:#888;font-size:12px;margin-bottom:6px;'>
                                        Live: {sig['live_price']:.5f} | Engine: {engine}% | AI: {ai_c}% | MTF: {mtf_s}% | {mtf_icon} | {regime_icon} | R:R 1:{sig.get('rr_ratio','N/A')}
                                    </div>
                                    <div style='background:#0d0900;border-radius:6px;padding:8px 12px;'>
                                        <b style='color:#ffaa00;font-size:12px;'>❌ Reasons this trade CANNOT be captured:</b>
                                        <ul style='margin:6px 0 0 0;padding-left:16px;'>{reason_html}</ul>
                                    </div>
                                </div>""", unsafe_allow_html=True)
                            with unc_col2:
                                unc_trade_id = f"unc_{sig['pair']}_{sig.get('timeframe','')}"
                                if st.button("💾 Save", key=f"save_unc_{unc_trade_id}_{conf_val}", help="Manually save to Ongoing Trades", use_container_width=True):
                                    save_dict = {
                                        "pair": sig['pair'], "dir": sig['dir'],
                                        "entry": sig['entry'], "sl": sig['sl'],
                                        "tp": sig.get('tp1', sig.get('tp', sig['entry'])),
                                        "tp1": sig.get('tp1', sig['entry']),
                                        "tp2": sig.get('tp2', sig['entry']),
                                        "tp3": sig.get('tp3', sig['entry']),
                                        "conf": sig.get('conf', conf_val),
                                    }
                                    if save_trade_to_ongoing(save_dict, user_info['Username'], sig.get('timeframe', tf), sig.get('forecast', f'⚠️ Below threshold ({conf_val}%)')):
                                        st.success(f"✅ {sig['pair']} saved to Ongoing!")
                                    else:
                                        st.error("Save failed.")
        else:
            if st.session_state.scan_results == [] and not st.session_state.rejected_trades:
                st.info("No scan results. Run a scan to see setups.")
            else:
                st.warning("⚠️ No trades passed all 6 accuracy gates. Check rejected trades below for details.")

        # ==================== REJECTED TRADES DISPLAY ====================
        rejected = st.session_state.rejected_trades
        if rejected and show_rejected:
            st.markdown("---")

            # Split: near-miss (engine_conf >= 40%) vs fully rejected
            near_miss = [rt for rt in rejected if rt.get('engine_conf', 0) >= 40]
            fully_rejected = [rt for rt in rejected if rt.get('engine_conf', 0) < 40]

            # ── NEAR-MISS SECTION (40%+ score but failed a gate) ──────────
            if near_miss:
                st.markdown("""<div style='background:linear-gradient(135deg,#1a1500,#2a2000);border:1px solid #ffaa00;border-left:5px solid #ffaa00;border-radius:10px;padding:12px 16px;margin-bottom:12px;'>
                    <b style='color:#ffaa00;font-size:15px;'>⚡ NEAR-MISS SETUPS</b>
                    <span style='color:#aaa;font-size:12px;'> — Engine score ≥ 40% but failed a quality gate. Watch these pairs.</span>
                </div>""", unsafe_allow_html=True)

                # Group near-miss by timeframe
                nm_by_tf = {}
                for rt in near_miss:
                    tf = rt.get('tf','Unknown')
                    if tf not in nm_by_tf: nm_by_tf[tf] = []
                    nm_by_tf[tf].append(rt)

                for tf, nm_trades in nm_by_tf.items():
                    # Sort by engine_conf descending so strongest near-misses show first
                    nm_trades_sorted = sorted(nm_trades, key=lambda x: x.get('engine_conf',0), reverse=True)
                    with st.expander(f"⚡ {tf} — Near-Miss Setups ({len(nm_trades_sorted)} pairs)", expanded=True):
                        for rt in nm_trades_sorted:
                            dir_color = "#00ff00" if rt['dir'] == "BUY" else "#ff4b4b"
                            engine_conf = rt.get('engine_conf', 0)
                            conf_pct = rt.get('confluence_pct', 'N/A')
                            quality = rt.get('quality_sc', 'N/A')
                            gate_label = rt.get('failed_gate', 'Unknown')
                            reason = rt.get('reject_reason', 'Unknown')
                            combined_conf = rt.get('combined_conf', 'N/A')
                            # Colour-code score bar
                            bar_color = "#ffcc00" if engine_conf >= 60 else "#ff9900"
                            score_bar = int(engine_conf / 100 * 20)
                            score_visual = "█" * score_bar + "░" * (20 - score_bar)
                            nm_col1, nm_col2 = st.columns([5, 1])
                            with nm_col1:
                                nm_entry = rt.get('entry', rt['price'])
                                nm_sl    = rt.get('sl', rt['price'])
                                nm_tp1   = rt.get('tp1', rt['price'])
                                nm_tp2   = rt.get('tp2', rt['price'])
                                nm_tp3   = rt.get('tp3', rt['price'])
                                st.markdown(f"""<div style='background:#1a1500;border:1px solid #ffaa0055;border-left:4px solid #ffaa00;border-radius:8px;padding:10px 14px;margin-bottom:4px;'>
                                    <div style='display:flex;justify-content:space-between;align-items:center;'>
                                        <b style='color:{dir_color};font-size:14px;'>{rt['pair']} | {rt['dir']}</b>
                                        <span style='color:#ffaa00;font-size:13px;font-weight:bold;'>Engine: {engine_conf:.0f}%</span>
                                    </div>
                                    <div style='color:{bar_color};font-size:11px;letter-spacing:0;margin:3px 0;'>{score_visual}</div>
                                    <div style='color:#aaa;font-size:12px;margin:4px 0;'>
                                        <span style='color:#00ff99;'>Entry:</span> <b>{nm_entry:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#ff6666;'>SL:</span> <b>{nm_sl:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP1:</span> <b>{nm_tp1:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP2:</span> <b>{nm_tp2:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP3:</span> <b>{nm_tp3:.5f}</b>
                                    </div>
                                    <div style='margin-top:2px;'>
                                        <span style='background:#33200a;color:#ffaa00;border:1px solid #ffaa0066;border-radius:4px;padding:1px 6px;font-size:11px;'>{gate_label} FAILED</span>
                                    </div>
                                    <div style='color:#ff9966;font-size:12px;margin-top:3px;'>⚠️ {reason}</div>
                                    <div style='color:#666;font-size:11px;margin-top:3px;'>Price: {rt['price']:.5f} | Confluence: {conf_pct}% | Quality: {quality}%{f" | Combined: {combined_conf}%" if combined_conf != "N/A" else ""}</div>
                                </div>""", unsafe_allow_html=True)
                            with nm_col2:
                                nm_id = f"nm_{rt['pair']}_{rt.get('tf','')}"
                                if st.button("💾 Save", key=f"save_nm_{nm_id}_{engine_conf:.0f}", help="Manually save to Ongoing Trades", use_container_width=True):
                                    save_dict = {
                                        "pair": rt['pair'], "dir": rt['dir'],
                                        "entry": rt.get('entry', rt['price']),
                                        "sl":    rt.get('sl', rt['price']),
                                        "tp":    rt.get('tp1', rt['price']),
                                        "tp1":   rt.get('tp1', rt['price']),
                                        "tp2":   rt.get('tp2', rt['price']),
                                        "tp3":   rt.get('tp3', rt['price']),
                                        "conf":  rt.get('conf', round(engine_conf)),
                                    }
                                    if save_trade_to_ongoing(save_dict, user_info['Username'], rt.get('tf', 'N/A'), f'⚡ Near-Miss — {gate_label} failed: {reason}'):
                                        st.success(f"✅ {rt['pair']} saved to Ongoing!")
                                    else:
                                        st.error("Save failed.")

            # ── FULLY REJECTED SECTION (<40% score) ───────────────────────
            if fully_rejected:
                # Group by timeframe
                rejected_by_tf = {}
                for rt in fully_rejected:
                    tf = rt.get('tf','Unknown')
                    if tf not in rejected_by_tf: rejected_by_tf[tf] = []
                    rejected_by_tf[tf].append(rt)

                for tf, r_trades in rejected_by_tf.items():
                    with st.expander(f"❌ {tf} Timeframe — Rejected ({len(r_trades)} weak signals)", expanded=False):
                        gate_counts = {}
                        for rt in r_trades:
                            gate = rt.get('failed_gate','Unknown')
                            gate_counts[gate] = gate_counts.get(gate,0) + 1
                        gate_summary = " | ".join([f"<span class='gate-fail-badge'>{g}: {c}</span>" for g,c in gate_counts.items()])
                        st.markdown(f"**Failure breakdown:** {gate_summary}", unsafe_allow_html=True)
                        st.markdown("")
                        for rt in r_trades:
                            dir_color = "#00ff00" if rt['dir'] == "BUY" else "#ff4b4b"
                            gate_label = rt.get('failed_gate','Unknown')
                            reason = rt.get('reject_reason','Unknown reason')
                            engine_conf = rt.get('engine_conf','N/A')
                            conf_pct = rt.get('confluence_pct','N/A')
                            quality = rt.get('quality_sc','N/A')
                            combined_conf = rt.get('combined_conf','N/A')
                            rej_col1, rej_col2 = st.columns([5, 1])
                            with rej_col1:
                                rej_entry = rt.get('entry', rt['price'])
                                rej_sl    = rt.get('sl', rt['price'])
                                rej_tp1   = rt.get('tp1', rt['price'])
                                rej_tp2   = rt.get('tp2', rt['price'])
                                rej_tp3   = rt.get('tp3', rt['price'])
                                st.markdown(f"""<div class='rejected-card'>
                                    <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;'>
                                        <b style='color:{dir_color};'>{rt['pair']} | {rt['dir']}</b>
                                        <span class='rejected-badge'>❌ REJECTED</span>
                                    </div>
                                    <div style='color:#aaa;font-size:12px;margin:4px 0;'>
                                        <span style='color:#00ff99;'>Entry:</span> <b>{rej_entry:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#ff6666;'>SL:</span> <b>{rej_sl:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP1:</span> <b>{rej_tp1:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP2:</span> <b>{rej_tp2:.5f}</b> &nbsp;|&nbsp;
                                        <span style='color:#66ff66;'>TP3:</span> <b>{rej_tp3:.5f}</b>
                                    </div>
                                    <span class='gate-fail-badge'>{gate_label}</span>
                                    <span style='color:#ff8888;'> ⚠️ {reason}</span><br>
                                    <small style='color:#888;'>Price: {rt['price']:.5f} | Engine: {engine_conf}% | Confluence: {conf_pct}% | Quality: {quality}%{f" | Combined: {combined_conf}%" if combined_conf != "N/A" else ""}</small>
                                </div>""", unsafe_allow_html=True)
                            with rej_col2:
                                rej_id = f"rej_{rt['pair']}_{rt.get('tf','')}"
                                if st.button("💾 Save", key=f"save_rej_{rej_id}_{gate_label}", help="Manually save to Ongoing Trades despite rejection", use_container_width=True):
                                    save_dict = {
                                        "pair": rt['pair'], "dir": rt['dir'],
                                        "entry": rt.get('entry', rt['price']),
                                        "sl":    rt.get('sl', rt['price']),
                                        "tp":    rt.get('tp1', rt['price']),
                                        "tp1":   rt.get('tp1', rt['price']),
                                        "tp2":   rt.get('tp2', rt['price']),
                                        "tp3":   rt.get('tp3', rt['price']),
                                        "conf":  rt.get('conf', round(float(engine_conf)) if engine_conf != 'N/A' else 0),
                                    }
                                    if save_trade_to_ongoing(save_dict, user_info['Username'], rt.get('tf', 'N/A'), f'❌ Rejected — {gate_label}: {reason}'):
                                        st.success(f"✅ {rt['pair']} saved to Ongoing!")
                                    else:
                                        st.error("Save failed.")

        # ==================== DEEP ANALYSIS ====================
        if not st.session_state.beginner_mode and st.session_state.selected_trade:
            st.markdown("---")
            st.subheader(f"🔬 Deep Analysis: {st.session_state.selected_trade['pair']} ({st.session_state.selected_trade['tf']})")
            if st.session_state.deep_analysis_result is None:
                with st.spinner("Running deep analysis with AI (Theory + MTF + News)..."):
                    try:
                        symbol_orig = st.session_state.selected_trade.get('symbol_orig', st.session_state.selected_trade['pair'])
                        tf_part = st.session_state.selected_trade.get('timeframe', '1h')
                        period = get_period_for_tf(tf_part)
                        df_hist = get_cached_historical_data(get_yf_symbol(symbol_orig), tf_part, period=period)
                        if df_hist is None or len(df_hist) < 10: df_hist = None
                    except: df_hist = None
                    result, provider, confirmation, reason = get_deep_hybrid_analysis(st.session_state.selected_trade, st.session_state.user, df_hist)
                    st.session_state.deep_analysis_result = result
                    st.session_state.deep_analysis_provider = provider
                    st.session_state.deep_confirmation = confirmation
                    st.session_state.deep_reason = reason
                    parsed = parse_ai_response(result); forecast_text = parsed.get('FORECAST', '')
                    if df_hist is not None and not df_hist.empty:
                        trade_sel = st.session_state.selected_trade
                        tp1_v = trade_sel.get('tp1', trade_sel.get('tp', trade_sel['entry']))
                        tp2_v = trade_sel.get('tp2', tp1_v); tp3_v = trade_sel.get('tp3', tp2_v)
                        chart = create_forecast_chart(df_hist, trade_sel['entry'], trade_sel['sl'], tp1_v, tp2_v, tp3_v, forecast_text, trade_sel.get('sinhala_summary', ''))
                        st.session_state.deep_forecast_chart = chart
                    else:
                        st.warning("Not enough historical data for forecast chart.")
            trade = st.session_state.selected_trade
            col_d1, col_d2, col_d3, col_d4, col_d5 = st.columns(5)
            with col_d1: st.metric("Combined Conf", f"{trade.get('conf', 'N/A')}%")
            with col_d2: st.metric("Engine Conf", f"{trade.get('engine_conf', 'N/A')}%")
            with col_d3: st.metric("AI News", f"{trade.get('ai_conf', 'N/A')}%")
            with col_d4: st.metric("MTF Score", f"{trade.get('mtf_score', 'N/A')}%")
            with col_d5: st.metric("R:R Ratio", f"1:{trade.get('rr_ratio', 'N/A')}")
            if trade.get('mtf_details'):
                with st.expander("📊 Multi-Timeframe Details"):
                    for tf_key, tf_data in trade['mtf_details'].items():
                        dir_sym = "🟢 BUY" if tf_data['direction'] == "bull" else ("🔴 SELL" if tf_data['direction'] == "bear" else "⚪ NEUTRAL")
                        cls = "mtf-bull" if tf_data['direction'] == "bull" else ("mtf-bear" if tf_data['direction'] == "bear" else "mtf-neutral")
                        st.markdown(f"<div class='mtf-box {cls}'><b>{tf_key}:</b> {dir_sym} | Conf: {tf_data['confidence']}% | {tf_data['trend']}</div>", unsafe_allow_html=True)
            st.markdown(f"**🤖 Provider:** `{st.session_state.deep_analysis_provider}`")
            st.markdown(f"<div class='entry-box'>{st.session_state.deep_analysis_result}</div>", unsafe_allow_html=True)
            if st.session_state.get("deep_confirmation"):
                conf = st.session_state.deep_confirmation; reason = st.session_state.get("deep_reason", "")
                if conf == "APPROVE": st.markdown(f"<div class='confirm-card confirm-approve'><span class='confirm-icon'>✅</span> <b>AI CONFIRMATION: APPROVE</b><br>{reason}</div>", unsafe_allow_html=True)
                elif conf == "REJECT": st.markdown(f"<div class='confirm-card confirm-reject'><span class='confirm-icon'>❌</span> <b>AI CONFIRMATION: REJECT</b><br>{reason}</div>", unsafe_allow_html=True)
                else: st.markdown(f"<div class='confirm-card'><span class='confirm-icon'>🤔</span> <b>AI CONFIRMATION: {conf}</b><br>{reason}</div>", unsafe_allow_html=True)
            if st.session_state.deep_forecast_chart is not None:
                st.plotly_chart(st.session_state.deep_forecast_chart, use_container_width=True)
            else: st.info("Forecast chart could not be generated.")
            if st.button("Close Analysis"):
                st.session_state.selected_trade = None; st.session_state.deep_analysis_result = None
                st.session_state.deep_analysis_provider = None; st.session_state.deep_forecast_chart = None
                st.session_state.deep_confirmation = None; st.session_state.deep_reason = None; st.rerun()

    elif app_mode == "Ongoing Trades":
        st.title("📋 Ongoing Trades")

        # ── Filters row ────────────────────────────────────────────────────
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1: start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=7))
        with col_f2: end_date = st.date_input("End Date", value=datetime.now())
        with col_f3:
            ongoing_min_acc = st.slider(
                "Minimum Accuracy (%)",
                min_value=0, max_value=100,
                value=st.session_state.get("ongoing_min_acc", 40),
                step=5,
                key="ongoing_min_acc_slider",
                help="Trades with Confidence >= this value will be shown as capturable. Others will be shown with reasons why they cannot be captured."
            )
            st.session_state["ongoing_min_acc"] = ongoing_min_acc

        if active_trades:
            all_timeframes = sorted(set([t.get('Timeframe', 'Unknown') for t in active_trades]))
            timeframe_options = ["All"] + all_timeframes
            selected_tf_filter = st.selectbox("Filter by Timeframe", options=timeframe_options, index=0)
        else: selected_tf_filter = "All"

        tab1, tab2 = st.tabs(["🟢 Active Trades", "📜 History"])
        with tab1:
            if active_trades:
                filtered_trades = active_trades if selected_tf_filter == "All" else [t for t in active_trades if t.get('Timeframe', 'Unknown') == selected_tf_filter]

                # ── Split trades by minimum accuracy threshold ──────────────
                capturable = []
                not_capturable = []
                for t in filtered_trades:
                    try:
                        conf_val = float(str(t.get('Confidence', 0)).replace('%','').strip())
                    except:
                        conf_val = 0
                    if conf_val >= ongoing_min_acc:
                        capturable.append((t, conf_val))
                    else:
                        not_capturable.append((t, conf_val))

                # ── Summary banner ──────────────────────────────────────────
                total_ongoing = len(filtered_trades)
                cap_count = len(capturable)
                nocap_count = len(not_capturable)
                st.markdown(f"""<div style='background:linear-gradient(135deg,#0a1f2e,#1e3c3f);border:1px solid #00ff99;border-radius:12px;padding:12px 20px;margin-bottom:16px;display:flex;gap:30px;align-items:center;'>
                    <div style='text-align:center;'><div style='color:#aaa;font-size:12px;'>TOTAL ACTIVE</div><div style='color:#fff;font-size:20px;font-weight:bold;'>{total_ongoing}</div></div>
                    <div style='text-align:center;'><div style='color:#aaa;font-size:12px;'>✅ CAPTURABLE (≥{ongoing_min_acc}%)</div><div style='color:#00ff00;font-size:20px;font-weight:bold;'>{cap_count}</div></div>
                    <div style='text-align:center;'><div style='color:#aaa;font-size:12px;'>❌ BELOW THRESHOLD</div><div style='color:#ff4b4b;font-size:20px;font-weight:bold;'>{nocap_count}</div></div>
                    <div style='text-align:center;'><div style='color:#aaa;font-size:12px;'>MIN ACCURACY</div><div style='color:#ffaa00;font-size:20px;font-weight:bold;'>{ongoing_min_acc}%</div></div>
                </div>""", unsafe_allow_html=True)

                # ── SECTION 1: CAPTURABLE TRADES ───────────────────────────
                if capturable:
                    st.markdown(f"""<div style='background:linear-gradient(135deg,#0a2010,#0d3020);border:1px solid #00ff99;border-left:5px solid #00ff00;border-radius:10px;padding:10px 16px;margin-bottom:12px;'>
                        <b style='color:#00ff00;font-size:15px;'>✅ CAPTURABLE TRADES — Accuracy ≥ {ongoing_min_acc}%</b>
                        <span style='color:#aaa;font-size:12px;'> — These trades meet your minimum accuracy threshold and can be taken.</span>
                    </div>""", unsafe_allow_html=True)

                    for trade, conf_val in sorted(capturable, key=lambda x: x[1], reverse=True):
                        color = "#00ff00" if trade['Direction'] == "BUY" else "#ff4b4b"
                        pair = trade['Pair']; live = get_live_price(pair)
                        live_display = f"{live:.4f}" if live else "N/A"
                        progress = 0.5; direction_text = ""
                        if live is not None:
                            try:
                                entry = float(trade['Entry']); tp3 = float(trade['TP'])
                                if trade['Direction'] == "BUY":
                                    if tp3 > entry: progress = (live - entry) / (tp3 - entry)
                                    direction_text = "⚠️ Moving towards **STOP LOSS**" if live < entry else ("✅ Moving towards **TAKE PROFIT**" if live > entry else "⚖️ At entry level")
                                else:
                                    if entry > tp3: progress = (entry - live) / (entry - tp3)
                                    direction_text = "⚠️ Moving towards **STOP LOSS**" if live > entry else ("✅ Moving towards **TAKE PROFIT**" if live < entry else "⚖️ At entry level")
                                progress = max(0, min(1, progress))
                            except: progress = 0.5; direction_text = "❌ Error calculating"
                        else: direction_text = "❌ Live price unavailable"
                        forecast = trade.get('Forecast', 'No forecast available')
                        col1, col2 = st.columns([5,1])
                        with col1:
                            st.markdown(f"""<div style='background:#0d2a1a; padding:15px; border-radius:10px; margin-bottom:10px; border-left:5px solid {color};'>
                                <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;'>
                                    <b style='color:{color};font-size:15px;'>{trade['Pair']} | {trade['Direction']}</b>
                                    <span style='background:#00ff0022;color:#00ff00;border:1px solid #00ff00;border-radius:8px;padding:2px 10px;font-size:12px;font-weight:bold;'>✅ CAPTURABLE — {conf_val:.0f}% Confidence</span>
                                </div>
                                <span style='color:#00ff99;font-size:12px;'>{trade.get('Timeframe', 'N/A')}</span><br>
                                Entry: {trade['Entry']} | SL: {trade['SL']} | TP: {trade['TP']}<br>
                                Live: {live_display}<br>
                                <small style='color:#aaa;'>Tracked since: {trade['Timestamp']}</small>
                            </div>""", unsafe_allow_html=True)
                            st.progress(progress, text="Progress to Target")
                            st.caption(direction_text)
                            st.caption(f"📊 Engine Forecast: {forecast}")
                        with col2:
                            if not st.session_state.beginner_mode:
                                if st.button("🗑️ Delete", key=f"del_active_{trade['row_num']}"):
                                    if delete_trade_by_row_number(trade['row_num']): st.success("Trade deleted."); st.rerun()
                else:
                    st.info(f"No active trades meet the minimum accuracy threshold of {ongoing_min_acc}%.")

                # ── SECTION 2: NOT CAPTURABLE TRADES ───────────────────────
                if not_capturable:
                    st.markdown("---")
                    with st.expander(f"❌ Cannot Be Captured — Below {ongoing_min_acc}% Threshold ({nocap_count} trades)", expanded=False):
                        st.markdown(f"""<div style='background:#1a0a0a;border:1px solid #ff4b4b44;border-left:5px solid #ff4b4b;border-radius:10px;padding:10px 16px;margin-bottom:12px;'>
                            <b style='color:#ff4b4b;font-size:14px;'>⚠️ These trades do NOT meet your minimum accuracy of {ongoing_min_acc}%</b>
                            <span style='color:#aaa;font-size:12px;'> — Reasons are shown below for each trade.</span>
                        </div>""", unsafe_allow_html=True)

                        for trade, conf_val in sorted(not_capturable, key=lambda x: x[1], reverse=True):
                            dir_color = "#00ff00" if trade['Direction'] == "BUY" else "#ff4b4b"
                            reasons = []
                            gap = ongoing_min_acc - conf_val
                            reasons.append(f"Confidence is {conf_val:.0f}% — needs {ongoing_min_acc:.0f}% (gap: {gap:.0f}%)")
                            if conf_val < 30:
                                reasons.append("Very low confidence — weak or conflicting indicators")
                            elif conf_val < 40:
                                reasons.append("Low confidence — insufficient indicator confluence")
                            elif conf_val < ongoing_min_acc:
                                reasons.append(f"Moderate confidence but below your set threshold of {ongoing_min_acc}%")
                            live = get_live_price(trade['Pair'])
                            if live is None:
                                reasons.append("Live price unavailable — cannot verify current market position")
                            else:
                                try:
                                    entry_f = float(trade['Entry']); sl_f = float(trade['SL']); tp_f = float(trade['TP'])
                                    if trade['Direction'] == "BUY" and live < sl_f:
                                        reasons.append(f"Price ({live:.5f}) has already crossed below SL ({sl_f:.5f})")
                                    elif trade['Direction'] == "SELL" and live > sl_f:
                                        reasons.append(f"Price ({live:.5f}) has already crossed above SL ({sl_f:.5f})")
                                    if trade['Direction'] == "BUY" and live > tp_f:
                                        reasons.append(f"Price ({live:.5f}) has already passed TP ({tp_f:.5f})")
                                    elif trade['Direction'] == "SELL" and live < tp_f:
                                        reasons.append(f"Price ({live:.5f}) has already passed TP ({tp_f:.5f})")
                                except: pass
                            reason_html = "".join([f"<li style='color:#ff9966;margin-bottom:3px;'>⚠️ {r}</li>" for r in reasons])
                            live_display = f"{live:.4f}" if live else "N/A"
                            st.markdown(f"""<div style='background:#1a0505;border:1px solid #ff4b4b33;border-left:4px solid #ff4b4b;border-radius:8px;padding:12px 16px;margin-bottom:10px;opacity:0.9;'>
                                <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>
                                    <b style='color:{dir_color};font-size:14px;'>{trade['Pair']} | {trade['Direction']}</b>
                                    <span style='background:#ff4b4b22;color:#ff4b4b;border:1px solid #ff4b4b;border-radius:8px;padding:2px 10px;font-size:12px;font-weight:bold;'>❌ CANNOT CAPTURE — {conf_val:.0f}%</span>
                                </div>
                                <div style='color:#888;font-size:12px;margin-bottom:6px;'>
                                    <span style='color:#00ff99;'>{trade.get('Timeframe', 'N/A')}</span> &nbsp;|&nbsp;
                                    Entry: {trade['Entry']} &nbsp;|&nbsp; SL: {trade['SL']} &nbsp;|&nbsp; TP: {trade['TP']} &nbsp;|&nbsp; Live: {live_display}
                                </div>
                                <div style='background:#0d0000;border-radius:6px;padding:8px 10px;margin-top:4px;'>
                                    <b style='color:#ff4b4b;font-size:12px;'>❌ Reasons this trade cannot be captured:</b>
                                    <ul style='margin:6px 0 0 0;padding-left:16px;'>{reason_html}</ul>
                                </div>
                                <small style='color:#555;'>Tracked since: {trade['Timestamp']}</small>
                            </div>""", unsafe_allow_html=True)
            else: st.info("No active ongoing trades.")
        with tab2:
            st.subheader("Closed Trades History")
            closed_trades = load_user_trades(user_info['Username'], status=['SL Hit', 'TP Hit'])
            filtered_trades = []
            for trade in closed_trades:
                closed_date_str = trade.get('ClosedDate', '')
                if closed_date_str:
                    try:
                        closed_date = datetime.strptime(closed_date_str, "%Y-%m-%d %H:%M:%S").date()
                        if start_date <= closed_date <= end_date: filtered_trades.append(trade)
                    except: filtered_trades.append(trade)
                else: filtered_trades.append(trade)

            if filtered_trades:
                filtered_trades.sort(key=lambda x: x.get('ClosedDate',''), reverse=True)

                # ── Summary stats bar ──────────────────────────────────────
                tp_hits  = sum(1 for t in filtered_trades if t['Status'] == 'TP Hit')
                sl_hits  = sum(1 for t in filtered_trades if t['Status'] == 'SL Hit')
                total_cl = len(filtered_trades)
                win_rate = (tp_hits / total_cl * 100) if total_cl > 0 else 0
                wr_color = "#00ff00" if win_rate >= 55 else ("#ffaa00" if win_rate >= 45 else "#ff4b4b")

                st.markdown(f"""<div style='background:linear-gradient(135deg,#0a1f2e,#1e3c3f);border:1px solid #00ff99;border-radius:12px;padding:14px 20px;margin-bottom:18px;display:flex;gap:30px;align-items:center;'>
                    <div style='text-align:center;'>
                        <div style='color:#aaa;font-size:12px;'>TOTAL CLOSED</div>
                        <div style='color:#fff;font-size:22px;font-weight:bold;'>{total_cl}</div>
                    </div>
                    <div style='text-align:center;'>
                        <div style='color:#aaa;font-size:12px;'>✅ TP HIT</div>
                        <div style='color:#00ff00;font-size:22px;font-weight:bold;'>{tp_hits}</div>
                    </div>
                    <div style='text-align:center;'>
                        <div style='color:#aaa;font-size:12px;'>❌ SL HIT</div>
                        <div style='color:#ff4b4b;font-size:22px;font-weight:bold;'>{sl_hits}</div>
                    </div>
                    <div style='text-align:center;'>
                        <div style='color:#aaa;font-size:12px;'>WIN RATE</div>
                        <div style='color:{wr_color};font-size:22px;font-weight:bold;'>{win_rate:.1f}%</div>
                    </div>
                </div>""", unsafe_allow_html=True)

                # ── Trade cards ───────────────────────────────────────────
                for trade in filtered_trades:
                    is_tp = trade['Status'] == 'TP Hit'
                    status_color  = "#00ff00" if is_tp else "#ff4b4b"
                    status_bg     = "#004d1a" if is_tp else "#4a0000"
                    status_icon   = "✅" if is_tp else "❌"
                    status_label  = "TP HIT — WIN" if is_tp else "SL HIT — LOSS"
                    dir_color     = "#00ff00" if trade['Direction'] == "BUY" else "#ff4b4b"

                    # Calculate P&L direction from direction + SL/TP
                    try:
                        entry_f = float(str(trade['Entry']).replace(',',''))
                        sl_f    = float(str(trade['SL']).replace(',',''))
                        tp_f    = float(str(trade['TP']).replace(',',''))
                        if is_tp:
                            pips_raw = abs(tp_f - entry_f) / entry_f * 100
                            pnl_text = f"+{pips_raw:.2f}% move"
                            pnl_color = "#00ff00"
                        else:
                            pips_raw = abs(sl_f - entry_f) / entry_f * 100
                            pnl_text = f"-{pips_raw:.2f}% move"
                            pnl_color = "#ff4b4b"
                    except:
                        pnl_text = ""; pnl_color = "#aaa"

                    col1, col2 = st.columns([5,1])
                    with col1:
                        st.markdown(f"""<div style='background:#1a1a1a;padding:14px 16px;border-radius:10px;margin-bottom:10px;border-left:5px solid {status_color};'>
                            <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>
                                <span style='color:{dir_color};font-size:15px;font-weight:bold;'>{trade['Pair']} | {trade['Direction']}</span>
                                <span style='background:{status_bg};color:{status_color};border:1px solid {status_color};border-radius:8px;padding:3px 10px;font-size:13px;font-weight:bold;'>{status_icon} {status_label}</span>
                            </div>
                            <div style='color:#ccc;font-size:13px;'>
                                <span style='color:#aaa;'>Entry:</span> <b>{trade['Entry']}</b> &nbsp;|&nbsp;
                                <span style='color:#ff6666;'>SL:</span> <b>{trade['SL']}</b> &nbsp;|&nbsp;
                                <span style='color:#66ff66;'>TP:</span> <b>{trade['TP']}</b>
                            </div>
                            <div style='margin-top:5px;display:flex;gap:16px;'>
                                <span style='color:{pnl_color};font-size:12px;font-weight:bold;'>{pnl_text}</span>
                                <span style='color:#888;font-size:12px;'>Confidence: {trade['Confidence']}%</span>
                                <span style='color:#00ff99;font-size:12px;'>{trade.get('Timeframe','N/A')}</span>
                            </div>
                            <div style='color:#555;font-size:11px;margin-top:4px;'>
                                Opened: {trade['Timestamp']} &nbsp;|&nbsp; Closed: <b style='color:#888;'>{trade.get('ClosedDate','N/A')}</b>
                            </div>
                        </div>""", unsafe_allow_html=True)
                    with col2:
                        if not st.session_state.beginner_mode:
                            if st.button("🗑️ Delete", key=f"del_closed_{trade['row_num']}"):
                                if delete_trade_by_row_number(trade['row_num']): st.success("Deleted."); st.rerun()
            else:
                st.info("No closed trades found in selected date range.")
        if st.button("Refresh & Check Status"): st.rerun()

    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Center & User Management")
            # ── Live API Rate Meter ────────────────────────────────────────────
            usage = _api_limiter.usage_stats()
            pct   = usage["pct_used"]
            meter_color = "#00ff00" if pct < 60 else ("#ffaa00" if pct < 85 else "#ff4b4b")
            st.markdown(f"""<div style='background:#0a1f2e;border:2px solid {meter_color};border-radius:12px;padding:12px 20px;margin-bottom:16px;'>
                <b style='color:{meter_color};font-size:15px;'>⚡ Live API Rate Meter (50 req/min combined)</b><br>
                <div style='display:flex;gap:30px;margin-top:8px;align-items:center;flex-wrap:wrap;'>
                    <div><span style='color:#aaa;font-size:11px;'>TOTAL USED</span><br>
                        <b style='color:{meter_color};font-size:22px;'>{usage['total_used']}/{usage['total_cap']}</b>
                        <span style='color:#888;font-size:11px;'> per min</span></div>
                    <div><span style='color:#aaa;font-size:11px;'>GOOGLE SHEETS</span><br>
                        <b style='color:#00ccff;font-size:18px;'>{usage['gs_used']}/{usage['gs_cap']}</b></div>
                    <div><span style='color:#aaa;font-size:11px;'>YFINANCE</span><br>
                        <b style='color:#ffaa00;font-size:18px;'>{usage['yf_used']}/{usage['yf_cap']}</b></div>
                    <div><span style='color:#aaa;font-size:11px;'>UTILIZATION</span><br>
                        <b style='color:{meter_color};font-size:18px;'>{pct:.0f}%</b></div>
                </div>
                <div style='background:#222;border-radius:6px;height:8px;margin-top:10px;'>
                    <div style='background:{meter_color};width:{min(pct,100):.0f}%;height:8px;border-radius:6px;transition:width 0.3s;'></div>
                </div>
                <span style='color:#555;font-size:10px;'>Window: 60 sec | GS cap: {usage['gs_cap']}/min | YF cap: {usage['yf_cap']}/min | Spacing: 250ms</span>
            </div>""", unsafe_allow_html=True)
            st.metric("Total System API Requests", st.session_state.total_api_requests)
            sheet, _ = get_user_sheet()
            if sheet:
                _gsheets_limiter.wait_if_needed()
                all_records = sheet.get_all_records()
                df_users = pd.DataFrame(all_records)
                st.dataframe(df_users, use_container_width=True)
                st.markdown("---")
                with st.expander("➕ Create New User", expanded=False):
                    with st.form("create_user_form"):
                        new_u_name = st.text_input("Username"); new_u_pass = st.text_input("Password")
                        new_u_limit = st.number_input("Initial Hybrid Limit", value=100, min_value=1)
                        if st.form_submit_button("Create User"):
                            if new_u_name and new_u_pass:
                                success, msg = add_new_user_to_db(new_u_name, new_u_pass, new_u_limit)
                                if success: st.success(msg); time.sleep(1); st.rerun()
                                else: st.error(msg)
                            else: st.warning("Please fill all fields")
                st.markdown("### ✏️ Manage User Credits")
                user_list = [r['Username'] for r in all_records if str(r.get('Username')) != 'Admin']
                target_user = st.selectbox("Select User to Update", user_list)
                if target_user:
                    curr_user_data = next((u for u in all_records if u['Username'] == target_user), {})
                    st.info(f"User: **{target_user}** | Current Limit: **{curr_user_data.get('HybridLimit', 'N/A')}** | Used: **{curr_user_data.get('UsageCount', 'N/A')}**")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.subheader("Update Limit")
                        new_limit_val = st.number_input("New Hybrid Limit", min_value=0, value=int(curr_user_data.get('HybridLimit', 100)))
                        if st.button("💾 Save Limit"):
                            update_user_limit_in_db(target_user, new_limit_val); st.success(f"Limit updated to {new_limit_val}"); time.sleep(1); st.rerun()
                    with c2:
                        st.subheader("Reset Usage")
                        new_usage_val = st.number_input("Set Usage Count", min_value=0, value=0)
                        if st.button("🔄 Update Usage"):
                            update_usage_in_db(target_user, new_usage_val); st.success(f"Usage count set to {new_usage_val}"); time.sleep(1); st.rerun()
            else: st.error("Database Connection Failed")

            # ── History Cache Management Section ──────────────────────────
            st.markdown("---")
            st.markdown("### 📊 Historical Data Cache (Google Sheets)")
            st.markdown("""<div style='background:#0a1f2e;border:1px solid #00ff9944;border-radius:10px;padding:12px 16px;margin-bottom:16px;font-size:13px;color:#ccc;'>
                <b style='color:#00ff99;'>How it works:</b><br>
                • First scan: Full history downloaded from yfinance → saved to Google Sheets<br>
                • Subsequent scans: Only <b>new candles</b> fetched (incremental update) → merged with saved data<br>
                • Memory cache: Expires per timeframe (1m=1min, 1h=30min, 1d=2hr)<br>
                • Sheets cache: Persistent across sessions → <b>faster startup, fewer API calls</b><br>
                <br>
                <b style='color:#00ff99;'>History Length:</b>
                1m=5d | 5m=1mo | 15m=3mo | 1h=6mo | 4h=1y | 1d=2y | 1wk=5y
            </div>""", unsafe_allow_html=True)

            col_h1, col_h2 = st.columns(2)
            with col_h1:
                if st.button("📋 Show Cache Stats", use_container_width=True):
                    with st.spinner("Loading cache stats..."):
                        stats = get_history_cache_stats()
                        if stats:
                            df_stats = pd.DataFrame(stats)
                            st.dataframe(df_stats, use_container_width=True)
                        else:
                            st.info("No history cache sheets found yet. Run a scan to populate.")

            with col_h2:
                st.subheader("🗑️ Clear Cache for Symbol")
                clear_sym = st.text_input("Symbol (e.g. EURUSD, XAUUSD, BTC-USD)", key="clear_cache_sym")
                clear_tf_opts = ["All TFs", "1m", "5m", "15m", "1h", "4h", "1d", "1wk"]
                clear_tf_sel = st.selectbox("Timeframe", clear_tf_opts, key="clear_cache_tf")
                if st.button("🗑️ Clear Cache", key="clear_cache_btn", use_container_width=True):
                    if clear_sym:
                        tf_arg = None if clear_tf_sel == "All TFs" else clear_tf_sel
                        # Format symbol
                        sym_fmt = clear_sym.upper().strip()
                        cleared = clear_history_cache_for_symbol(sym_fmt, tf_arg)
                        if cleared:
                            st.success(f"Cleared: {', '.join(cleared)}")
                        else:
                            st.warning("No cache found for that symbol.")
                    else:
                        st.warning("Enter a symbol first.")

        else: st.error("Access Denied.")

    elif app_mode == "Backtest" and not st.session_state.beginner_mode:
        st.title("📈 Backtest Engine")
        st.markdown("<div class='scan-header'><h3>⚙️ Configure Backtest</h3></div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1: market_choice = st.selectbox("Market", options=["All","Forex","Crypto","Metals"], index=0, key="backtest_market")
        with col2: min_acc = st.slider("Minimum Accuracy (%)", min_value=0, max_value=100, value=st.session_state.min_accuracy, step=5)
        col3, col4 = st.columns(2)
        with col3: start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=30))
        with col4: end_date = st.date_input("End Date", value=datetime.now())
        if st.button("🚀 Run Backtest", type="primary"):
            with st.spinner("Running backtest... This may take a while."):
                results = run_backtest(market_choice, start_date, end_date, min_acc, st.session_state.user, assets)
                st.session_state.backtest_results = results
        if st.session_state.backtest_results:
            res = st.session_state.backtest_results
            st.markdown("---"); st.subheader("📊 Backtest Results")
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Total Trades", res['total_trades'])
            with col2: st.metric("Winning Trades", res['winning_trades'])
            with col3: st.metric("Win Rate", f"{res['win_rate']:.2f}%")
            with col4: st.metric("Total Profit %", f"{res['total_profit_pct']:.2f}%")
            if res['results']:
                df_res = pd.DataFrame(res['results'])
                st.dataframe(df_res, use_container_width=True)

    st.markdown("---")
    st.markdown("<div class='footer'>⚡ Infinite AI Terminal v32.0 | Unified 50 req/min Rate Engine (GS:28 + YF:22) | Per-TF Google Sheets Cache | EW+ICT+SMC+Fibonacci Precision | Risk Badges</div>", unsafe_allow_html=True)
    if auto_refresh: time.sleep(60); st.rerun()
