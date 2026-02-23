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

# --- 1. SETUP & STYLE (UPDATED ANIMATIONS & BRANDING) ---
st.set_page_config(page_title="Infinite Algo Terminal v27.0 (AI-Powered Scanner)", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    /* --- ANIMATIONS & GLOBAL STYLES --- */
    @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes pulse-green { 0% { box-shadow: 0 0 0 0 rgba(0, 255, 0, 0.7); } 70% { box-shadow: 0 0 15px 15px rgba(0, 255, 0, 0); } 100% { box-shadow: 0 0 0 0 rgba(0, 255, 0, 0); } }
    @keyframes pulse-red { 0% { box-shadow: 0 0 0 0 rgba(255, 75, 75, 0.7); } 70% { box-shadow: 0 0 15px 15px rgba(255, 75, 75, 0); } 100% { box-shadow: 0 0 0 0 rgba(255, 75, 75, 0); } }
    @keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    @keyframes shimmer {
        0% { background-position: -1000px 0; }
        100% { background-position: 1000px 0; }
    }
    @keyframes float {
        0% { transform: translateY(0px); }
        50% { transform: translateY(-5px); }
        100% { transform: translateY(0px); }
    }
    @keyframes glow {
        0% { box-shadow: 0 0 5px #00ff99; }
        50% { box-shadow: 0 0 20px #00ff99; }
        100% { box-shadow: 0 0 5px #00ff99; }
    }
    .loading-icon { display: inline-block; animation: rotate 2s linear infinite; font-size: 24px; }
    
    .stApp { animation: fadeIn 0.8s ease-out forwards; }

    /* --- ALERT PANELS --- */
    .high-prob-alert {
        background: linear-gradient(135deg, #1a1a1a, #2d2d2d);
        border: 2px solid #00ff99;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 20px;
        text-align: center;
        animation: glow 2s infinite;
    }
    
    /* --- TEXT COLORS --- */
    .price-up { color: #00ff00; font-size: 26px; font-weight: 800; text-shadow: 0 0 10px rgba(0, 255, 0, 0.5); }
    .price-down { color: #ff4b4b; font-size: 26px; font-weight: 800; text-shadow: 0 0 10px rgba(255, 75, 75, 0.5); }
    
    /* --- BOXES --- */
    .entry-box { 
        background: rgba(0, 255, 153, 0.1);
        border: 2px solid #00ff99; 
        padding: 20px; border-radius: 15px; margin-top: 15px; 
        color: white; backdrop-filter: blur(10px);
        box-shadow: 0 0 20px rgba(0, 255, 153, 0.2);
        transition: transform 0.3s, box-shadow 0.3s;
        animation: float 4s ease-in-out infinite;
    }
    .entry-box:hover { transform: scale(1.02); box-shadow: 0 0 30px rgba(0, 255, 153, 0.5); }
    
    .trade-metric { 
        background: linear-gradient(145deg, #1e1e1e, #2a2a2a);
        border: 1px solid #444; 
        border-radius: 12px; padding: 15px; text-align: center; transition: all 0.3s ease;
    }
    .trade-metric:hover { transform: translateY(-5px) scale(1.02); box-shadow: 0 10px 20px rgba(0,0,0,0.5); border-color: #00ff99; }
    .trade-metric h4 { margin: 0; color: #aaa; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }
    .trade-metric h2 { margin: 5px 0 0 0; color: #fff; font-size: 22px; font-weight: bold; }
    
    /* --- NEWS CARDS --- */
    .news-card { 
        background: #1e1e1e;
        padding: 12px; margin-bottom: 10px; 
        border-radius: 8px; transition: all 0.3s ease; border-right: 1px solid #333;
        animation: fadeIn 0.5s;
        position: relative;
    }
    .news-card:hover { transform: translateX(5px); background: #252525; box-shadow: -5px 0 10px rgba(0,0,0,0.3); }
    .news-positive { border-left: 5px solid #00ff00; }
    .news-negative { border-left: 5px solid #ff4b4b; }
    .news-neutral { border-left: 5px solid #00ff99; }
    .news-time {
        font-size: 10px;
        color: #888;
        position: absolute;
        bottom: 2px;
        right: 8px;
    }
    
    /* --- SIGNAL BOXES --- */
    .sig-box { 
        padding: 12px;
        border-radius: 8px; font-size: 13px; text-align: center; 
        font-weight: bold; border: 1px solid #444; margin-bottom: 8px; box-shadow: inset 0 0 10px rgba(0,0,0,0.2);
        transition: all 0.3s;
        animation: fadeIn 0.6s;
    }
    .sig-box:hover {
        transform: scale(1.02);
        box-shadow: 0 0 15px currentColor;
    }
    .bull { background: linear-gradient(90deg, #004d40, #00695c); color: #00ff00; border-color: #00ff00; }
    .bear { background: linear-gradient(90deg, #4a1414, #7f0000); color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background: #262626; color: #888; }

    /* --- NOTIFICATIONS --- */
    .notif-container { 
        padding: 20px;
        border-radius: 12px; margin-bottom: 25px; 
        border-left: 8px solid; background: #121212; font-size: 18px;
        animation: fadeIn 0.8s;
    }
    .notif-buy { border-color: #00ff00; color: #00ff00; animation: pulse-green 2s infinite; }
    .notif-sell { border-color: #ff4b4b; color: #ff4b4b; animation: pulse-red 2s infinite; }
    .notif-wait { border-color: #555; color: #aaa; }
    
    /* --- CONFIRMATION CARD --- */
    .confirm-card {
        background: #1e1e1e;
        border-left: 5px solid;
        border-radius: 8px;
        padding: 10px 15px;
        margin: 10px 0;
        font-size: 14px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .confirm-approve { border-color: #00ff00; }
    .confirm-reject { border-color: #ff4b4b; }
    .confirm-icon { font-size: 20px; }
    
    /* --- ADMIN TABLE --- */
    .admin-table { font-size: 14px; width: 100%; border-collapse: collapse; }
    .admin-table th, .admin-table td { border: 1px solid #444; padding: 8px; text-align: left; }
    .admin-table th { background-color: #333; color: #00ff99; }
    
    /* --- FORECAST ANIMATION --- */
    .forecast-loading {
        text-align: center;
        padding: 20px;
        background: #1e1e1e;
        border-radius: 10px;
        border: 1px solid #00ff99;
        margin: 10px 0;
        animation: glow 1.5s infinite;
    }
    .forecast-loading span {
        font-size: 20px;
        color: #00ff99;
    }
    
    /* --- NEW SCAN CARD ANIMATION --- */
    .scan-card {
        animation: slideInUp 0.5s ease-out;
    }
    @keyframes slideInUp {
        from { opacity: 0; transform: translateY(30px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* --- USER-FRIENDLY IMPROVEMENTS --- */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 10px rgba(0,255,153,0.3);
    }
    .scan-header {
        background: linear-gradient(90deg, #1e3c3f, #0a1f2e);
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 5px solid #00ff99;
    }
    
    /* --- ADDITIONAL PROFESSIONAL TOUCHES --- */
    .main-title {
        text-align: center;
        background: linear-gradient(135deg, #0a1f2e, #1e3c3f);
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 25px;
        border: 1px solid #00ff99;
        box-shadow: 0 0 30px rgba(0,255,153,0.2);
    }
    .main-title h1 {
        color: #00ff99;
        font-weight: 700;
        letter-spacing: 2px;
        margin: 0;
    }
    .main-title p {
        color: #ccc;
        margin: 5px 0 0;
    }
    .footer {
        text-align: center;
        margin-top: 40px;
        padding: 15px;
        background: #0e0e0e;
        border-radius: 10px;
        font-size: 12px;
        color: #666;
        border-top: 1px solid #333;
    }
    div.stSlider > div[data-baseweb="slider"] {
        padding-top: 1rem;
    }
    .stSlider label {
        color: #00ff99 !important;
        font-weight: 600;
    }
    .stSelectbox label {
        color: #00ff99 !important;
        font-weight: 600;
    }
    .stRadio label {
        color: #00ff99 !important;
    }
    .stCheckbox label {
        color: #00ff99 !important;
    }
    .css-1v0mbdj.etr89bj1 {
        background: #1e1e1e;
        border-radius: 10px;
        padding: 10px;
    }
    hr {
        border-color: #333;
    }
    
    /* --- SESSION DASHBOARD --- */
    .session-card {
        background: #0e0e0e;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 15px;
        font-size: 13px;
        border-left: 3px solid #00ff99;
    }
    .session-card span {
        color: #00ff99;
        font-weight: 600;
    }
    
    /* --- AI BADGE --- */
    .ai-badge {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
        margin-left: 8px;
    }
    .ai-approve {
        background-color: #00ff0022;
        color: #00ff00;
        border: 1px solid #00ff00;
    }
    .ai-reject {
        background-color: #ff4b4b22;
        color: #ff4b4b;
        border: 1px solid #ff4b4b;
    }
    
    /* --- DASHBOARD CARDS --- */
    .dashboard-card {
        background: linear-gradient(145deg, #1e1e1e, #2a2a2a);
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 20px;
        border: 1px solid #444;
        box-shadow: 0 10px 20px rgba(0,0,0,0.5);
        transition: all 0.3s ease;
    }
    .dashboard-card:hover {
        transform: translateY(-5px);
        border-color: #00ff99;
        box-shadow: 0 15px 30px rgba(0,255,153,0.2);
    }
    .dashboard-card h3 {
        color: #00ff99;
        margin-top: 0;
        border-bottom: 1px solid #333;
        padding-bottom: 10px;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #fff;
    }
    .metric-label {
        color: #aaa;
        font-size: 14px;
    }
    
    /* --- LIVE PRICE TABLE --- */
    .live-price-table {
        width: 100%;
        border-collapse: collapse;
    }
    .live-price-table th {
        background-color: #333;
        color: #00ff99;
        padding: 8px;
        text-align: left;
    }
    .live-price-table td {
        padding: 8px;
        border-bottom: 1px solid #444;
    }
    
    /* --- NEW: SYSTEM ANALYSIS ENGINE ANIMATION --- */
    .system-engine-card {
        background: linear-gradient(145deg, #0a1f2e, #1e3c3f);
        border: 2px solid #00ff99;
        border-radius: 20px;
        padding: 25px;
        margin-bottom: 20px;
        text-align: center;
        box-shadow: 0 0 30px rgba(0,255,153,0.3);
        animation: glow 2s infinite;
    }
    .system-engine-card h2 {
        color: #00ff99;
        margin-bottom: 15px;
        font-weight: 700;
        letter-spacing: 2px;
    }
    .engine-icon {
        font-size: 60px;
        animation: rotate 3s linear infinite;
        display: inline-block;
        margin-bottom: 15px;
        color: #00ff99;
    }
    .engine-text {
        color: white;
        font-size: 20px;
        background: rgba(0,0,0,0.3);
        padding: 10px;
        border-radius: 10px;
        border: 1px solid #00ff99;
        backdrop-filter: blur(5px);
    }
    
    /* --- SINHALA FONT SUPPORT --- */
    body {
        font-family: 'Noto Sans Sinhala', 'Iskoola Pota', 'Arial Unicode MS', sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "active_provider" not in st.session_state: st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
if "scan_results" not in st.session_state: st.session_state.scan_results = []  # Now a flat list
if "forecast_chart" not in st.session_state: st.session_state.forecast_chart = None
if "selected_trade" not in st.session_state: st.session_state.selected_trade = None
if "deep_analysis_result" not in st.session_state: st.session_state.deep_analysis_result = None
if "deep_analysis_provider" not in st.session_state: st.session_state.deep_analysis_provider = None
if "deep_forecast_chart" not in st.session_state: st.session_state.deep_forecast_chart = None
if "selected_market" not in st.session_state: st.session_state.selected_market = "All"
if "min_accuracy" not in st.session_state: st.session_state.min_accuracy = 40  # default
if "last_activity" not in st.session_state: st.session_state.last_activity = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
if "login_time" not in st.session_state: st.session_state.login_time = None
if "ai_confirmations" not in st.session_state: st.session_state.ai_confirmations = {}  # store AI confirmations for scanner trades
if "tracked_trades" not in st.session_state: st.session_state.tracked_trades = set()  # store IDs of auto-tracked trades

# NEW: Session state for dashboard forecast and news analysis
if "dashboard_forecast" not in st.session_state:
    st.session_state.dashboard_forecast = None
if "dashboard_forecast_provider" not in st.session_state:
    st.session_state.dashboard_forecast_provider = None
if "news_impact_analysis" not in st.session_state:
    st.session_state.news_impact_analysis = None
if "news_impact_provider" not in st.session_state:
    st.session_state.news_impact_provider = None
if "tech_chart" not in st.session_state:
    st.session_state.tech_chart = None
if "theory_chart" not in st.session_state:
    st.session_state.theory_chart = None

# NEW: Total API requests counter (for Admin Panel)
if "total_api_requests" not in st.session_state:
    st.session_state.total_api_requests = 0

# NEW: Historical data cache
if "historical_data_cache" not in st.session_state:
    st.session_state.historical_data_cache = {}  # key -> (df, timestamp)

# NEW: Beginner mode
if "beginner_mode" not in st.session_state:
    st.session_state.beginner_mode = False

# NEW: Backtest results
if "backtest_results" not in st.session_state:
    st.session_state.backtest_results = None

# Cache for live prices (to avoid rate limits)
if "price_cache" not in st.session_state:
    st.session_state.price_cache = {}  # clean_pair -> (price, timestamp)

# ==================== HELPER FUNCTIONS ====================

def get_yf_symbol(display_symbol):
    """Convert display symbol to yfinance symbol."""
    if display_symbol.endswith("-USDT"):
        return display_symbol.replace("-USDT", "-USD")
    # Metals
    if display_symbol in ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]:
        return display_symbol + "=X"
    return display_symbol

def clean_pair_to_yf_symbol(clean_pair):
    """Convert clean pair string to yfinance symbol."""
    if clean_pair in ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"]:
        return clean_pair + "=X"
    if clean_pair.endswith("USDT"):
        base = clean_pair[:-4]
        return base + "-USD"
    return clean_pair + "=X"

def get_live_price(clean_pair):
    """Fetch current live price using yfinance with caching."""
    current_time = time.time()
    cache_duration = 60

    if clean_pair in st.session_state.price_cache:
        price, timestamp = st.session_state.price_cache[clean_pair]
        if current_time - timestamp < cache_duration and price is not None:
            return price

    yf_sym = clean_pair_to_yf_symbol(clean_pair)
    price = None
    try:
        ticker = yf.Ticker(yf_sym)
        # Try 1-minute history
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
        else:
            # Try fast_info
            if hasattr(ticker, 'fast_info') and ticker.fast_info:
                try:
                    price = ticker.fast_info['lastPrice']
                except:
                    pass
            if price is None:
                # Try info
                info = ticker.info
                price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('ask')
        if price is not None:
            st.session_state.price_cache[clean_pair] = (price, current_time)
            return price
        else:
            # Don't cache None
            return None
    except Exception as e:
        print(f"Error fetching price for {clean_pair}: {e}")
        return None

# --- Historical Data Cache ---
def get_cached_historical_data(symbol, interval, period=None, start=None, end=None):
    """
    Fetch historical data with caching.
    Cache key is based on symbol, interval, and period (or start/end).
    Cache expires after 1 hour.
    """
    if period:
        key = f"{symbol}_{interval}_{period}"
    else:
        key = f"{symbol}_{interval}_{start}_{end}"
    
    current_time = time.time()
    cache_entry = st.session_state.historical_data_cache.get(key)
    
    if cache_entry:
        df, timestamp = cache_entry
        if current_time - timestamp < 3600:  # 1 hour cache
            return df
    
    # Download data
    try:
        if period:
            df = yf.download(symbol, period=period, interval=interval, progress=False)
        else:
            df = yf.download(symbol, start=start, end=end, interval=interval, progress=False)
        
        if df.empty or len(df) < 10:
            return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        st.session_state.historical_data_cache[key] = (df, current_time)
        return df
    except Exception as e:
        print(f"Error downloading {symbol} {interval}: {e}")
        return None

# --- Helper to get period for a given timeframe ---
def get_period_for_tf(tf):
    """Return yfinance period string for a given timeframe."""
    period_map = {
        "1m": "1d",
        "5m": "5d",
        "15m": "1mo",
        "1h": "3mo",
        "4h": "6mo",
        "1d": "1y",
        "1wk": "5y"
    }
    return period_map.get(tf, "1mo")

# --- Google Sheets Functions (User DB) ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        try: sheet = client.open("Forex_User_DB").sheet1
        except: sheet = None
        return sheet, client
    except: return None, None

def get_ongoing_sheet():
    """Get or create Ongoing Trades worksheet."""
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("Forex_User_DB")
        try:
            sheet = spreadsheet.worksheet("Ongoing_Trades")
        except gspread.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(title="Ongoing_Trades", rows=100, cols=11)
            headers = ["User", "Timestamp", "Pair", "Direction", "Entry", "SL", "TP", "Confidence", "Status", "ClosedDate", "Notes"]
            sheet.append_row(headers)
        return sheet, client
    except Exception as e:
        st.error(f"Ongoing Trades sheet error: {e}")
        return None, None

def save_trade_to_ongoing(trade, username):
    sheet, _ = get_ongoing_sheet()
    if sheet:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [
                username,
                now,
                trade['pair'],
                trade['dir'],
                trade['entry'],
                trade['sl'],
                trade['tp'],
                trade['conf'],
                "Active",
                "",
                ""
            ]
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
            records = sheet.get_all_records()
            user_trades = []
            for idx, record in enumerate(records):
                if record.get('User') == username:
                    if status is None or record.get('Status') == status or (isinstance(status, list) and record.get('Status') in status):
                        record_copy = record.copy()
                        record_copy['row_num'] = idx + 2
                        user_trades.append(record_copy)
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
            sheet.update_cell(row_index + 2, status_col, new_status)
            if closed_date:
                sheet.update_cell(row_index + 2, closed_col, closed_date)
            return True
        except Exception as e:
            st.error(f"Error updating trade: {e}")
            return False
    return False

def delete_trade_by_row_number(row_number):
    """
    Delete a trade from Ongoing Trades by row number.
    Also remove its trade_id from tracked_trades if it was auto-tracked.
    """
    sheet, _ = get_ongoing_sheet()
    if not sheet:
        return False
    try:
        # Get the trade details before deleting
        row_values = sheet.row_values(row_number)
        headers = sheet.row_values(1)
        if len(row_values) >= len(headers):
            trade_dict = dict(zip(headers, row_values))
            pair = trade_dict.get('Pair', '')
            direction = trade_dict.get('Direction', '')
            entry_str = trade_dict.get('Entry', '0').replace(',', '')
            try:
                entry = float(entry_str)
                # Since we don't have timeframe, we can't reconstruct exact trade_id.
                # We'll leave tracked_trades as is; user may need to clear session to see deleted trades again.
                pass
            except:
                pass
        # Delete the row
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
        records = sheet.get_all_records()
        for idx, record in enumerate(records):
            if record.get('User') == username and record.get('Status') == 'Active':
                pair = record['Pair']
                live = get_live_price(pair)
                if live is None:
                    continue
                try:
                    entry_str = str(record['Entry']).replace(',', '')
                    sl_str = str(record['SL']).replace(',', '')
                    tp_str = str(record['TP']).replace(',', '')
                    entry = float(entry_str)
                    sl = float(sl_str)
                    tp = float(tp_str)
                except:
                    continue
                direction = record['Direction']
                hit = False
                new_status = ""
                if direction == "BUY":
                    if live <= sl:
                        new_status = "SL Hit"
                        hit = True
                    elif live >= tp:
                        new_status = "TP Hit"
                        hit = True
                else:
                    if live >= sl:
                        new_status = "SL Hit"
                        hit = True
                    elif live <= tp:
                        new_status = "TP Hit"
                        hit = True
                if hit:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    update_trade_status_by_row(idx, new_status, now)
        return load_user_trades(username, status='Active')
    except Exception as e:
        st.error(f"Error checking trades: {e}")
        return []

def is_trade_tracked(scan_trade, active_trades):
    for active in active_trades:
        if active['Pair'] != scan_trade['pair']:
            continue
        if active['Direction'] != scan_trade['dir']:
            continue
        try:
            active_entry = float(active['Entry'])
            scan_entry = scan_trade['entry']
            diff_percent = abs(active_entry - scan_entry) / scan_entry
            if diff_percent < 0.001:
                return True
        except:
            pass
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
            records = sheet.get_all_records()
            user = next((i for i in records if str(i.get("Username")) == username), None)
            if user and str(user.get("Password")) == password:
                current_date = get_current_date_str()
                last_login_date = str(user.get("LastLogin", ""))
                if last_login_date != current_date:
                    try:
                        cell = sheet.find(username)
                        headers = sheet.row_values(1)
                        if "UsageCount" in headers:
                            sheet.update_cell(cell.row, headers.index("UsageCount") + 1, 0)
                            user["UsageCount"] = 0
                        # Set HybridLimit to 100 for new day
                        if "HybridLimit" in headers:
                            # Reset to 100 (or keep existing if admin wants? but requirement: daily 100)
                            sheet.update_cell(cell.row, headers.index("HybridLimit") + 1, 100)
                            user["HybridLimit"] = 100
                        if "LastLogin" in headers:
                            sheet.update_cell(cell.row, headers.index("LastLogin") + 1, current_date)
                            user["LastLogin"] = current_date
                    except Exception as e:
                        print(f"Daily Reset Error: {e}")
                # Ensure limit and usage are present
                if "HybridLimit" not in user: user["HybridLimit"] = 100
                if "UsageCount" not in user: user["UsageCount"] = 0
                return user
        except: return None
    return None

def update_usage_in_db(username, new_usage):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell:
                headers = sheet.row_values(1)
                if "UsageCount" in headers:
                    col_idx = headers.index("UsageCount") + 1
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
            if cell:
                return False, "User already exists!"
            # Default limit to 100 if not specified
            if limit is None:
                limit = 100
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
    except:
        pass
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
        except:
            pass
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
    """Calculate a sentiment score for confidence (old code style)."""
    score = 0
    for news in news_items:
        s_class = get_sentiment_class(news['title'])
        if s_class == "news-positive":
            score += 10
        elif s_class == "news-negative":
            score -= 10
    return max(min(score, 20), -20)

def get_data_period(tf):
    if tf in ["1m", "5m"]: return "5d"
    elif tf == "15m": return "1mo"
    elif tf == "1h": return "6mo"
    elif tf == "4h": return "1y"
    elif tf == "1d": return "2y"
    elif tf == "1wk": return "5y"
    return "1mo"

# --- 4. ADVANCED SIGNAL ENGINE (UPDATED TO OLD CODE STYLE + RISK MINIMIZATION) ---
def calculate_advanced_signals(df, tf, news_items=None):
    """
    Calculate signals using old code weights and include news score.
    Returns signals dict, atr, confidence, and a detailed score breakdown.
    """
    if df is None or len(df) < 50:
        return None, 0, 0, {}
    signals = {}
    score_breakdown = {}
    c = df['Close'].iloc[-1]
    h = df['High'].iloc[-1]
    l = df['Low'].iloc[-1]
    
    # --- 1. TREND (MA & Slope) ---
    ma_50 = df['Close'].rolling(50).mean().iloc[-1]
    ma_200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) > 200 else ma_50
    y_vals = df['Close'].tail(20).values
    x_vals = np.arange(len(y_vals))
    slope, intercept = np.polyfit(x_vals, y_vals, 1) if len(y_vals) > 1 else (0, c)
    
    trend_dir = "neutral"
    trend_score = 0
    if c > ma_50 and c > ma_200 and slope > 0:
        trend_dir = "bull"
        trend_score = 20
    elif c < ma_50 and c < ma_200 and slope < 0:
        trend_dir = "bear"
        trend_score = -20
    signals['TREND'] = (f"Trend {trend_dir.upper()} (Slope {slope:.2f})", trend_dir)
    score_breakdown['Trend'] = trend_score

    # --- 2. MACD ---
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    macd_val = macd.iloc[-1]
    sig_val = signal_line.iloc[-1]
    macd_signal = "neutral"
    macd_score = 0
    if macd_val > sig_val and macd_val > 0:
        macd_signal = "bull"
        macd_score = 10
    elif macd_val < sig_val and macd_val < 0:
        macd_signal = "bear"
        macd_score = -10
    score_breakdown['MACD'] = macd_score
    
    # --- 3. SMC & ICT ---
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    last_candles = df.tail(5)
    is_bullish_ob = (last_candles['Close'].iloc[-3] < last_candles['Open'].iloc[-3]) and \
                    (last_candles['Close'].iloc[-1] > last_candles['High'].iloc[-3])
    is_bearish_ob = (last_candles['Close'].iloc[-3] > last_candles['Open'].iloc[-3]) and \
                    (last_candles['Close'].iloc[-1] < last_candles['Low'].iloc[-3])

    smc_signal = "neutral"
    smc_score = 0
    if c > highs.iloc[-2] or is_bullish_ob:
        smc_signal = "bull"
        smc_score = 20
    elif c < lows.iloc[-2] or is_bearish_ob:
        smc_signal = "bear"
        smc_score = -20
    signals['SMC'] = (f"{smc_signal.upper()} Structure/OB", smc_signal)
    score_breakdown['SMC'] = smc_score
    
    fvg_bull = df['Low'].iloc[-1] > df['High'].iloc[-3]
    fvg_bear = df['High'].iloc[-1] < df['Low'].iloc[-3]
    ict_signal = "bull" if fvg_bull else ("bear" if fvg_bear else "neutral")
    ict_score = 10 if ict_signal == "bull" else (-10 if ict_signal == "bear" else 0)
    signals['ICT'] = (f"{ict_signal.upper()} FVG", ict_signal)
    score_breakdown['ICT'] = ict_score

    # --- 4. LIQUIDITY & SUPPORT/RESISTANCE ---
    liq_signal = "neutral"
    liq_text = "Holding"
    recent_low = df['Low'].tail(30).min()
    recent_high = df['High'].tail(30).max()
    is_at_support = abs(c - recent_low) < (c * 0.002)
    is_at_resistance = abs(c - recent_high) < (c * 0.002)

    liq_score = 0
    if l < df['Low'].iloc[-10:-1].min() or is_at_support:
        liq_signal = "bull"
        liq_text = "Liq Grab / Support"
        liq_score = 15
    elif h > df['High'].iloc[-10:-1].max() or is_at_resistance:
        liq_signal = "bear"
        liq_text = "Liq Grab / Resist"
        liq_score = -15
    signals['LIQ'] = (liq_text, liq_signal)
    score_breakdown['Liquidity'] = liq_score
    
    # --- 5. PATTERNS ---
    patt_signal = "neutral"
    patt_text = "No Pattern"
    patt_score = 0
    if (df['Close'].iloc[-1] > df['Open'].iloc[-1] and df['Close'].iloc[-1] > df['Open'].iloc[-2] and df['Open'].iloc[-1] < df['Close'].iloc[-2]):
        patt_signal = "bull"
        patt_text = "Bull Engulfing"
        patt_score = 15
    elif (df['Close'].iloc[-1] < df['Open'].iloc[-1] and df['Close'].iloc[-1] < df['Open'].iloc[-2] and df['Open'].iloc[-1] > df['Close'].iloc[-2]):
        patt_signal = "bear"
        patt_text = "Bear Engulfing"
        patt_score = -15
    signals['PATT'] = (patt_text, patt_signal)
    score_breakdown['Patterns'] = patt_score
    
    # --- 6. BOLLINGER BANDS ---
    sma_20 = df['Close'].rolling(20).mean()
    std_20 = df['Close'].rolling(20).std()
    upper_bb = sma_20 + (std_20 * 2)
    lower_bb = sma_20 - (std_20 * 2)
    bb_status = "neutral"
    bb_text = "Normal Vol"
    bb_score = 0
    if c > upper_bb.iloc[-1]:
        bb_status = "bear"
        bb_text = "Overextended"
        bb_score = -10
    elif c < lower_bb.iloc[-1]:
        bb_status = "bull"
        bb_text = "Oversold"
        bb_score = 10
    signals['VOLATILITY'] = (bb_text, bb_status)
    score_breakdown['Bollinger'] = bb_score

    # --- 7. RSI ---
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
    signals['RSI'] = (f"RSI: {int(rsi_val)}", "neutral")
    rsi_score = 0
    if rsi_val < 30:
        rsi_score = 10 if trend_dir == "bull" else -5
    elif rsi_val > 70:
        rsi_score = -10 if trend_dir == "bear" else 5
    score_breakdown['RSI'] = rsi_score

    # --- 8. FIBONACCI ---
    ph_fib = df['High'].rolling(50).max().iloc[-1]
    pl_fib = df['Low'].rolling(50).min().iloc[-1]
    fib_range = ph_fib - pl_fib
    fib_618 = ph_fib - (fib_range * 0.618)
    fib_score = 10 if abs(c - fib_618) < (c * 0.001) else 0
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.001) else ("Ranging", "neutral")
    score_breakdown['Fibonacci'] = fib_score
    
    # --- 9. ELLIOTT WAVE ---
    last_50 = df['Close'].tail(50)
    max_50, min_50 = last_50.max(), last_50.min()
    current_pos = (c - min_50) / (max_50 - min_50) if (max_50 - min_50) != 0 else 0.5
    
    ew_status = "Wave Analysis"
    ew_col = "neutral"
    ew_score = 0
    if trend_dir == "bull":
        if current_pos > 0.8:
            ew_status, ew_col = "Wave 5 (Top)", "bear"
            ew_score = -5
        elif 0.4 < current_pos <= 0.8:
            ew_status, ew_col = "Wave 3 (Impulse)", "bull"
            ew_score = 10
        else:
            ew_status, ew_col = "Wave 1 (Start)", "bull"
            ew_score = 5
    else:
        if current_pos < 0.2:
            ew_status, ew_col = "Wave C (Drop)", "bull"
            ew_score = 10
        elif 0.2 <= current_pos < 0.6:
            ew_status, ew_col = "Wave A (Corr)", "bear"
            ew_score = -10
        else:
            ew_status, ew_col = "Wave B (Rally)", "neutral"
            ew_score = 0
    signals['ELLIOTT'] = (ew_status, ew_col)
    score_breakdown['Elliott'] = ew_score

    # --- 10. CONFIDENCE SCORING (OLD CODE STYLE) ---
    confidence = 0

    # News impact (old code style)
    if news_items:
        news_score = calculate_news_score(news_items)
        confidence += news_score
        score_breakdown['News'] = news_score

    # Sum all scores
    confidence += (trend_score + macd_score + smc_score + ict_score + liq_score + patt_score + bb_score + rsi_score + fib_score + ew_score)

    final_signal = "neutral"
    if confidence > 0:
        final_signal = "bull"
    elif confidence < 0:
        final_signal = "bear"

    signals['SK'] = (f"CONFIDENCE: {abs(confidence)}%", final_signal)

    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    return signals, atr, confidence, score_breakdown

# --- 5. ADVANCED SL/TP CALCULATION USING SMC + ICT + ELLIOTT WAVE + FIBONACCI ---
def calculate_advanced_sl_tp(df, direction, entry, atr, tf_type, signals):
    """
    Calculate SL and TP using SMC, ICT, Elliott Wave, and Fibonacci concepts.
    Compares multiple candidates and selects the optimal level based on confluence and distance.
    """
    # Get recent swing levels (last 5 candles for structure)
    recent_low = df['Low'].tail(5).min()
    recent_high = df['High'].tail(5).max()
    
    # Get recent range for Fibonacci extensions
    recent_range = recent_high - recent_low
    
    # Determine base SL distance from ATR (structure-based)
    if tf_type == 'scalp':
        base_sl_mult = 1.2
    else:
        base_sl_mult = 1.5
    
    atr_distance = atr * base_sl_mult
    
    # --- SL Calculation (compare structure vs ATR) ---
    if direction == "BUY":
        # Structure-based SL: below recent low
        structure_sl = recent_low - (recent_low * 0.001)  # just below recent low
        structure_distance = entry - structure_sl
        # ATR-based SL
        atr_sl = entry - atr_distance
        atr_sl_distance = atr_distance
        # Choose the most conservative SL (largest distance for BUY means lowest price)
        if structure_sl < atr_sl:
            sl = structure_sl
            sl_distance = structure_distance
        else:
            sl = atr_sl
            sl_distance = atr_sl_distance
    else:  # SELL
        structure_sl = recent_high + (recent_high * 0.001)  # just above recent high
        structure_distance = structure_sl - entry
        atr_sl = entry + atr_distance
        atr_sl_distance = atr_distance
        if structure_sl > atr_sl:
            sl = structure_sl
            sl_distance = structure_distance
        else:
            sl = atr_sl
            sl_distance = atr_sl_distance
    
    # --- TP Calculation (compare multiple candidates) ---
    tp_candidates = []
    
    if direction == "BUY":
        # 1. SMC: recent high
        smc_tp = df['High'].tail(20).max()
        tp_candidates.append(smc_tp)
        
        # 2. ICT: Fair Value Gaps above
        for i in range(2, len(df)-1):
            if df['Low'].iloc[i] > df['High'].iloc[i+1]:  # bullish FVG
                fvg_top = df['Low'].iloc[i]  # top of FVG
                if fvg_top > entry:
                    tp_candidates.append(fvg_top)
        
        # 3. Elliott Wave extensions
        ew_status = signals.get('ELLIOTT', ("", "neutral"))[0]
        if "Wave 3" in ew_status:
            # Fibonacci extension 1.618 of recent range
            fib_1618 = recent_high + 1.618 * recent_range
            tp_candidates.append(fib_1618)
        elif "Wave 5" in ew_status:
            # Wave 5 often extends 1.272 of Wave 3
            if len(df) > 100:
                wave3_high = df['High'].tail(100).max()
                fib_1272 = wave3_high + 0.272 * recent_range
                tp_candidates.append(fib_1272)
        
        # 4. Fibonacci extensions from entry
        fib_levels = [1.272, 1.382, 1.618]
        for level in fib_levels:
            fib_tp = entry + level * recent_range
            tp_candidates.append(fib_tp)
        
        # Remove duplicates and sort ascending
        unique_candidates = sorted(set(tp_candidates))
        
        # Select the best TP: closest to entry among those above entry
        valid_candidates = [c for c in unique_candidates if c > entry]
        if valid_candidates:
            tp = min(valid_candidates, key=lambda x: abs(x - entry))
        else:
            tp = entry * 1.02  # fallback
    
    else:  # SELL
        # 1. SMC: recent low
        smc_tp = df['Low'].tail(20).min()
        tp_candidates.append(smc_tp)
        
        # 2. ICT: Fair Value Gaps below
        for i in range(2, len(df)-1):
            if df['High'].iloc[i] < df['Low'].iloc[i+1]:  # bearish FVG
                fvg_bottom = df['High'].iloc[i]  # bottom of FVG
                if fvg_bottom < entry:
                    tp_candidates.append(fvg_bottom)
        
        # 3. Elliott Wave extensions
        ew_status = signals.get('ELLIOTT', ("", "neutral"))[0]
        if "Wave C" in ew_status:
            fib_1618 = recent_low - 1.618 * recent_range
            tp_candidates.append(fib_1618)
        elif "Wave A" in ew_status:
            if len(df) > 100:
                wave_a_low = df['Low'].tail(100).min()
                tp_candidates.append(wave_a_low)
        
        # 4. Fibonacci extensions from entry
        fib_levels = [1.272, 1.382, 1.618]
        for level in fib_levels:
            fib_tp = entry - level * recent_range
            tp_candidates.append(fib_tp)
        
        # Remove duplicates and sort descending
        unique_candidates = sorted(set(tp_candidates), reverse=True)
        
        # Select the best TP: closest to entry among those below entry
        valid_candidates = [c for c in unique_candidates if c < entry]
        if valid_candidates:
            tp = max(valid_candidates, key=lambda x: abs(x - entry))  # closest below entry
        else:
            tp = entry * 0.98  # fallback
    
    return sl, tp

# ==================== AI FUNCTIONS WITH GEMINI FIRST + GROQ + PUTER (KEY ROTATION) ====================

def call_gemini(prompt):
    """Try Gemini API with key rotation (7 keys). Returns response text or None."""
    gemini_keys = []
    for i in range(1, 8):
        k = st.secrets.get(f"GEMINI_API_KEY_{i}")
        if k:
            gemini_keys.append(k)
    
    if not gemini_keys:
        return None
    
    # Try each key in order until one succeeds
    for idx, key in enumerate(gemini_keys):
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-3-flash-preview')
            response = model.generate_content(prompt)
            # Success: return response text
            return response.text
        except Exception as e:
            print(f"Gemini key {idx+1} failed: {e}")
            continue
    return None  # all keys failed

def call_groq(prompt):
    """Try Groq API with key rotation (4 keys). Returns response text or None."""
    groq_keys = []
    for i in range(1, 5):
        key = st.secrets.get(f"GROQ_KEYS_{i}")
        if key:
            groq_keys.append(key)
    
    if not groq_keys:
        return None
    
    for idx, key in enumerate(groq_keys):
        try:
            client = groq.Client(api_key=key)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Groq key {idx+1} failed: {e}")
            continue
    return None

def call_ai_with_fallback(prompt, user_info=None, progress_callback=None):
    """Try Gemini first, then Groq (with key rotation), then Puter, with credit check."""
    # Credit check
    if user_info:
        current_usage = user_info.get("UsageCount", 0)
        max_limit = user_info.get("HybridLimit", 30)
        if current_usage >= max_limit and user_info.get("Role") != "Admin":
            return None, "Daily limit reached (30 credits). Please try again tomorrow."
    
    if progress_callback:
        progress_callback(0.2, "Trying Gemini...")
    # Try Gemini first
    response = call_gemini(prompt)
    if response:
        if user_info and user_info.get("Role") != "Admin":
            new_usage = current_usage + 1
            user_info["UsageCount"] = new_usage
            st.session_state.user = user_info
            update_usage_in_db(user_info["Username"], new_usage)
        if progress_callback:
            progress_callback(1.0, "Gemini response received")
        # Increment total API requests counter
        st.session_state.total_api_requests += 1
        return response, "Gemini 3.0 Flash"
    
    if progress_callback:
        progress_callback(0.4, "Gemini failed, trying Groq...")
    # Try Groq (key rotation)
    response = call_groq(prompt)
    if response:
        if user_info and user_info.get("Role") != "Admin":
            new_usage = current_usage + 1
            user_info["UsageCount"] = new_usage
            st.session_state.user = user_info
            update_usage_in_db(user_info["Username"], new_usage)
        if progress_callback:
            progress_callback(1.0, "Groq response received")
        st.session_state.total_api_requests += 1
        return response, "Groq (llama-3.3-70b-versatile)"
    
    if progress_callback:
        progress_callback(0.7, "Groq failed, trying Puter...")
    # Fallback to Puter
    try:
        puter_resp = puter.ai.chat(prompt)
        if user_info and user_info.get("Role") != "Admin":
            new_usage = current_usage + 1
            user_info["UsageCount"] = new_usage
            st.session_state.user = user_info
            update_usage_in_db(user_info["Username"], new_usage)
        if progress_callback:
            progress_callback(1.0, "Puter response received")
        st.session_state.total_api_requests += 1
        return puter_resp.message.content, "Puter AI (Fallback)"
    except:
        if progress_callback:
            progress_callback(1.0, "All providers failed")
        return None, "All AI providers failed"

def parse_ai_response(text):
    data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A", "FORECAST": "N/A"}
    try:
        entry_match = re.search(r"ENTRY\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        sl_match = re.search(r"SL\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        tp_match = re.search(r"TP\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        forecast_match = re.search(r"FORECAST\s*[:=]\s*(.*?)(?=\n|$)", text, re.IGNORECASE | re.DOTALL)
        
        if entry_match:
            val = entry_match.group(1).strip().rstrip('.,')
            if val:
                data["ENTRY"] = val
        if sl_match:
            val = sl_match.group(1).strip().rstrip('.,')
            if val:
                data["SL"] = val
        if tp_match:
            val = tp_match.group(1).strip().rstrip('.,')
            if val:
                data["TP"] = val
        if forecast_match:
            data["FORECAST"] = forecast_match.group(1).strip()
    except:
        pass
    return data

def get_ai_trade_setup(pair, primary_tf, direction, current_price, df_hist, news_items, user_info, progress_callback=None):
    """
    Get AI-generated trade setup including entry, SL, TP, confidence, forecast, confirmation,
    and a short Sinhala summary. Now includes multi-timeframe analysis.
    """
    if df_hist is None or df_hist.empty:
        return None
    
    if progress_callback:
        progress_callback(0.1, "Calculating market stats...")
    # Calculate some basic stats for prompt
    high_52w = df_hist['High'].tail(252).max() if len(df_hist) > 252 else df_hist['High'].max()
    low_52w = df_hist['Low'].tail(252).min() if len(df_hist) > 252 else df_hist['Low'].min()
    atr = (df_hist['High'] - df_hist['Low']).rolling(14).mean().iloc[-1]
    
    news_str = "\n".join([f"- {n['title']}" for n in news_items]) if news_items else "No recent news."
    
    # --- Multi-Timeframe Analysis ---
    if progress_callback:
        progress_callback(0.2, "Performing multi-timeframe analysis...")
    symbol_orig = clean_pair_to_yf_symbol(pair)
    timeframes = ["15m", "1h", "4h", "1d"]
    tf_signals = {}
    for tf in timeframes:
        period_map = {"15m": "1mo", "1h": "3mo", "4h": "6mo", "1d": "1y"}
        try:
            df_tf = get_cached_historical_data(get_yf_symbol(symbol_orig), tf, period=period_map[tf])
            if df_tf is not None and len(df_tf) > 50:
                sigs, _, conf, _ = calculate_advanced_signals(df_tf, tf, news_items=None)
                if sigs:
                    tf_signals[tf] = {
                        "trend": sigs['TREND'][0],
                        "signal": sigs['SK'][1].upper(),
                        "confidence": abs(conf)
                    }
        except Exception as e:
            print(f"Error fetching {tf} data for {pair}: {e}")
            continue
    
    mtf_summary = ""
    if tf_signals:
        mtf_summary = "\n**Multi-Timeframe Analysis:**\n"
        for tf, sig in tf_signals.items():
            mtf_summary += f"- {tf}: {sig['signal']} (Conf: {sig['confidence']}%), Trend: {sig['trend']}\n"
    else:
        mtf_summary = "\n**Multi-Timeframe Analysis:** Insufficient data for other timeframes.\n"
    
    prompt = f"""
    Act as a Senior Hedge Fund Risk Manager & Technical Analyst.
    Analyze {pair} on {primary_tf} timeframe for a potential {direction} trade.
    
    **Current Market Data:**
    - Current Price: {current_price:.5f}
    - 52-Week High: {high_52w:.5f}
    - 52-Week Low: {low_52w:.5f}
    - ATR (14): {atr:.5f}
    
    **Recent News Headlines:**
    {news_str}
    {mtf_summary}
    **Task:**
    1. Determine if a {direction} trade is valid based on technical and fundamental analysis, considering the multi-timeframe context.
    2. Provide precise Entry, Stop Loss, and Take Profit levels.
    3. Use concepts like support/resistance, Fibonacci, and recent swings to set logical SL/TP.
    4. Ensure risk-reward ratio is at least 1:2 for scalp, 1:3 for swing.
    5. Provide a confidence percentage (0-100%).
    6. Give a short-term price forecast (next 5-10 candles).
    7. Finally, give a CONFIRMATION decision: APPROVE or REJECT the trade setup with a brief reason.
    8. Provide a very short summary in SINHALA language (1 sentence) of this trade setup.
    
    **FINAL OUTPUT FORMAT (STRICT):**
    CONFIDENCE: XX%
    ENTRY: xxxxx
    SL: xxxxx
    TP: xxxxx
    FORECAST: [Brief forecast description]
    SINHALA_SUMMARY: [One sentence in Sinhala]
    CONFIRMATION: APPROVE/REJECT
    REASON: [Short reason]
    """
    
    if progress_callback:
        progress_callback(0.3, "Calling AI...")
    response, provider = call_ai_with_fallback(prompt, user_info, progress_callback)
    if not response:
        return None
    
    parsed = parse_ai_response(response)
    
    # Extract confidence
    conf_match = re.search(r"CONFIDENCE\s*[:=]\s*(\d+)", response, re.IGNORECASE)
    confidence = int(conf_match.group(1)) if conf_match else 50
    
    # Extract confirmation and reason
    confirm_match = re.search(r"CONFIRMATION\s*:\s*(APPROVE|REJECT)", response, re.IGNORECASE)
    reason_match = re.search(r"REASON\s*:\s*(.+)", response, re.IGNORECASE)
    confirmation = confirm_match.group(1).upper() if confirm_match else "N/A"
    reason = reason_match.group(1).strip() if reason_match else ""
    
    # Extract Sinhala summary
    sinhala_match = re.search(r"SINHALA_SUMMARY\s*:\s*(.+)", response, re.IGNORECASE)
    sinhala_summary = sinhala_match.group(1).strip() if sinhala_match else ""
    
    if progress_callback:
        progress_callback(1.0, "Done")
    
    # --- Entry Optimization (compare AI entry with OB/FVG) ---
    # Get signals for current timeframe to find best entry levels
    sigs, _, _, _ = calculate_advanced_signals(df_hist, primary_tf, news_items)
    
    optimized_entry = None
    entry_source = "AI"
    
    if direction == "BUY":
        # Look for bullish OB or FVG near AI entry
        best_level = None
        best_distance = float('inf')
        
        # Check recent bullish order blocks (last 10 candles)
        for i in range(10, len(df_hist)-1):
            # Simple OB detection: bearish candle followed by bullish breakout
            if df_hist['Close'].iloc[i-1] < df_hist['Open'].iloc[i-1]:  # bearish candle
                if df_hist['Close'].iloc[i] > df_hist['High'].iloc[i-1]:  # breakout
                    ob_level = df_hist['High'].iloc[i-1]  # top of OB
                    if ob_level < current_price * 1.01:  # within 1% of current price
                        dist = abs(ob_level - float(parsed["ENTRY"]) if parsed["ENTRY"] != "N/A" else current_price)
                        if dist < best_distance:
                            best_distance = dist
                            best_level = ob_level
        
        # Check FVGs
        for i in range(2, len(df_hist)-1):
            if df_hist['Low'].iloc[i] > df_hist['High'].iloc[i+1]:  # bullish FVG
                fvg_level = df_hist['Low'].iloc[i]  # top of FVG
                if fvg_level < current_price * 1.01:
                    dist = abs(fvg_level - float(parsed["ENTRY"]) if parsed["ENTRY"] != "N/A" else current_price)
                    if dist < best_distance:
                        best_distance = dist
                        best_level = fvg_level
        
        if best_level and best_distance < (current_price * 0.002):  # within 0.2%
            optimized_entry = best_level
            entry_source = "SMC/ICT"
    
    else:  # SELL
        best_level = None
        best_distance = float('inf')
        
        # Bearish order blocks
        for i in range(10, len(df_hist)-1):
            if df_hist['Close'].iloc[i-1] > df_hist['Open'].iloc[i-1]:  # bullish candle
                if df_hist['Close'].iloc[i] < df_hist['Low'].iloc[i-1]:  # breakdown
                    ob_level = df_hist['Low'].iloc[i-1]  # bottom of OB
                    if ob_level > current_price * 0.99:
                        dist = abs(ob_level - float(parsed["ENTRY"]) if parsed["ENTRY"] != "N/A" else current_price)
                        if dist < best_distance:
                            best_distance = dist
                            best_level = ob_level
        
        # Bearish FVGs
        for i in range(2, len(df_hist)-1):
            if df_hist['High'].iloc[i] < df_hist['Low'].iloc[i+1]:  # bearish FVG
                fvg_level = df_hist['High'].iloc[i]  # bottom of FVG
                if fvg_level > current_price * 0.99:
                    dist = abs(fvg_level - float(parsed["ENTRY"]) if parsed["ENTRY"] != "N/A" else current_price)
                    if dist < best_distance:
                        best_distance = dist
                        best_level = fvg_level
        
        if best_level and best_distance < (current_price * 0.002):
            optimized_entry = best_level
            entry_source = "SMC/ICT"
    
    # Use optimized entry if found, otherwise use AI entry
    final_entry = optimized_entry if optimized_entry is not None else (float(parsed["ENTRY"]) if parsed["ENTRY"] != "N/A" else current_price)
    
    # TP optimization (using the new calculate_advanced_sl_tp)
    tf_type = 'scalp' if 'scalp' in primary_tf.lower() or '15m' in primary_tf else 'swing'
    sl, tp = calculate_advanced_sl_tp(df_hist, direction, final_entry, atr, tf_type, sigs)
    
    # Override AI SL/TP with optimized ones
    final_sl = sl
    final_tp = tp
    
    trade = {
        "pair": pair,
        "tf": primary_tf,
        "dir": direction,
        "entry": final_entry,
        "sl": final_sl,
        "tp": final_tp,
        "conf": confidence,
        "price": current_price,
        "live_price": get_live_price(pair) or current_price,
        "symbol_orig": symbol_orig,
        "forecast": parsed["FORECAST"],
        "confirmation": confirmation,
        "reason": reason,
        "provider": provider,
        "sinhala_summary": sinhala_summary,
        "entry_source": entry_source  # for debugging/info
    }
    return trade

# --- 6. INFINITE ALGORITHMIC ENGINE (UPDATED WITH SMC/ICT/ELLIOTT SL/TP) ---
def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr, tf, df):
    if sigs is None:
        return "Insufficient Data for Analysis"
    
    confidence = sigs['SK'][0]
    signal_dir = sigs['SK'][1]
    trend = sigs['TREND'][0]
    
    if tf in ["1m", "5m"]:
        trade_mode = "SCALPING (වේගවත්)"
        tf_type = 'scalp'
    else:
        trade_mode = "SWING (දිගු කාලීන)"
        tf_type = 'swing'

    action = "WAIT"
    status_sinhala = "ප්‍රවේශම් වන්න. වෙළඳපල අවිනිශ්චිතයි."
    sl, tp = 0, 0
    
    if signal_dir == "bull":
        action = "BUY"
        status_sinhala = "වෙළඳපල ගැනුම්කරුවන් අත. (Market is Bullish)"
        sl, tp = calculate_advanced_sl_tp(df, "BUY", curr_p, atr, tf_type, sigs)
    elif signal_dir == "bear":
        action = "SELL"
        status_sinhala = "වෙළඳපල විකුණුම්කරුවන් අත. (Market is Bearish)"
        sl, tp = calculate_advanced_sl_tp(df, "SELL", curr_p, atr, tf_type, sigs)

    analysis_text = f"""
    ♾️ **INFINITE ALGO ENGINE V27.0 (AI-POWERED SCANNER)**
    
    📊 **වෙළඳපල විශ්ලේෂණය ({tf}):**
    • Trade Type: {trade_mode}
    • Signal Confidence: {confidence}
    • Action: {action}
    • Trend: {trend}
    • Liquidity: {sigs['LIQ'][0]}
    
    💡 **නිගමනය:**
    {status_sinhala}
    
    DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}
    """
    return analysis_text

# --- 7. HYBRID AI ENGINE WITH CONFIRMATION (uses new AI call) ---
def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info, tf, df):
    if sigs is None:
        return "Error: Insufficient Signal Data", "System Error", None, None
    
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr, tf, df)
    
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 30)
    
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return algo_result, "Infinite Algo (Limit Reached)", None, None

    news_str = "\n".join([f"- {n['title']}" for n in news_items])

    prompt = f"""
    Act as a Senior Hedge Fund Risk Manager & Technical Analyst.
    Analyze {pair} on {tf} timeframe.
    
    **Current Technical Signals:**
    - Trend: {sigs['TREND'][0]}
    - SMC Structure: {sigs['SMC'][0]}
    - RSI/Retail: {sigs['RSI'][0]}
    - Algo Signal: {sigs['SK'][1].upper()} (Confidence: {sigs['SK'][0]})
    - ICT FVG: {sigs['ICT'][0]}
    
    **Recent News Headlines:**
    {news_str}
    
    **Task:**
    1. VERIFY the Algo Signal against the News. If news is highly negative but signal is Buy, WARN the user.
    2. Use SMC, Fibonacci, and Liquidity concepts to confirm the best entry.
    3. Output the explanation in SINHALA language (Technical terms in English).
    4. Provide strict ENTRY, SL, TP based on ATR ({atr:.5f}) and Support/Resistance.
    5. Additionally, provide a short-term price forecast (next 5-10 candles) in terms of direction and approximate targets.
    6. **Crucially, give a final CONFIRMATION decision** – either APPROVE or REJECT the trade setup, with a brief reason.
    
    **FINAL OUTPUT FORMAT (STRICT):**
    [Sinhala Verification & Explanation Here]
    
    DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx
    FORECAST: [Brief forecast description]
    CONFIRMATION: APPROVE/REJECT
    REASON: [Short reason in English or Sinhala]
    """

    response, provider = call_ai_with_fallback(prompt, user_info)
    
    if response:
        new_usage = current_usage + 1
        user_info["UsageCount"] = new_usage
        st.session_state.user = user_info
        if user_info["Username"] != "Admin":
            update_usage_in_db(user_info["Username"], new_usage)

        confirm_match = re.search(r"CONFIRMATION\s*:\s*(APPROVE|REJECT)", response, re.IGNORECASE)
        reason_match = re.search(r"REASON\s*:\s*(.+)", response, re.IGNORECASE)
        confirmation = confirm_match.group(1).upper() if confirm_match else "N/A"
        reason = reason_match.group(1).strip() if reason_match else ""

        return response, f"{provider} | Used: {new_usage}/{max_limit}", confirmation, reason
    else:
        return algo_result, "Infinite Algo (Default)", None, None

# ==================== DEEP ANALYSIS FUNCTION (HYBRID ENGINE) WITH MULTI-TIMEFRAME ====================
def get_deep_hybrid_analysis(trade, user_info, df_hist_original):
    """Run deep analysis with confirmation for scanner trade, incorporating multi-timeframe signals."""
    pair = trade['pair']
    symbol_orig = trade.get('symbol_orig', clean_pair_to_yf_symbol(pair))
    
    news_items = get_market_news(symbol_orig)
    news_str = "\n".join([f"- {n['title']}" for n in news_items])
    
    live_price = trade.get('live_price', trade['price'])
    tf_display = trade['tf']
    
    # Fetch data for multiple timeframes
    timeframes = ["15m", "1h", "4h", "1d"]
    tf_signals = {}
    for tf in timeframes:
        period_map = {"15m": "1mo", "1h": "3mo", "4h": "6mo", "1d": "1y"}
        try:
            df_tf = get_cached_historical_data(get_yf_symbol(symbol_orig), tf, period=period_map[tf])
            if df_tf is not None and len(df_tf) > 50:
                sigs, _, _, _ = calculate_advanced_signals(df_tf, tf, news_items=None)
                if sigs:
                    tf_signals[tf] = {
                        "trend": sigs['TREND'][0],
                        "smc": sigs['SMC'][0],
                        "rsi": sigs['RSI'][0],
                        "signal": sigs['SK'][1].upper(),
                        "confidence": sigs['SK'][0]
                    }
        except Exception as e:
            print(f"Error fetching {tf} data for {pair}: {e}")
    
    # Build multi-timeframe summary
    mtf_summary = ""
    for tf, sig in tf_signals.items():
        mtf_summary += f"- {tf}: {sig['signal']} (Conf: {sig['confidence']}), Trend: {sig['trend']}\n"
    
    prompt = f"""
    Act as a Senior Hedge Fund Risk Manager & Technical Analyst.
    Perform a deep analysis of the following trade setup:
    
    **Asset:** {pair}
    **Timeframe:** {tf_display}
    **Direction:** {trade['dir']}
    **Entry:** {trade['entry']:.5f}
    **Stop Loss:** {trade['sl']:.5f}
    **Take Profit:** {trade['tp']:.5f}
    **Confidence:** {trade['conf']}%
    **Current Live Price:** {live_price:.5f}
    
    **Multi-Timeframe Analysis:**
    {mtf_summary}
    
    **Recent News Headlines:**
    {news_str}
    
    **Task:**
    1. Evaluate the risk-reward ratio of this trade.
    2. Check if the current price is near entry and if it's a good moment to enter.
    3. Provide a detailed analysis in SINHALA (use English for technical terms).
    4. Suggest any adjustments to SL/TP based on recent price action.
    5. Give a short-term price forecast (next 5-10 candles) in terms of direction and approximate targets.
    6. **Provide a final CONFIRMATION decision** – APPROVE or REJECT this trade, with a short reason.
    
    **FINAL OUTPUT FORMAT (STRICT):**
    [Sinhala Analysis]
    
    RISK:REWARD = x:y
    FORECAST: [Brief forecast description]
    CONFIRMATION: APPROVE/REJECT
    REASON: [Short reason]
    """
    
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 30)
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return "Daily limit reached. Please try again tomorrow.", "Limit Reached", None, None
    
    response, provider = call_ai_with_fallback(prompt, user_info)
    
    if response:
        new_usage = current_usage + 1
        user_info["UsageCount"] = new_usage
        st.session_state.user = user_info
        if user_info["Username"] != "Admin":
            update_usage_in_db(user_info["Username"], new_usage)

        confirm_match = re.search(r"CONFIRMATION\s*:\s*(APPROVE|REJECT)", response, re.IGNORECASE)
        reason_match = re.search(r"REASON\s*:\s*(.+)", response, re.IGNORECASE)
        confirmation = confirm_match.group(1).upper() if confirm_match else "N/A"
        reason = reason_match.group(1).strip() if reason_match else ""

        return response, f"{provider} | Used: {new_usage}/{max_limit}", confirmation, reason
    else:
        return "Deep analysis failed.", "Error", None, None

# ==================== BACKTEST FUNCTION (CORRECTED) ====================
def run_backtest(market_choice, start_date, end_date, min_accuracy, user_info, assets_dict):
    """
    Run backtest over historical data.
    For each asset in selected market, for each day in range (or each candle), simulate trades.
    Uses same logic as scan_market_with_ai but on historical data up to that point.
    This is simplified: we only check signals at the end of each day (using daily data) to avoid too many AI calls.
    For performance, we limit to last 30 days and use daily timeframe.
    """
    assets_list = []
    if market_choice == "All":
        assets_list = assets_dict["Forex"] + assets_dict["Crypto"] + assets_dict["Metals"]
    else:
        assets_list = assets_dict[market_choice]
    
    # For simplicity, use daily timeframe for backtest
    interval = "1d"
    # Convert dates to datetime
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())
    
    results = []
    total_trades = 0
    winning_trades = 0
    total_profit = 0.0
    
    progress_bar = st.progress(0, text="Running backtest...")
    total_assets = len(assets_list)
    
    for idx, symbol in enumerate(assets_list):
        progress_bar.progress((idx+1)/total_assets, text=f"Backtesting {symbol}...")
        try:
            # Fetch historical data for the entire period
            df = get_cached_historical_data(get_yf_symbol(symbol), interval, start=start, end=end)
            if df is None or len(df) < 10:
                continue
            
            # For each day, we could simulate a trade if signal appears
            # To avoid too many AI calls, we'll only consider the last bar of each day (which is the daily close)
            # Actually, with daily data, each row is a day. We'll loop through rows and check signal at each day's close.
            # But that would be many AI calls. Let's limit to last 30 days.
            df = df.tail(30)  # last 30 days
            for i in range(len(df)-1):  # we need next day's price to simulate exit
                row = df.iloc[i]
                current_price = row['Close']
                # Get signals using data up to this point (including current row)
                df_up_to_now = df.iloc[:i+1].copy()
                if len(df_up_to_now) < 50:
                    continue
                sigs, atr, conf, _ = calculate_advanced_signals(df_up_to_now, interval, news_items=None)
                if sigs and abs(conf) > min_accuracy:
                    direction = "BUY" if conf > 0 else "SELL"
                    # Get AI trade setup using data up to now
                    news_items = get_market_news(symbol)  # note: news is current, not historical
                    # We'll use current news as approximation (hard to get historical news)
                    # For backtest, we pass user_info (which may be None) but get_ai_trade_setup handles it
                    ai_trade = get_ai_trade_setup(
                        clean_pair_to_yf_symbol(symbol).replace("=X","").replace("-USD","").replace("-USDT",""),
                        interval,
                        direction,
                        current_price,
                        df_up_to_now,
                        news_items,
                        user_info  # Pass the current user_info (may be None, but function handles)
                    )
                    if ai_trade and ai_trade['confirmation'] == "APPROVE":
                        # Simulate trade: enter at next day's open? For simplicity, enter at current close, exit at next close.
                        next_row = df.iloc[i+1]
                        exit_price = next_row['Close']
                        if direction == "BUY":
                            profit = (exit_price - ai_trade['entry']) / ai_trade['entry']
                        else:
                            profit = (ai_trade['entry'] - exit_price) / ai_trade['entry']
                        total_trades += 1
                        if profit > 0:
                            winning_trades += 1
                        total_profit += profit
                        results.append({
                            "symbol": symbol,
                            "date": row.name,
                            "direction": direction,
                            "entry": ai_trade['entry'],
                            "exit": exit_price,
                            "profit_pct": profit * 100,
                            "confidence": ai_trade['conf']
                        })
        except Exception as e:
            print(f"Backtest error for {symbol}: {e}")
            continue
    
    progress_bar.empty()
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    # Simplified profit factor (total profit / absolute total profit) - not accurate, but placeholder
    profit_factor = total_profit / abs(total_profit) if total_profit != 0 else 0
    
    return {
        "results": results,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "win_rate": win_rate,
        "total_profit_pct": total_profit * 100,
        "profit_factor": profit_factor
    }

# ==================== SESSION DETECTION ====================
def get_current_session():
    """Return the current trading session based on UTC time."""
    now_utc = datetime.now(pytz.utc)
    hour = now_utc.hour
    if 0 <= hour < 8:
        return "Asia"
    elif 8 <= hour < 16:
        return "London"
    elif 16 <= hour < 24:
        return "New York"
    else:
        return "Other"

# ==================== SCAN FUNCTION WITH AI ANALYSIS (MULTI-TIMEFRAME) ====================
def scan_market_with_ai(assets_list, user_info, timeframes, min_accuracy=40):
    """
    Scan market for setups across multiple timeframes using AI analysis for each candidate.
    Automatically saves trades to Ongoing Trades if approved by AI, but only if not already tracked.
    Returns a flat list of trades, each with a 'timeframe' field.
    """
    all_trades = []
    
    # Progress bars for each timeframe
    progress_bars = {}
    for tf in timeframes:
        progress_bars[tf] = st.progress(0, text=f"Scanning {tf}...")
    
    total_assets = len(assets_list)
    
    for idx, symbol in enumerate(assets_list):
        # Update progress for each timeframe
        for tf in timeframes:
            progress_bars[tf].progress((idx+1)/total_assets, text=f"Scanning {symbol} on {tf}...")
        
        try:
            # For each timeframe, fetch data and analyze
            for tf in timeframes:
                period = get_period_for_tf(tf)
                df = get_cached_historical_data(get_yf_symbol(symbol), tf, period=period)
                if df is None or len(df) < 50:
                    continue
                
                # Use algorithmic signals to get direction and confidence quickly
                sigs, atr, conf, _ = calculate_advanced_signals(df, tf, news_items=None)
                if sigs and abs(conf) > min_accuracy:
                    clean_sym = symbol.replace("=X","").replace("-USD","").replace("-USDT","")
                    direction = "BUY" if conf > 0 else "SELL"
                    curr_price = df['Close'].iloc[-1]
                    
                    # Get AI analysis for this candidate
                    news_items = get_market_news(symbol)
                    ai_trade = get_ai_trade_setup(
                        clean_sym,
                        f"{tf} (Auto)",
                        direction,
                        curr_price,
                        df,
                        news_items,
                        user_info
                    )
                    if ai_trade and ai_trade['confirmation'] == "APPROVE":
                        # Add timeframe to trade dict for display
                        ai_trade['timeframe'] = tf
                        # Check if already tracked (using pair, timeframe, direction, entry)
                        trade_id = f"{clean_sym}_{tf}_{direction}_{ai_trade['entry']:.5f}"
                        if trade_id not in st.session_state.tracked_trades:
                            if save_trade_to_ongoing(ai_trade, user_info['Username']):
                                st.session_state.tracked_trades.add(trade_id)
                                all_trades.append(ai_trade)
        except Exception as e:
            print(f"Error scanning {symbol}: {e}")
            continue
    
    # Clear all progress bars
    for tf in timeframes:
        progress_bars[tf].empty()
    
    return all_trades

# --- FORECAST CHART FUNCTION (unchanged) ---
def create_forecast_chart(historical_df, entry_price, sl, tp, forecast_text):
    hist = historical_df.tail(30).copy()
    last_date = hist.index[-1]
    if isinstance(last_date, pd.Timestamp):
        if len(hist) > 1:
            deltas = hist.index.to_series().diff().dropna()
            median_delta = deltas.median()
            if pd.isna(median_delta) or median_delta.total_seconds() == 0:
                total_seconds = (hist.index[-1] - hist.index[0]).total_seconds()
                avg_seconds = total_seconds / (len(hist)-1) if len(hist) > 1 else 3600
                median_delta = timedelta(seconds=avg_seconds)
        else:
            median_delta = timedelta(hours=1)
        future_dates = [last_date + (i+1)*median_delta for i in range(15)]
    else:
        future_dates = list(range(len(hist), len(hist)+15))
    
    if tp > entry_price:
        target = tp
        direction = "bullish"
    else:
        target = tp
        direction = "bearish"
    
    forecast_prices = np.linspace(entry_price, target, len(future_dates))
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=hist.index,
        open=hist['Open'],
        high=hist['High'],
        low=hist['Low'],
        close=hist['Close'],
        name='Historical',
        showlegend=True
    ))
    fig.add_trace(go.Scatter(
        x=future_dates,
        y=forecast_prices,
        mode='lines+markers',
        name=f'Forecast ({direction})',
        line=dict(color='#00ff99', width=3, dash='dot'),
        marker=dict(size=5, color='#00ff99', symbol='circle')
    ))
    fig.add_hline(y=entry_price, line_dash="dashdot", line_color="#ffff00",
                  annotation_text="Entry", annotation_position="bottom right")
    fig.add_hline(y=sl, line_dash="dash", line_color="#ff4b4b",
                  annotation_text="SL", annotation_position="bottom right")
    fig.add_hline(y=tp, line_dash="dash", line_color="#00ff00",
                  annotation_text="TP", annotation_position="top right")
    
    if forecast_text and forecast_text != 'N/A':
        fig.add_annotation(
            x=future_dates[-1] if future_dates else hist.index[-1],
            y=forecast_prices[-1],
            text=forecast_text,
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor="#00ff99",
            font=dict(size=12, color="white"),
            bgcolor="#1e1e1e",
            bordercolor="#00ff99",
            borderwidth=1,
            borderpad=4,
            ax=20,
            ay=-30
        )
    
    fig.update_layout(
        title=f"AI Forecast & Projection ({direction.capitalize()})",
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis_title="Time",
        yaxis_title="Price",
        hovermode="x unified",
        xaxis=dict(
            rangeslider=dict(visible=False),
            type='date' if isinstance(last_date, pd.Timestamp) else 'linear'
        )
    )
    return fig

# NEW: Small chart for trade card
def create_mini_chart(df, entry_price, sl, tp):
    """Create a small line chart for trade card."""
    hist = df.tail(20).copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist.index,
        y=hist['Close'],
        mode='lines',
        line=dict(color='#00ff99', width=2),
        name='Price'
    ))
    fig.add_hline(y=entry_price, line_dash="dash", line_color="#ffff00", line_width=1)
    fig.add_hline(y=sl, line_dash="dash", line_color="#ff4b4b", line_width=1)
    fig.add_hline(y=tp, line_dash="dash", line_color="#00ff00", line_width=1)
    fig.update_layout(
        template="plotly_dark",
        height=100,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(showticklabels=False, showgrid=False)
    )
    return fig

# NEW: Technical chart with multiple indicators
def create_technical_chart(df, tf):
    """Create a multi-panel chart with indicators."""
    # Calculate indicators
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    df['BB_upper'] = df['Close'].rolling(20).mean() + 2*df['Close'].rolling(20).std()
    df['BB_lower'] = df['Close'].rolling(20).mean() - 2*df['Close'].rolling(20).std()
    
    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['Signal']
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Support/Resistance (last 20 days high/low)
    recent_high = float(df['High'].tail(20).max())
    recent_low = float(df['Low'].tail(20).min())
    
    # Fibonacci levels from last swing high/low (simplified: use recent_high and recent_low)
    fib_levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
    fib_prices = [recent_low + (recent_high - recent_low) * level for level in fib_levels]
    
    # Create subplots
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True,
                        vertical_spacing=0.05,
                        row_heights=[0.5, 0.15, 0.15, 0.2],
                        subplot_titles=('Price & Indicators', 'MACD', 'RSI', 'Volume'))
    
    # Price candlesticks
    fig.add_trace(go.Candlestick(x=df.index,
                                 open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'],
                                 name='Price'), row=1, col=1)
    # Moving averages
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], line=dict(color='orange', width=1), name='MA50'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], line=dict(color='blue', width=1), name='MA200'), row=1, col=1)
    # Bollinger Bands
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_upper'], line=dict(color='gray', width=1, dash='dash'), name='BB Upper'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_lower'], line=dict(color='gray', width=1, dash='dash'), name='BB Lower'), row=1, col=1)
    
    # Support/Resistance lines using add_shape (more robust)
    fig.add_shape(
        type="line",
        x0=df.index[0], x1=df.index[-1],
        y0=recent_high, y1=recent_high,
        line=dict(color="red", width=1, dash="dot"),
        row=1, col=1
    )
    fig.add_shape(
        type="line",
        x0=df.index[0], x1=df.index[-1],
        y0=recent_low, y1=recent_low,
        line=dict(color="green", width=1, dash="dot"),
        row=1, col=1
    )
    # Add annotation manually
    fig.add_annotation(
        x=df.index[-1], y=recent_high,
        text="Resistance", showarrow=False,
        xshift=10, yshift=10,
        font=dict(color="red"), row=1, col=1
    )
    fig.add_annotation(
        x=df.index[-1], y=recent_low,
        text="Support", showarrow=False,
        xshift=10, yshift=-10,
        font=dict(color="green"), row=1, col=1
    )
    
    # Fibonacci levels
    for price in fib_prices:
        fig.add_shape(
            type="line",
            x0=df.index[0], x1=df.index[-1],
            y0=price, y1=price,
            line=dict(color="purple", width=0.5, dash="dot"),
            opacity=0.3,
            row=1, col=1
        )
    
    # MACD
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue'), name='MACD'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='orange'), name='Signal'), row=2, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['MACD_hist'], marker_color='gray', name='Histogram'), row=2, col=1)
    
    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=3, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=70, y1=70,
                  line=dict(color="red", dash="dash"), row=3, col=1)
    fig.add_shape(type="line", x0=df.index[0], x1=df.index[-1], y0=30, y1=30,
                  line=dict(color="green", dash="dash"), row=3, col=1)
    
    # Volume
    colors = ['red' if close < open else 'green' for close, open in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='Volume'), row=4, col=1)
    
    fig.update_layout(height=800, template='plotly_dark', showlegend=False)
    fig.update_xaxes(rangeslider_visible=False)
    return fig



# NEW: Theory Chart (SMC, ICT, Liquidity, Support/Resistance, Fibonacci, Elliott Wave) - FINAL CORRECTED VERSION
def create_theory_chart(df, tf):
    """Create a simplified chart showing SMC/ICT concepts, liquidity levels, Fibonacci, and Elliott Wave labels."""
    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(x=df.index,
                                 open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'],
                                 name='Price', showlegend=False))

    # Convert index to numeric timestamps (milliseconds) for vrect
    if isinstance(df.index, pd.DatetimeIndex):
        ts = {idx: idx.timestamp() * 1000 for idx in df.index}
    else:
        ts = {idx: i for i, idx in enumerate(df.index)}  # fallback to integer positions

    # Identify swing highs and lows using a simple peak/trough detection with a window of 5 candles
    window = 5
    swing_highs = []
    swing_lows = []
    for i in range(window, len(df)-window):
        high_window = df['High'].iloc[i-window:i+window+1].tolist()
        low_window = df['Low'].iloc[i-window:i+window+1].tolist()
        current_high = float(df['High'].iloc[i])
        current_low = float(df['Low'].iloc[i])
        
        if np.isclose(current_high, max(high_window)):
            swing_highs.append((df.index[i], current_high))
        if np.isclose(current_low, min(low_window)):
            swing_lows.append((df.index[i], current_low))

    # Plot swing points as markers
    if swing_highs:
        fig.add_trace(go.Scatter(x=[x[0] for x in swing_highs], y=[x[1] for x in swing_highs],
                                  mode='markers', marker=dict(color='red', size=5, symbol='triangle-down'),
                                  name='Swing High', showlegend=True))
    if swing_lows:
        fig.add_trace(go.Scatter(x=[x[0] for x in swing_lows], y=[x[1] for x in swing_lows],
                                  mode='markers', marker=dict(color='green', size=5, symbol='triangle-up'),
                                  name='Swing Low', showlegend=True))

    # Liquidity levels: horizontal lines at recent highs/lows (last 20 periods)
    recent_high = float(df['High'].tail(20).max())
    recent_low = float(df['Low'].tail(20).min())
    fig.add_hline(y=recent_high, line_dash="dot", line_color="orange", annotation_text="Resistance", annotation_position="top right")
    fig.add_hline(y=recent_low, line_dash="dot", line_color="blue", annotation_text="Support", annotation_position="bottom right")

    # Fibonacci retracement from last major swing (using highest high and lowest low in last 50 candles)
    high_50 = df['High'].tail(50).max()
    low_50 = df['Low'].tail(50).min()
    if high_50 > low_50:
        fib_levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]
        for level in fib_levels:
            price = low_50 + (high_50 - low_50) * level
            fig.add_hline(y=price, line_dash="dash", line_color="purple", opacity=0.3,
                          annotation_text=f"Fib {level*100:.1f}%", annotation_position="right")

    # Elliott Wave: simple labeling using the detected swing points (alternating)
    swings = sorted(swing_highs + swing_lows, key=lambda x: x[0])
    if len(swings) > 3:
        labels = ['1', '2', '3', '4', '5']
        for i, (idx, price) in enumerate(swings[-5:]):
            if i < len(labels):
                fig.add_annotation(x=idx, y=price, text=labels[i],
                                   showarrow=True, arrowhead=1, ax=0, ay=-20 if i%2==0 else 20,
                                   font=dict(color='cyan', size=12))

    # Fair Value Gaps (ICT) - simplified: highlight gaps between candles
    for i in range(1, len(df)-1):
        if df['Low'].iloc[i] > df['High'].iloc[i+1]:  # bullish gap
            fig.add_vrect(x0=ts[df.index[i]], x1=ts[df.index[i+1]], 
                          fillcolor="green", opacity=0.1, line_width=0,
                          annotation_text="FVG", annotation_position="top")
        elif df['High'].iloc[i] < df['Low'].iloc[i+1]:  # bearish gap
            fig.add_vrect(x0=ts[df.index[i]], x1=ts[df.index[i+1]], 
                          fillcolor="red", opacity=0.1, line_width=0,
                          annotation_text="FVG", annotation_position="bottom")

    # Order Blocks (SMC) - simplified: mark strong candles
    for i in range(2, len(df)):
        # Bullish OB: previous candle bearish, current strong bullish
        if df['Close'].iloc[i-2] < df['Open'].iloc[i-2] and df['Close'].iloc[i] > df['Open'].iloc[i] and df['Close'].iloc[i] > df['High'].iloc[i-2]:
            fig.add_vrect(x0=ts[df.index[i-2]], x1=ts[df.index[i-1]], 
                          fillcolor="blue", opacity=0.2, line_width=0,
                          annotation_text="OB", annotation_position="top")
        # Bearish OB
        if df['Close'].iloc[i-2] > df['Open'].iloc[i-2] and df['Close'].iloc[i] < df['Open'].iloc[i] and df['Close'].iloc[i] < df['Low'].iloc[i-2]:
            fig.add_vrect(x0=ts[df.index[i-2]], x1=ts[df.index[i-1]], 
                          fillcolor="orange", opacity=0.2, line_width=0,
                          annotation_text="OB", annotation_position="bottom")

    fig.update_layout(title=f"SMC/ICT Theory Chart ({tf})",
                      template="plotly_dark",
                      height=600,
                      xaxis_title="Time",
                      yaxis_title="Price",
                      hovermode="x unified")
    return fig

# ==================== DASHBOARD FUNCTIONS ====================
def get_major_prices():
    """Get live prices for major forex, crypto, and metals."""
    majors = {
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "USDJPY=X",
        "BTC/USD": "BTC-USD",
        "ETH/USD": "ETH-USD",
        "XAU/USD": "XAUUSD=X"
    }
    prices = {}
    for name, sym in majors.items():
        price = get_live_price(sym.replace("=X","").replace("-USD","").replace("-USDT",""))
        prices[name] = price if price else "N/A"
    return prices

# NEW: Dashboard forecast function with market selector
def generate_dashboard_forecast(market, pair_display, tf, user_info):
    """Generate forecast chart for selected pair and timeframe."""
    # Map display name to yfinance symbol based on market
    pair_map = {}
    if market == "Forex":
        pair_map = {
            "EUR/USD": "EURUSD=X",
            "GBP/USD": "GBPUSD=X",
            "USD/JPY": "USDJPY=X",
            "AUD/USD": "AUDUSD=X",
            "USD/CAD": "USDCAD=X",
            "NZD/USD": "NZDUSD=X",
            "USD/CHF": "USDCHF=X",
            # Additional Forex pairs
            "USD/SEK": "USDSEK=X",
            "USD/NOK": "USDNOK=X",
            "USD/TRY": "USDTRY=X",
            "USD/ZAR": "USDZAR=X",
            "EUR/TRY": "EURTRY=X",
            "EUR/SEK": "EURSEK=X",
            "EUR/NOK": "EURNOK=X",
            "GBP/SEK": "GBPSEK=X",
            "GBP/NOK": "GBPNOK=X",
            "AUD/CHF": "AUDCHF=X",
            "CAD/CHF": "CADCHF=X",
            "NZD/CHF": "NZDCHF=X",
            "CHF/JPY": "CHFJPY=X",
            "EUR/HUF": "EURHUF=X",
            "USD/HUF": "USDHUF=X",
            "EUR/PLN": "EURPLN=X",
            "USD/PLN": "USDPLN=X",
            "EUR/CZK": "EURCZK=X",
            "USD/CZK": "USDCZK=X"
        }
    elif market == "Crypto":
        pair_map = {
            "BTC/USD": "BTC-USD",
            "ETH/USD": "ETH-USD",
            "SOL/USD": "SOL-USD",
            "BNB/USD": "BNB-USD",
            "XRP/USD": "XRP-USD",
            "ADA/USD": "ADA-USD",
            "DOGE/USD": "DOGE-USD",
            "MATIC/USD": "MATIC-USD",
            "DOT/USD": "DOT-USD",
            "LINK/USD": "LINK-USD",
            "AVAX/USD": "AVAX-USD",
            "UNI/USD": "UNI-USD",
            "LTC/USD": "LTC-USD",
            "BCH/USD": "BCH-USD",
            # Additional Crypto
            "ALGO/USD": "ALGO-USD",
            "VET/USD": "VET-USD",
            "ICP/USD": "ICP-USD",
            "FIL/USD": "FIL-USD",
            "AAVE/USD": "AAVE-USD",
            "AXS/USD": "AXS-USD",
            "SAND/USD": "SAND-USD",
            "MANA/USD": "MANA-USD",
            "EGLD/USD": "EGLD-USD",
            "THETA/USD": "THETA-USD"
        }
    elif market == "Metals":
        pair_map = {
            "XAU/USD": "XAUUSD=X",
            "XAG/USD": "XAGUSD=X",
            "XPT/USD": "XPTUSD=X",
            "XPD/USD": "XPDUSD=X"
        }
    yf_sym = pair_map.get(pair_display, pair_display)
    clean_pair = yf_sym.replace("=X", "").replace("-USD", "").replace("-USDT", "")
    
    # Determine period based on tf
    period = get_period_for_tf(tf)
    
    # Create a progress bar
    progress_bar = st.progress(0, text="Starting forecast generation...")
    
    def update_progress(progress, text):
        progress_bar.progress(progress, text=text)
    
    try:
        update_progress(0.1, "Downloading data...")
        df = get_cached_historical_data(yf_sym, tf, period=period)
        if df is None or len(df) < 50:
            progress_bar.empty()
            return None, "Insufficient data", None
        
        update_progress(0.3, "Calculating signals...")
        current_price = df['Close'].iloc[-1]
        # Get simple signal direction
        sigs, atr, conf, _ = calculate_advanced_signals(df, tf, news_items=None)
        direction = "BUY" if conf > 0 else "SELL" if conf < 0 else "NEUTRAL"
        if direction == "NEUTRAL":
            direction = "BUY"  # default to buy for forecast
        
        update_progress(0.5, "Fetching news...")
        news_items = get_market_news(yf_sym)
        
        update_progress(0.7, "Calling AI for trade setup...")
        ai_trade = get_ai_trade_setup(clean_pair, tf, direction, current_price, df, news_items, user_info, update_progress)
        if not ai_trade:
            progress_bar.empty()
            return None, "AI analysis failed", None
        
        update_progress(0.9, "Creating forecast chart...")
        chart = create_forecast_chart(df, ai_trade['entry'], ai_trade['sl'], ai_trade['tp'], ai_trade['forecast'])
        
        progress_bar.progress(1.0, "Done")
        time.sleep(0.5)
        progress_bar.empty()
        return chart, ai_trade['provider'], ai_trade
    except Exception as e:
        progress_bar.empty()
        return None, str(e), None

# NEW: News impact analysis using AI (Sinhala output) for a specific pair
def analyze_news_impact(news_items, target_pair, user_info):
    """Use AI to determine impact on a specific currency pair."""
    news_titles = "\n".join([f"- {n['title']} (Time: {n['time']})" for n in news_items])
    prompt = f"""
    Based on the following recent market news headlines (with Colombo times), analyze the impact on {target_pair}.
    Provide a brief summary in SINHALA language, indicating whether the news is positive, negative, or neutral for {target_pair}, and why.
    Also mention the time of the news that is most relevant.

    News:
    {news_titles}

    Output format:
    IMPACT: [positive/negative/neutral]
    REASON: [Sinhala reason]
    TIME: [most relevant news time]
    """
    response, provider = call_ai_with_fallback(prompt, user_info)
    return response, provider

# --- 7. MAIN APPLICATION ---
if not st.session_state.logged_in:
    st.markdown("<div class='main-title'><h1>⚡ INFINITE AI EDITION TERMINAL v27.0 (AI-Powered Scanner)</h1><p>Professional Trading Intelligence</p></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login_form"):
            u, p = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Access Terminal"):
                user = check_login(u, p)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.session_state.login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.rerun()
                else:
                    st.error("Invalid Credentials")
else:
    user_info = st.session_state.get('user', {})
    # Update last activity timestamp on each interaction
    st.session_state.last_activity = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Check and update ongoing trades automatically
    active_trades = check_and_update_trades(user_info['Username'])

    # --- SIDEBAR WITH SESSION DASHBOARD ---
    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    st.sidebar.caption(f"Credits: {user_info.get('UsageCount', 0)}/{user_info.get('HybridLimit', 30)}")
    
    # Beginner mode toggle
    st.sidebar.checkbox("👶 Beginner Mode", value=st.session_state.beginner_mode, key="beginner_mode_toggle")
    st.session_state.beginner_mode = st.session_state.beginner_mode_toggle
    
    # Session dashboard card
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Session Info")
    st.sidebar.markdown(f"""
    <div class='session-card'>
        <span>User:</span> {user_info['Username']}<br>
        <span>Login:</span> {st.session_state.login_time or 'N/A'}<br>
        <span>Last Activity:</span> {st.session_state.last_activity}<br>
        <span>Status:</span> ✅ Active
    </div>
    """, unsafe_allow_html=True)
    
    auto_refresh = st.sidebar.checkbox("🔄 Auto-Monitor (60s)", value=False)
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    # Navigation
    nav_options = ["Dashboard", "Market Scanner", "Ongoing Trades"]
    if user_info.get("Role") == "Admin" and not st.session_state.beginner_mode:
        nav_options.append("Admin Panel")
    if not st.session_state.beginner_mode:
        nav_options.append("Backtest")
    app_mode = st.sidebar.radio("Navigation", nav_options)
    
    assets = {
        "Forex": [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCHF=X", "USDCAD=X", "NZDUSD=X",
            "EURJPY=X", "GBPJPY=X", "EURGBP=X", "EURCHF=X", "CADJPY=X", "AUDJPY=X", "NZDJPY=X",
            "GBPAUD=X", "GBPCAD=X", "EURCAD=X", "AUDCAD=X", "AUDNZD=X", "EURNZD=X",
            # New additions
            "USDSEK=X", "USDNOK=X", "USDTRY=X", "USDZAR=X", "EURTRY=X", "EURSEK=X", "EURNOK=X",
            "GBPSEK=X", "GBPNOK=X", "AUDCHF=X", "CADCHF=X", "NZDCHF=X", "CHFJPY=X", "EURHUF=X",
            "USDHUF=X", "EURPLN=X", "USDPLN=X", "EURCZK=X", "USDCZK=X"
        ],
        "Crypto": [
            "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "ADA-USDT", "DOGE-USDT",
            "MATIC-USDT", "DOT-USDT", "LINK-USDT", "AVAX-USDT", "UNI-USDT", "LTC-USDT", "BCH-USDT",
            # New additions
            "ALGO-USDT", "VET-USDT", "ICP-USDT", "FIL-USDT", "AAVE-USDT", "AXS-USDT", "SAND-USDT",
            "MANA-USDT", "EGLD-USDT", "THETA-USDT"
        ],
        "Metals": ["XAUUSD=X", "XAGUSD=X", "XPTUSD=X", "XPDUSD=X"]
    }

    if app_mode == "Dashboard":
        st.title("📊 Trading Dashboard")
        
        # System Analysis Engine Live Animation
        st.markdown("""
        <div class='system-engine-card'>
            <div class='engine-icon'>⚙️</div>
            <h2>SYSTEM ANALYSIS ENGINE</h2>
            <div class='engine-text'>🔴 Real-time Analysis Engine Running • Live Market Data • AI Processing</div>
        </div>
        """, unsafe_allow_html=True)
        
        # User details card
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div class='dashboard-card'>
                <h3>👤 User Profile</h3>
                <p><span class='metric-label'>Username:</span> <span class='metric-value'>{user_info['Username']}</span></p>
                <p><span class='metric-label'>Role:</span> {user_info.get('Role', 'User')}</p>
                <p><span class='metric-label'>Credits Used:</span> {user_info.get('UsageCount', 0)} / {user_info.get('HybridLimit', 30)}</p>
                <p><span class='metric-label'>Last Login:</span> {user_info.get('LastLogin', 'N/A')}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            # Live market prices
            prices = get_major_prices()
            price_html = "<div class='dashboard-card'><h3>💰 Live Prices</h3><table class='live-price-table'>"
            for name, price in prices.items():
                price_html += f"<tr><td>{name}</td><td><b>{price}</b></td></tr>"
            price_html += "</table></div>"
            st.markdown(price_html, unsafe_allow_html=True)
        
        with col3:
            # Market Pulse
            st.markdown(f"""
            <div class='dashboard-card'>
                <h3>📈 Market Pulse</h3>
                <p><span class='metric-label'>Current Session:</span> <b>{get_current_session()}</b></p>
                <p><span class='metric-label'>Active Trades:</span> <b>{len(active_trades)}</b></p>
                <p><span class='metric-label'>Closed Today:</span> <b>{len([t for t in load_user_trades(user_info['Username'], status=['SL Hit', 'TP Hit']) if t.get('ClosedDate','').startswith(get_current_date_str())])}</b></p>
                <p><span class='metric-label'>AI Analysis Method:</span> Gemini (Primary) → Groq (Key Rotation) → Puter</p>
                <p><span class='metric-label'>Gemini Keys:</span> 7 keys (rotated)</p>
                <p><span class='metric-label'>Groq Keys:</span> 4 keys (rotated)</p>
                <p><span class='metric-label'>Scanner Accuracy Threshold:</span> {st.session_state.min_accuracy}%</p>
            </div>
            """, unsafe_allow_html=True)
        
        # NEW: Trades Near Entry Alert
        st.markdown("### 🎯 Trades Near Entry")
        near_entry_trades = []
        for trade in active_trades:
            live = get_live_price(trade['Pair'])
            if live:
                entry = float(trade['Entry'])
                diff_pct = abs(live - entry) / entry * 100
                if diff_pct < 0.5:  # within 0.5% of entry
                    near_entry_trades.append((trade, live))

        if near_entry_trades:
            for trade, live in near_entry_trades:
                color = "#00ff00" if trade['Direction'] == "BUY" else "#ff4b4b"
                st.markdown(f"""
                <div style='background:#1e1e1e; padding:10px; border-radius:8px; border-left:5px solid {color}; margin-bottom:5px;'>
                    <b>{trade['Pair']} | {trade['Direction']}</b> - Live: {live:.4f} (Entry: {trade['Entry']}) 
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No trades are near entry price currently.")
        
        # Theory Card - AI Forecast with Market Selector
        st.markdown("### 📈 Theory Card - AI Forecast")
        col_a, col_b, col_c, col_d, col_e = st.columns([1,2,2,1,1])
        with col_a:
            selected_market = st.selectbox(
                "Market",
                options=["Forex", "Crypto", "Metals"],
                index=0,
                key="theory_market"
            )
        # Define pair options based on market
        if selected_market == "Forex":
            pair_options = [
                "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "NZD/USD", "USD/CHF",
                "USD/SEK", "USD/NOK", "USD/TRY", "USD/ZAR", "EUR/TRY", "EUR/SEK", "EUR/NOK",
                "GBP/SEK", "GBP/NOK", "AUD/CHF", "CAD/CHF", "NZD/CHF", "CHF/JPY", "EUR/HUF",
                "USD/HUF", "EUR/PLN", "USD/PLN", "EUR/CZK", "USD/CZK"
            ]
        elif selected_market == "Crypto":
            pair_options = [
                "BTC/USD", "ETH/USD", "SOL/USD", "BNB/USD", "XRP/USD", "ADA/USD", "DOGE/USD",
                "MATIC/USD", "DOT/USD", "LINK/USD", "AVAX/USD", "UNI/USD", "LTC/USD", "BCH/USD",
                "ALGO/USD", "VET/USD", "ICP/USD", "FIL/USD", "AAVE/USD", "AXS/USD", "SAND/USD",
                "MANA/USD", "EGLD/USD", "THETA/USD"
            ]
        else:
            pair_options = ["XAU/USD", "XAG/USD", "XPT/USD", "XPD/USD"]
        
        with col_b:
            selected_pair = st.selectbox("Currency Pair", options=pair_options, index=0, key="theory_pair")
        with col_c:
            selected_tf = st.selectbox(
                "Timeframe",
                options=["15m", "1h", "4h", "1d"],
                index=1,
                key="theory_tf"
            )
        with col_d:
            generate_btn = st.button("🔮 Generate Forecast", type="primary", use_container_width=True)
        with col_e:
            if not st.session_state.beginner_mode:
                tech_btn = st.button("📊 Technical Chart", use_container_width=True)
                theory_btn = st.button("📐 Theory Chart", use_container_width=True)  # NEW button for theory chart
        
        # Get yfinance symbol for selected pair (for later use)
        pair_map = {}
        if selected_market == "Forex":
            pair_map = {p: p.replace("/","")+"=X" for p in pair_options}
            pair_map["USD/SEK"] = "USDSEK=X"  # handle special cases
        elif selected_market == "Crypto":
            pair_map = {p: p.replace("/","-")+"USD" for p in pair_options}
        else:
            pair_map = {p: p.replace("/","")+"=X" for p in pair_options}
        yf_sym = pair_map.get(selected_pair, selected_pair)
        
        # Generate forecast chart
        if generate_btn:
            with st.spinner("Generating AI forecast..."):
                chart, provider, trade_data = generate_dashboard_forecast(selected_market, selected_pair, selected_tf, user_info)
                if chart and trade_data:
                    st.session_state.dashboard_forecast = chart
                    st.session_state.dashboard_forecast_provider = provider
                    st.session_state.dashboard_forecast_data = trade_data
                else:
                    st.error(f"Failed to generate forecast: {provider}")
        
        if st.session_state.get("dashboard_forecast") is not None:
            st.plotly_chart(st.session_state.dashboard_forecast, use_container_width=True)
            data = st.session_state.dashboard_forecast_data
            st.caption(f"🤖 AI Provider: {st.session_state.dashboard_forecast_provider}")
            if data:
                live = get_live_price(data['pair'])
                if live:
                    if data['dir'] == "BUY":
                        progress = (live - data['entry']) / (data['tp'] - data['entry'])
                    else:
                        progress = (data['entry'] - live) / (data['entry'] - data['tp'])
                    progress = max(0, min(1, progress))
                    st.progress(progress, text="Progress to Target")
                st.markdown(f"**Sinhala Summary:** {data.get('sinhala_summary', 'N/A')}")
        
        # Generate technical chart (only in expert mode)
        if not st.session_state.beginner_mode:
            if 'tech_btn' in locals() and tech_btn:
                with st.spinner("Generating technical analysis chart..."):
                    period = get_period_for_tf(selected_tf)
                    df_tech = get_cached_historical_data(yf_sym, selected_tf, period=period)
                    if df_tech is not None and len(df_tech) > 50:
                        tech_chart = create_technical_chart(df_tech, selected_tf)
                        st.session_state.tech_chart = tech_chart
                    else:
                        st.error("Insufficient data for technical chart.")
            
            if st.session_state.get("tech_chart") is not None:
                st.plotly_chart(st.session_state.tech_chart, use_container_width=True)
            
            # Generate theory chart (SMC/ICT etc.)
            if 'theory_btn' in locals() and theory_btn:
                with st.spinner("Generating theory chart (SMC, ICT, Fibonacci, Elliott)..."):
                    period = get_period_for_tf(selected_tf)
                    df_theory = get_cached_historical_data(yf_sym, selected_tf, period=period)
                    if df_theory is not None and len(df_theory) > 50:
                        theory_chart = create_theory_chart(df_theory, selected_tf)
                        st.session_state.theory_chart = theory_chart
                    else:
                        st.error("Insufficient data for theory chart.")
            
            if st.session_state.get("theory_chart") is not None:
                st.plotly_chart(st.session_state.theory_chart, use_container_width=True)
        
        # Market News with AI Impact Analysis (Sinhala) for selected pair
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
        
        # Recent scanner signals
        st.markdown("### 🔥 Recent Scanner Signals")
        if st.session_state.scan_results:
            # Group by timeframe for display
            trades_by_tf = {}
            for t in st.session_state.scan_results:
                tf = t.get('timeframe', 'Unknown')
                if tf not in trades_by_tf:
                    trades_by_tf[tf] = []
                trades_by_tf[tf].append(t)
            
            for tf, trades in trades_by_tf.items():
                with st.expander(f"⏰ {tf} Timeframe ({len(trades)} trades)", expanded=False):
                    for t in trades[:3]:  # Show only first 3
                        st.info(f"{t['pair']} {t['dir']} @ {t['entry']:.4f} (Conf: {t['conf']}%)")
        else:
            st.info("No recent scans. Run Market Scanner to see signals.")

    elif app_mode == "Market Scanner":
        st.title("📡 AI-Powered Market Scanner (Multi-Timeframe)")
        
        st.markdown("<div class='scan-header'><h3>🔍 Select Markets & Timeframes to Scan</h3></div>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            market_choice = st.selectbox(
                "Market",
                options=["All", "Forex", "Crypto", "Metals"],
                index=0,
                key="market_selector"
            )
        with col2:
            # Timeframe multiselect
            available_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d", "1wk"]
            default_timeframes = ["4h", "15m"]  # Swing and scalp
            selected_timeframes = st.multiselect(
                "Timeframes",
                options=available_timeframes,
                default=default_timeframes,
                help="Select one or more timeframes to scan."
            )
        
        if market_choice == "All":
            scan_assets = assets["Forex"] + assets["Crypto"] + assets["Metals"]
        else:
            scan_assets = assets[market_choice]
        
        st.info(f"Selected markets: **{market_choice}** ({len(scan_assets)} assets) | Timeframes: {', '.join(selected_timeframes)}")
        
        min_acc = st.slider(
            "Minimum Accuracy (%)",
            min_value=0,
            max_value=100,
            value=st.session_state.min_accuracy,
            step=5,
            help="Set the minimum confidence level for scan results."
        )
        st.session_state.min_accuracy = min_acc
        
        col1, col2 = st.columns([1,5])
        with col1:
            if st.button("🚀 Start AI Scan", type="primary", use_container_width=True):
                if not selected_timeframes:
                    st.warning("Please select at least one timeframe.")
                else:
                    with st.spinner(f"AI Scanning {market_choice} on {len(selected_timeframes)} timeframe(s)..."):
                        results = scan_market_with_ai(scan_assets, user_info, selected_timeframes, min_accuracy=min_acc)
                        st.session_state.scan_results = results  # Now a flat list
                        
                        if not results:
                            st.warning(f"No signals found above {min_acc}% accuracy.")
                        else:
                            st.success(f"Scan Complete! Found {len(results)} setups across {len(selected_timeframes)} timeframe(s).")
        
        with col2:
            if st.button("🗑️ Clear Results", use_container_width=True):
                st.session_state.scan_results = []
                st.rerun()
        
        st.markdown("---")
        
        res = st.session_state.scan_results
        if res:
            # Group results by timeframe
            trades_by_tf = {}
            for trade in res:
                tf = trade.get('timeframe', 'Unknown')
                if tf not in trades_by_tf:
                    trades_by_tf[tf] = []
                trades_by_tf[tf].append(trade)
            
            # Display each timeframe group
            for tf, trades in trades_by_tf.items():
                with st.expander(f"⏰ {tf} Timeframe ({len(trades)} trades)", expanded=True):
                    current_session = get_current_session()
                    for idx, sig in enumerate(trades):
                        max_diff = abs(sig['entry'] - sig['sl'])
                        if max_diff > 0:
                            progress = 1 - (abs(sig['live_price'] - sig['entry']) / max_diff)
                            progress = max(0, min(1, progress))
                        else:
                            progress = 0
                        
                        conf_badge = f"<span class='ai-badge ai-approve'>✅ {sig['confirmation']}</span>" if sig['confirmation'] == "APPROVE" else f"<span class='ai-badge ai-reject'>❌ {sig['confirmation']}</span>" if sig['confirmation'] == "REJECT" else ""
                        
                        col1, col2, col3, col4 = st.columns([3,1,1,2])
                        with col1:
                            color = "#00ff00" if sig['dir'] == "BUY" else "#ff4b4b"
                            session_tag = f"<span style='color:#00ff99; font-size:0.9em;'> [{current_session}]</span>" if current_session else ""
                            st.markdown(f"""
                            <div style='background:#1e1e1e; padding:10px; border-radius:8px; border-left:5px solid {color}; margin-bottom:10px;'>
                                <b>{sig['pair']} | {sig['dir']}{session_tag}</b> {conf_badge}<br>
                                Entry: {sig['entry']:.4f} | SL: {sig['sl']:.4f} | TP: {sig['tp']:.4f}<br>
                                Live: {sig['live_price']:.4f} | AI Confidence: {sig['conf']}%<br>
                                <small>Provider: {sig.get('provider', 'AI')} | Forecast: {sig.get('forecast', 'N/A')}</small><br>
                                <small>🇱🇰 {sig.get('sinhala_summary', '')}</small>
                            </div>
                            """, unsafe_allow_html=True)
                        with col2:
                            st.progress(progress, text="Approach")
                        with col3:
                            if not st.session_state.beginner_mode:
                                if st.button("🔍 Deep", key=f"deep_{tf}_{idx}"):
                                    st.session_state.selected_trade = sig
                                    st.session_state.deep_analysis_result = None
                                    st.session_state.deep_analysis_provider = None
                                    st.session_state.deep_forecast_chart = None
                                    st.session_state.deep_confirmation = None
                                    st.session_state.deep_reason = None
                                    st.rerun()
                        with col4:
                            # Fetch historical data for mini chart (use same timeframe as the trade)
                            try:
                                symbol_orig = sig.get('symbol_orig', sig['pair'])
                                period = get_period_for_tf(tf)
                                df_hist = get_cached_historical_data(get_yf_symbol(symbol_orig), tf, period=period)
                                if df_hist is not None:
                                    mini_chart = create_mini_chart(df_hist, sig['entry'], sig['sl'], sig['tp'])
                                    st.plotly_chart(mini_chart, use_container_width=True)
                            except:
                                st.write("Chart N/A")
        else:
            st.info("No scan results. Run a scan to see setups.")
        
        # Deep analysis display (only in expert mode)
        if not st.session_state.beginner_mode and st.session_state.selected_trade:
            st.markdown("---")
            st.subheader(f"🔬 Deep Analysis: {st.session_state.selected_trade['pair']} ({st.session_state.selected_trade['tf']})")
            
            if st.session_state.deep_analysis_result is None:
                with st.spinner("Running deep analysis with AI..."):
                    try:
                        symbol_orig = st.session_state.selected_trade.get('symbol_orig', st.session_state.selected_trade['pair'])
                        # Extract timeframe from the trade's tf field
                        tf_part = st.session_state.selected_trade.get('timeframe', '1h')
                        interval = tf_part
                        period = get_period_for_tf(interval)
                        df_hist = get_cached_historical_data(get_yf_symbol(symbol_orig), interval, period=period)
                        if df_hist is None or len(df_hist) < 10:
                            df_hist = None
                    except:
                        df_hist = None
                    
                    result, provider, confirmation, reason = get_deep_hybrid_analysis(st.session_state.selected_trade, st.session_state.user, df_hist)
                    st.session_state.deep_analysis_result = result
                    st.session_state.deep_analysis_provider = provider
                    st.session_state.deep_confirmation = confirmation
                    st.session_state.deep_reason = reason
                    
                    parsed = parse_ai_response(result)
                    forecast_text = parsed.get('FORECAST', '')
                    
                    if df_hist is not None and not df_hist.empty:
                        chart = create_forecast_chart(
                            df_hist,
                            st.session_state.selected_trade['entry'],
                            st.session_state.selected_trade['sl'],
                            st.session_state.selected_trade['tp'],
                            forecast_text
                        )
                        st.session_state.deep_forecast_chart = chart
                    else:
                        st.warning("Not enough historical data for forecast chart.")
            
            st.markdown(f"**🤖 Provider:** `{st.session_state.deep_analysis_provider}`")
            st.markdown(f"<div class='entry-box'>{st.session_state.deep_analysis_result}</div>", unsafe_allow_html=True)
            
            if st.session_state.get("deep_confirmation"):
                conf = st.session_state.deep_confirmation
                reason = st.session_state.get("deep_reason", "")
                if conf == "APPROVE":
                    st.markdown(f"<div class='confirm-card confirm-approve'><span class='confirm-icon'>✅</span> <b>AI CONFIRMATION: APPROVE</b><br>{reason}</div>", unsafe_allow_html=True)
                elif conf == "REJECT":
                    st.markdown(f"<div class='confirm-card confirm-reject'><span class='confirm-icon'>❌</span> <b>AI CONFIRMATION: REJECT</b><br>{reason}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='confirm-card confirm-neutral'><span class='confirm-icon'>🤔</span> <b>AI CONFIRMATION: {conf}</b><br>{reason}</div>", unsafe_allow_html=True)
            
            if st.session_state.deep_forecast_chart is not None:
                st.plotly_chart(st.session_state.deep_forecast_chart, use_container_width=True)
            else:
                st.info("Forecast chart could not be generated.")
            
            if st.button("Close Analysis"):
                st.session_state.selected_trade = None
                st.session_state.deep_analysis_result = None
                st.session_state.deep_analysis_provider = None
                st.session_state.deep_forecast_chart = None
                st.session_state.deep_confirmation = None
                st.session_state.deep_reason = None
                st.rerun()

    elif app_mode == "Ongoing Trades":
        st.title("📋 Ongoing Trades")
        
        # Date filter
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=7))
        with col2:
            end_date = st.date_input("End Date", value=datetime.now())
        
        tab1, tab2 = st.tabs(["🟢 Active Trades", "📜 History"])
        
        with tab1:
            if active_trades:
                for trade in active_trades:
                    color = "#00ff00" if trade['Direction'] == "BUY" else "#ff4b4b"
                    pair = trade['Pair']
                    live = get_live_price(pair)
                    live_display = f"{live:.4f}" if live else "N/A"
                    
                    # Calculate progress towards target (0 = entry, 1 = TP)
                    progress = 0.5  # default
                    direction_text = ""
                    if live is not None:
                        try:
                            entry = float(trade['Entry'])
                            tp = float(trade['TP'])
                            if trade['Direction'] == "BUY":
                                # For BUY: progress = (live - entry) / (tp - entry)
                                if tp > entry:
                                    progress = (live - entry) / (tp - entry)
                                # Determine direction
                                if live < entry:
                                    direction_text = "⚠️ Moving towards **STOP LOSS**"
                                elif live > entry:
                                    direction_text = "✅ Moving towards **TAKE PROFIT**"
                                else:
                                    direction_text = "⚖️ At entry level"
                            else:  # SELL
                                # For SELL: progress = (entry - live) / (entry - tp)
                                if entry > tp:
                                    progress = (entry - live) / (entry - tp)
                                # Determine direction
                                if live > entry:
                                    direction_text = "⚠️ Moving towards **STOP LOSS**"
                                elif live < entry:
                                    direction_text = "✅ Moving towards **TAKE PROFIT**"
                                else:
                                    direction_text = "⚖️ At entry level"
                            progress = max(0, min(1, progress))
                        except Exception as e:
                            progress = 0.5
                            direction_text = "❌ Error calculating"
                    else:
                        direction_text = "❌ Live price unavailable"
                    
                    col1, col2 = st.columns([5,1])
                    with col1:
                        st.markdown(f"""
                        <div style='background:#1e1e1e; padding:15px; border-radius:10px; margin-bottom:10px; border-left:5px solid {color};'>
                            <b>{trade['Pair']} | {trade['Direction']}</b><br>
                            Entry: {trade['Entry']} | SL: {trade['SL']} | TP: {trade['TP']}<br>
                            Live: {live_display} | Confidence: {trade['Confidence']}%<br>
                            <small>Tracked since: {trade['Timestamp']}</small>
                        </div>
                        """, unsafe_allow_html=True)
                        # Progress bar
                        st.progress(progress, text="Progress to Target")
                        st.caption(direction_text)
                    
                    with col2:
                        if not st.session_state.beginner_mode:
                            if st.button("🗑️ Delete", key=f"del_active_{trade['row_num']}"):
                                if delete_trade_by_row_number(trade['row_num']):
                                    st.success("Trade deleted.")
                                    st.rerun()
            else:
                st.info("No active ongoing trades.")
        
        with tab2:
            st.subheader("Closed Trades History")
            closed_trades = load_user_trades(user_info['Username'], status=['SL Hit', 'TP Hit'])
            filtered_trades = []
            for trade in closed_trades:
                closed_date_str = trade.get('ClosedDate', '')
                if closed_date_str:
                    try:
                        closed_date = datetime.strptime(closed_date_str, "%Y-%m-%d %H:%M:%S").date()
                        if start_date <= closed_date <= end_date:
                            filtered_trades.append(trade)
                    except:
                        filtered_trades.append(trade)
                else:
                    filtered_trades.append(trade)
            
            if filtered_trades:
                filtered_trades.sort(key=lambda x: x.get('ClosedDate', ''), reverse=True)
                for trade in filtered_trades:
                    color = "#ff4b4b" if trade['Status'] == 'SL Hit' else "#00ff00"
                    col1, col2 = st.columns([5,1])
                    with col1:
                        st.markdown(f"""
                        <div style='background:#1e1e1e; padding:15px; border-radius:10px; margin-bottom:10px; border-left:5px solid {color};'>
                            <b>{trade['Pair']} | {trade['Direction']}</b> - <span style='color:{color};'>{trade['Status']}</span><br>
                            Entry: {trade['Entry']} | SL: {trade['SL']} | TP: {trade['TP']}<br>
                            Confidence: {trade['Confidence']}%<br>
                            <small>Tracked: {trade['Timestamp']} | Closed: {trade.get('ClosedDate', 'N/A')}</small>
                        </div>
                        """, unsafe_allow_html=True)
                    with col2:
                        if not st.session_state.beginner_mode:
                            if st.button("🗑️ Delete", key=f"del_closed_{trade['row_num']}"):
                                if delete_trade_by_row_number(trade['row_num']):
                                    st.success("Trade deleted.")
                                    st.rerun()
            else:
                st.info("No closed trades found in selected date range.")
        
        if st.button("Refresh & Check Status"):
            st.rerun()

    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Center & User Management")
            
            # Display total API requests
            st.metric("Total System API Requests", st.session_state.total_api_requests)
            
            sheet, _ = get_user_sheet()
            if sheet:
                all_records = sheet.get_all_records()
                df_users = pd.DataFrame(all_records)
                st.dataframe(df_users, use_container_width=True)
                
                st.markdown("---")
                with st.expander("➕ Create New User", expanded=False):
                    with st.form("create_user_form"):
                        new_u_name = st.text_input("Username")
                        new_u_pass = st.text_input("Password")
                        new_u_limit = st.number_input("Initial Hybrid Limit", value=100, min_value=1)
                        if st.form_submit_button("Create User"):
                            if new_u_name and new_u_pass:
                                success, msg = add_new_user_to_db(new_u_name, new_u_pass, new_u_limit)
                                if success:
                                    st.success(msg)
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(msg)
                            else:
                                st.warning("Please fill all fields")

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
                            update_user_limit_in_db(target_user, new_limit_val)
                            st.success(f"Limit updated to {new_limit_val}")
                            time.sleep(1)
                            st.rerun()
                    with c2:
                        st.subheader("Reset Usage")
                        new_usage_val = st.number_input("Set Usage Count", min_value=0, value=0)
                        if st.button("🔄 Update Usage"):
                            update_usage_in_db(target_user, new_usage_val)
                            st.success(f"Usage count set to {new_usage_val}")
                            time.sleep(1)
                            st.rerun()
            else:
                st.error("Database Connection Failed")
        else:
            st.error("Access Denied.")

    elif app_mode == "Backtest" and not st.session_state.beginner_mode:
        st.title("📈 Backtest Engine")
        
        st.markdown("<div class='scan-header'><h3>⚙️ Configure Backtest</h3></div>", unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            market_choice = st.selectbox(
                "Market",
                options=["All", "Forex", "Crypto", "Metals"],
                index=0,
                key="backtest_market"
            )
        with col2:
            min_acc = st.slider(
                "Minimum Accuracy (%)",
                min_value=0,
                max_value=100,
                value=st.session_state.min_accuracy,
                step=5
            )
        
        col3, col4 = st.columns(2)
        with col3:
            start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=30))
        with col4:
            end_date = st.date_input("End Date", value=datetime.now())
        
        if st.button("🚀 Run Backtest", type="primary"):
            with st.spinner("Running backtest... This may take a while."):
                # Pass the global assets dictionary to the function
                results = run_backtest(market_choice, start_date, end_date, min_acc, st.session_state.user, assets)
                st.session_state.backtest_results = results
        
        if st.session_state.backtest_results:
            res = st.session_state.backtest_results
            st.markdown("---")
            st.subheader("📊 Backtest Results")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Trades", res['total_trades'])
            with col2:
                st.metric("Winning Trades", res['winning_trades'])
            with col3:
                st.metric("Win Rate", f"{res['win_rate']:.2f}%")
            with col4:
                st.metric("Total Profit %", f"{res['total_profit_pct']:.2f}%")
            
            if res['results']:
                df_res = pd.DataFrame(res['results'])
                st.dataframe(df_res, use_container_width=True)

    # Footer
    st.markdown("---")
    st.markdown("<div class='footer'>⚡ Infinite AI Terminal v27.0 (AI-Powered Scanner) | Professional Trading Interface | Data delayed by market conditions</div>", unsafe_allow_html=True)

    if auto_refresh:
        time.sleep(60)
        st.rerun()