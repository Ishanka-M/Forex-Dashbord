import streamlit as st
import yfinance as yf
import pandas as pd
import puter  # Puter AI for Fallback
import google.generativeai as genai # Gemini AI
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import re
import numpy as np
import requests
import xml.etree.ElementTree as ET
import pytz # For Timezone handling

# --- 1. SETUP & STYLE (UPDATED ANIMATIONS & BRANDING) ---
st.set_page_config(page_title="Infinite Algo Terminal v26.0 (Advanced Risk)", layout="wide", page_icon="⚡")

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
        0% { box-shadow: 0 0 5px #00d4ff; }
        50% { box-shadow: 0 0 20px #00d4ff; }
        100% { box-shadow: 0 0 5px #00d4ff; }
    }
    .loading-icon { display: inline-block; animation: rotate 2s linear infinite; font-size: 24px; }
    
    .stApp { animation: fadeIn 0.8s ease-out forwards; }

    /* --- ALERT PANELS --- */
    .high-prob-alert {
        background: linear-gradient(135deg, #1a1a1a, #2d2d2d);
        border: 2px solid #00d4ff;
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
        background: rgba(0, 212, 255, 0.1);
        border: 2px solid #00d4ff; 
        padding: 20px; border-radius: 15px; margin-top: 15px; 
        color: white; backdrop-filter: blur(10px);
        box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
        transition: transform 0.3s, box-shadow 0.3s;
        animation: float 4s ease-in-out infinite;
    }
    .entry-box:hover { transform: scale(1.02); box-shadow: 0 0 30px rgba(0, 212, 255, 0.5); }
    
    .trade-metric { 
        background: linear-gradient(145deg, #1e1e1e, #2a2a2a);
        border: 1px solid #444; 
        border-radius: 12px; padding: 15px; text-align: center; transition: all 0.3s ease;
    }
    .trade-metric:hover { transform: translateY(-5px) scale(1.02); box-shadow: 0 10px 20px rgba(0,0,0,0.5); border-color: #00d4ff; }
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
    .news-neutral { border-left: 5px solid #00d4ff; }
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
    .admin-table th { background-color: #333; color: #00d4ff; }
    
    /* --- FORECAST ANIMATION --- */
    .forecast-loading {
        text-align: center;
        padding: 20px;
        background: #1e1e1e;
        border-radius: 10px;
        border: 1px solid #00d4ff;
        margin: 10px 0;
        animation: glow 1.5s infinite;
    }
    .forecast-loading span {
        font-size: 20px;
        color: #00d4ff;
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
        box-shadow: 0 5px 10px rgba(0,212,255,0.3);
    }
    .scan-header {
        background: linear-gradient(90deg, #1e3c3f, #0a1f2e);
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 20px;
        border-left: 5px solid #00d4ff;
    }
    
    /* --- ADDITIONAL PROFESSIONAL TOUCHES --- */
    .main-title {
        text-align: center;
        background: linear-gradient(135deg, #0a1f2e, #1e3c3f);
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 25px;
        border: 1px solid #00d4ff;
        box-shadow: 0 0 30px rgba(0,212,255,0.2);
    }
    .main-title h1 {
        color: #00d4ff;
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
        color: #00d4ff !important;
        font-weight: 600;
    }
    .stSelectbox label {
        color: #00d4ff !important;
        font-weight: 600;
    }
    .stRadio label {
        color: #00d4ff !important;
    }
    .stCheckbox label {
        color: #00d4ff !important;
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
        border-left: 3px solid #00d4ff;
    }
    .session-card span {
        color: #00d4ff;
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
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "active_provider" not in st.session_state: st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
if "scan_results" not in st.session_state: st.session_state.scan_results = {"swing": [], "scalp": []}
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

# Cache for live prices (to avoid rate limits)
if "price_cache" not in st.session_state:
    st.session_state.price_cache = {}  # clean_pair -> (price, timestamp)

# ==================== HELPER FUNCTIONS ====================

def get_yf_symbol(display_symbol):
    """Convert display symbol to yfinance symbol."""
    if display_symbol.endswith("-USDT"):
        return display_symbol.replace("-USDT", "-USD")
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
        if current_time - timestamp < cache_duration:
            return price

    yf_sym = clean_pair_to_yf_symbol(clean_pair)
    try:
        ticker = yf.Ticker(yf_sym)
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            price = float(hist['Close'].iloc[-1])
            st.session_state.price_cache[clean_pair] = (price, current_time)
            return price
        if hasattr(ticker, 'fast_info') and ticker.fast_info:
            price = ticker.fast_info['lastPrice']
            st.session_state.price_cache[clean_pair] = (price, current_time)
            return price
        price = ticker.info.get('regularMarketPrice', None)
        if price:
            st.session_state.price_cache[clean_pair] = (price, current_time)
        return price
    except Exception as e:
        print(f"Error fetching price for {clean_pair}: {e}")
        return None

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
    sheet, _ = get_ongoing_sheet()
    if sheet:
        try:
            sheet.delete_rows(row_number)
            return True
        except Exception as e:
            st.error(f"Error deleting trade: {e}")
            return False
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
                        if "HybridLimit" in headers:
                            current_limit = int(user.get("HybridLimit", 10))
                            if current_limit < 9000:
                                sheet.update_cell(cell.row, headers.index("HybridLimit") + 1, 10)
                                user["HybridLimit"] = 10
                        if "LastLogin" in headers:
                            sheet.update_cell(cell.row, headers.index("LastLogin") + 1, current_date)
                            user["LastLogin"] = current_date
                    except Exception as e:
                        print(f"Daily Reset Error: {e}")
                if "HybridLimit" not in user: user["HybridLimit"] = 10
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
    Returns signals dict, atr, confidence.
    """
    if df is None or len(df) < 50:
        return None, 0, 0
    signals = {}
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
    if c > ma_50 and c > ma_200 and slope > 0:
        trend_dir = "bull"
    elif c < ma_50 and c < ma_200 and slope < 0:
        trend_dir = "bear"
    signals['TREND'] = (f"Trend {trend_dir.upper()} (Slope {slope:.2f})", trend_dir)

    # --- 2. MACD ---
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    macd_val = macd.iloc[-1]
    sig_val = signal_line.iloc[-1]
    macd_signal = "neutral"
    if macd_val > sig_val and macd_val > 0:
        macd_signal = "bull"
    elif macd_val < sig_val and macd_val < 0:
        macd_signal = "bear"
    
    # --- 3. SMC & ICT ---
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    last_candles = df.tail(5)
    is_bullish_ob = (last_candles['Close'].iloc[-3] < last_candles['Open'].iloc[-3]) and \
                    (last_candles['Close'].iloc[-1] > last_candles['High'].iloc[-3])
    is_bearish_ob = (last_candles['Close'].iloc[-3] > last_candles['Open'].iloc[-3]) and \
                    (last_candles['Close'].iloc[-1] < last_candles['Low'].iloc[-3])

    smc_signal = "neutral"
    if c > highs.iloc[-2] or is_bullish_ob:
        smc_signal = "bull"
    elif c < lows.iloc[-2] or is_bearish_ob:
        smc_signal = "bear"
    signals['SMC'] = (f"{smc_signal.upper()} Structure/OB", smc_signal)
    
    fvg_bull = df['Low'].iloc[-1] > df['High'].iloc[-3]
    fvg_bear = df['High'].iloc[-1] < df['Low'].iloc[-3]
    ict_signal = "bull" if fvg_bull else ("bear" if fvg_bear else "neutral")
    signals['ICT'] = (f"{ict_signal.upper()} FVG", ict_signal)

    # --- 4. LIQUIDITY & SUPPORT/RESISTANCE ---
    liq_signal = "neutral"
    liq_text = "Holding"
    recent_low = df['Low'].tail(30).min()
    recent_high = df['High'].tail(30).max()
    is_at_support = abs(c - recent_low) < (c * 0.002)
    is_at_resistance = abs(c - recent_high) < (c * 0.002)

    if l < df['Low'].iloc[-10:-1].min() or is_at_support:
        liq_signal = "bull"
        liq_text = "Liq Grab / Support"
    elif h > df['High'].iloc[-10:-1].max() or is_at_resistance:
        liq_signal = "bear"
        liq_text = "Liq Grab / Resist"
    signals['LIQ'] = (liq_text, liq_signal)
    
    # --- 5. PATTERNS ---
    patt_signal = "neutral"
    patt_text = "No Pattern"
    if (df['Close'].iloc[-1] > df['Open'].iloc[-1] and df['Close'].iloc[-1] > df['Open'].iloc[-2] and df['Open'].iloc[-1] < df['Close'].iloc[-2]):
        patt_signal = "bull"
        patt_text = "Bull Engulfing"
    elif (df['Close'].iloc[-1] < df['Open'].iloc[-1] and df['Close'].iloc[-1] < df['Open'].iloc[-2] and df['Open'].iloc[-1] > df['Close'].iloc[-2]):
        patt_signal = "bear"
        patt_text = "Bear Engulfing"
    signals['PATT'] = (patt_text, patt_signal)
    
    # --- 6. BOLLINGER BANDS ---
    sma_20 = df['Close'].rolling(20).mean()
    std_20 = df['Close'].rolling(20).std()
    upper_bb = sma_20 + (std_20 * 2)
    lower_bb = sma_20 - (std_20 * 2)
    bb_status = "neutral"
    bb_text = "Normal Vol"
    if c > upper_bb.iloc[-1]:
        bb_status = "bear"
        bb_text = "Overextended"
    elif c < lower_bb.iloc[-1]:
        bb_status = "bull"
        bb_text = "Oversold"
    signals['VOLATILITY'] = (bb_text, bb_status)

    # --- 7. RSI ---
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
    signals['RSI'] = (f"RSI: {int(rsi_val)}", "neutral")

    # --- 8. FIBONACCI ---
    ph_fib = df['High'].rolling(50).max().iloc[-1]
    pl_fib = df['Low'].rolling(50).min().iloc[-1]
    fib_range = ph_fib - pl_fib
    fib_618 = ph_fib - (fib_range * 0.618)
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.001) else ("Ranging", "neutral")
    
    # --- 9. ELLIOTT WAVE ---
    last_50 = df['Close'].tail(50)
    max_50, min_50 = last_50.max(), last_50.min()
    current_pos = (c - min_50) / (max_50 - min_50) if (max_50 - min_50) != 0 else 0.5
    
    ew_status = "Wave Analysis"
    ew_col = "neutral"
    if trend_dir == "bull":
        if current_pos > 0.8:
            ew_status, ew_col = "Wave 5 (Top)", "bear"
        elif 0.4 < current_pos <= 0.8:
            ew_status, ew_col = "Wave 3 (Impulse)", "bull"
        else:
            ew_status, ew_col = "Wave 1 (Start)", "bull"
    else:
        if current_pos < 0.2:
            ew_status, ew_col = "Wave C (Drop)", "bull"
        elif 0.2 <= current_pos < 0.6:
            ew_status, ew_col = "Wave A (Corr)", "bear"
        else:
            ew_status, ew_col = "Wave B (Rally)", "neutral"
    signals['ELLIOTT'] = (ew_status, ew_col)

    # --- 10. CONFIDENCE SCORING (OLD CODE STYLE) ---
    confidence = 0

    # News impact (old code style)
    if news_items:
        news_score = calculate_news_score(news_items)
        confidence += news_score

    # Trend
    if trend_dir == "bull":
        confidence += 20
    elif trend_dir == "bear":
        confidence -= 20

    # MACD
    if macd_signal == "bull":
        confidence += 10
    elif macd_signal == "bear":
        confidence -= 10

    # SMC
    if smc_signal == "bull":
        confidence += 20
    elif smc_signal == "bear":
        confidence -= 20

    # ICT
    if ict_signal == "bull":
        confidence += 10
    elif ict_signal == "bear":
        confidence -= 10

    # Liquidity
    if liq_signal == "bull":
        confidence += 15
    elif liq_signal == "bear":
        confidence -= 15

    # Patterns
    if patt_signal == "bull":
        confidence += 15
    elif patt_signal == "bear":
        confidence -= 15

    # RSI combo (old code sk_conf)
    if rsi_val < 30 and trend_dir == "bull":
        confidence += 10
    elif rsi_val > 70 and trend_dir == "bear":
        confidence -= 10

    final_signal = "neutral"
    if confidence > 0:
        final_signal = "bull"
    elif confidence < 0:
        final_signal = "bear"

    signals['SK'] = (f"CONFIDENCE: {abs(confidence)}%", final_signal)

    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    return signals, atr, confidence

# --- 5. RISK-OPTIMIZED SL/TP CALCULATION ---
def calculate_risk_optimized_sl_tp(df, direction, entry, atr, tf_type):
    """
    Calculate SL and TP using ATR and recent swing levels to minimize risk.
    tf_type: 'scalp' or 'swing'
    """
    # Get recent swing levels (last 5 candles)
    recent_low = df['Low'].tail(5).min()
    recent_high = df['High'].tail(5).max()
    
    # Determine base SL distance from ATR
    if tf_type == 'scalp':
        base_sl_mult = 1.2
        risk_reward = 2.0
    else:
        base_sl_mult = 1.5
        risk_reward = 3.0
    
    atr_distance = atr * base_sl_mult
    
    if direction == "BUY":
        # SL should be below recent low and below entry
        structure_distance = (entry - recent_low) * 1.1  # place 10% below recent low
        sl_distance = max(atr_distance, structure_distance)
        sl = entry - sl_distance
        tp = entry + (sl_distance * risk_reward)
    else:  # SELL
        structure_distance = (recent_high - entry) * 1.1
        sl_distance = max(atr_distance, structure_distance)
        sl = entry + sl_distance
        tp = entry - (sl_distance * risk_reward)
    
    return sl, tp

# --- 6. INFINITE ALGORITHMIC ENGINE (UPDATED WITH RISK-OPTIMIZED SL/TP) ---
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
        sl, tp = calculate_risk_optimized_sl_tp(df, "BUY", curr_p, atr, tf_type)
    elif signal_dir == "bear":
        action = "SELL"
        status_sinhala = "වෙළඳපල විකුණුම්කරුවන් අත. (Market is Bearish)"
        sl, tp = calculate_risk_optimized_sl_tp(df, "SELL", curr_p, atr, tf_type)

    analysis_text = f"""
    ♾️ **INFINITE ALGO ENGINE V26.0 (ADVANCED RISK)**
    
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

# --- 7. HYBRID AI ENGINE WITH CONFIRMATION ---
def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info, tf, df):
    if sigs is None:
        return "Error: Insufficient Signal Data", "System Error", None, None
    
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr, tf, df)
    
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 10)
    
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return algo_result, "Infinite Algo (Limit Reached)", None, None

    news_str = "\n".join([f"- {n['title']}" for n in news_items])

    # Prompt now asks for explicit confirmation and reason
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

    gemini_keys = []
    for i in range(1, 8):
        k = st.secrets.get(f"GEMINI_API_KEY_{i}")
        if k:
            gemini_keys.append(k)
        
    response_text = ""
    provider_name = ""

    with st.status(f"🚀 Infinite AI Activating ({tf})...", expanded=True) as status:
        if not gemini_keys:
            st.error("❌ No Gemini Keys found!")
        
        for idx, key in enumerate(gemini_keys):
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel('gemini-3-flash-preview')
                response = model.generate_content(prompt)
                response_text = response.text
                provider_name = f"Gemini 1.5 Flash (Key {idx+1}) ⚡"
                status.update(label=f"✅ Gemini Analysis Complete!", state="complete", expanded=False)
                break
            except Exception as e:
                continue

        if not response_text:
            try:
                puter_resp = puter.ai.chat(prompt)
                response_text = puter_resp.message.content
                provider_name = "Puter AI (Fallback) 🔵"
                status.update(label="✅ Puter Analysis Complete!", state="complete", expanded=False)
            except Exception as e_puter:
                return algo_result, "Infinite Algo (Fallback)", None, None

    if response_text:
        new_usage = current_usage + 1
        user_info["UsageCount"] = new_usage
        st.session_state.user = user_info
        if user_info["Username"] != "Admin":
            update_usage_in_db(user_info["Username"], new_usage)

        # Parse confirmation and reason
        confirm_match = re.search(r"CONFIRMATION\s*:\s*(APPROVE|REJECT)", response_text, re.IGNORECASE)
        reason_match = re.search(r"REASON\s*:\s*(.+)", response_text, re.IGNORECASE)
        confirmation = confirm_match.group(1).upper() if confirm_match else "N/A"
        reason = reason_match.group(1).strip() if reason_match else ""

        return response_text, f"{provider_name} | Used: {new_usage}/{max_limit}", confirmation, reason

    return algo_result, "Infinite Algo (Default)", None, None

def parse_ai_response(text):
    data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A", "FORECAST": "N/A"}
    try:
        entry_match = re.search(r"ENTRY\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        sl_match = re.search(r"SL\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        tp_match = re.search(r"TP\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        forecast_match = re.search(r"FORECAST\s*[:=]\s*(.*?)(?=\n|$)", text, re.IGNORECASE | re.DOTALL)
        if entry_match:
            data["ENTRY"] = entry_match.group(1)
        if sl_match:
            data["SL"] = sl_match.group(1)
        if tp_match:
            data["TP"] = tp_match.group(1)
        if forecast_match:
            data["FORECAST"] = forecast_match.group(1).strip()
    except:
        pass
    return data

# ==================== DEEP ANALYSIS FUNCTION (HYBRID ENGINE) ====================
def get_deep_hybrid_analysis(trade, user_info, df_hist):
    """Run deep analysis with confirmation for scanner trade."""
    pair = trade['pair']
    if "=X" not in pair and "-USDT" not in pair and pair not in ["XAUUSD","XAGUSD","XPTUSD","XPDUSD"]:
        if pair in ["XAUUSD","XAGUSD","XPTUSD","XPDUSD"]:
            orig_sym = pair + "=X"
        else:
            orig_sym = pair + "-USDT"
    else:
        orig_sym = pair
    
    news_items = get_market_news(orig_sym)
    news_str = "\n".join([f"- {n['title']}" for n in news_items])
    
    live_price = trade.get('live_price', trade['price'])
    tf_display = trade['tf']
    
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
    
    gemini_keys = []
    for i in range(1, 8):
        k = st.secrets.get(f"GEMINI_API_KEY_{i}")
        if k:
            gemini_keys.append(k)
    
    response_text = ""
    provider_name = ""
    
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 10)
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return "Daily limit reached. Please try again tomorrow.", "Limit Reached", None, None
    
    with st.status(f"🔍 Deep AI Analysis for {pair}...", expanded=True) as status:
        if not gemini_keys:
            st.error("❌ No Gemini Keys found!")
            try:
                puter_resp = puter.ai.chat(prompt)
                response_text = puter_resp.message.content
                provider_name = "Puter AI (Fallback) 🔵"
                status.update(label="✅ Deep Analysis Complete (Puter)", state="complete", expanded=False)
            except:
                return "Deep analysis failed. Please try again.", "Error", None, None
        else:
            for idx, key in enumerate(gemini_keys):
                try:
                    genai.configure(api_key=key)
                    model = genai.GenerativeModel('gemini-3-flash-preview')
                    response = model.generate_content(prompt)
                    response_text = response.text
                    provider_name = f"Gemini 1.5 Flash (Key {idx+1}) ⚡"
                    status.update(label="✅ Deep Analysis Complete (Gemini)", state="complete", expanded=False)
                    break
                except Exception as e:
                    continue
            
            if not response_text:
                try:
                    puter_resp = puter.ai.chat(prompt)
                    response_text = puter_resp.message.content
                    provider_name = "Puter AI (Fallback) 🔵"
                    status.update(label="✅ Deep Analysis Complete (Puter)", state="complete", expanded=False)
                except Exception as e_puter:
                    return "Deep analysis failed. Please try again.", "Error", None, None
    
    if response_text:
        new_usage = current_usage + 1
        user_info["UsageCount"] = new_usage
        st.session_state.user = user_info
        if user_info["Username"] != "Admin":
            update_usage_in_db(user_info["Username"], new_usage)

        confirm_match = re.search(r"CONFIRMATION\s*:\s*(APPROVE|REJECT)", response_text, re.IGNORECASE)
        reason_match = re.search(r"REASON\s*:\s*(.+)", response_text, re.IGNORECASE)
        confirmation = confirm_match.group(1).upper() if confirm_match else "N/A"
        reason = reason_match.group(1).strip() if reason_match else ""

        return response_text, f"{provider_name} | Used: {new_usage}/{max_limit}", confirmation, reason
    
    return "Deep analysis failed.", "Error", None, None

# ==================== QUICK AI CONFIRMATION FOR SCANNER TRADES ====================
def quick_ai_confirm(trade, user_info):
    """Run deep analysis and return only confirmation and reason."""
    # Fetch historical data based on timeframe
    if "Swing" in trade['tf']:
        interval = "4h"
        period = "3mo"
    else:
        interval = "15m"
        period = "1mo"
    symbol_orig = trade.get('symbol_orig', trade['pair'])
    try:
        df_hist = yf.download(get_yf_symbol(symbol_orig), period=period, interval=interval, progress=False)
        if not df_hist.empty and len(df_hist) > 10:
            if isinstance(df_hist.columns, pd.MultiIndex):
                df_hist.columns = df_hist.columns.get_level_values(0)
        else:
            df_hist = None
    except:
        df_hist = None
    result, provider, confirmation, reason = get_deep_hybrid_analysis(trade, user_info, df_hist)
    return confirmation, reason

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

# ==================== SCAN FUNCTION WITH ADVANCED SL/TP ====================
def scan_market(assets_list, active_trades=None, min_accuracy=40):
    """
    Scan market for swing and scalp setups using risk-optimized SL/TP.
    """
    swing_list = []
    scalp_list = []
    
    # Swing scan (4H)
    for symbol in assets_list:
        try:
            df_sw = yf.download(get_yf_symbol(symbol), period="6mo", interval="4h", progress=False)
            if not df_sw.empty and len(df_sw) > 50:
                if isinstance(df_sw.columns, pd.MultiIndex):
                    df_sw.columns = df_sw.columns.get_level_values(0)
                # For scanner, we don't fetch news (speed), use old weights but no news
                sigs_sw, atr_sw, conf_sw = calculate_advanced_signals(df_sw, "4h", news_items=None)
                
                if abs(conf_sw) > min_accuracy:
                    clean_sym = symbol.replace("=X","").replace("-USD","").replace("-USDT","")
                    direction = "BUY" if conf_sw > 0 else "SELL"
                    curr_price = df_sw['Close'].iloc[-1]
                    # Use risk-optimized SL/TP
                    tf_type = 'swing'
                    sl, tp = calculate_risk_optimized_sl_tp(df_sw, direction, curr_price, atr_sw, tf_type)
                    
                    trade_candidate = {
                        "pair": clean_sym, "tf": "4H (Swing)", "dir": direction,
                        "conf": abs(conf_sw), "price": curr_price,
                        "entry": curr_price, "sl": sl, "tp": tp,
                        "live_price": get_live_price(clean_sym) or curr_price,
                        "symbol_orig": symbol
                    }
                    
                    if active_trades and is_trade_tracked(trade_candidate, active_trades):
                        continue
                    
                    swing_list.append(trade_candidate)
        except:
            pass
        
    # Scalp scan (15M)
    for symbol in assets_list:
        try:
            df_sc = yf.download(get_yf_symbol(symbol), period="1mo", interval="15m", progress=False)
            if not df_sc.empty and len(df_sc) > 50:
                if isinstance(df_sc.columns, pd.MultiIndex):
                    df_sc.columns = df_sc.columns.get_level_values(0)
                sigs_sc, atr_sc, conf_sc = calculate_advanced_signals(df_sc, "15m", news_items=None)
                
                if abs(conf_sc) > min_accuracy:
                    clean_sym = symbol.replace("=X","").replace("-USD","").replace("-USDT","")
                    direction = "BUY" if conf_sc > 0 else "SELL"
                    curr_price = df_sc['Close'].iloc[-1]
                    tf_type = 'scalp'
                    sl, tp = calculate_risk_optimized_sl_tp(df_sc, direction, curr_price, atr_sc, tf_type)
                    
                    trade_candidate = {
                        "pair": clean_sym, "tf": "15M (Scalp)", "dir": direction,
                        "conf": abs(conf_sc), "price": curr_price,
                        "entry": curr_price, "sl": sl, "tp": tp,
                        "live_price": get_live_price(clean_sym) or curr_price,
                        "symbol_orig": symbol
                    }
                    
                    if active_trades and is_trade_tracked(trade_candidate, active_trades):
                        continue
                    
                    scalp_list.append(trade_candidate)
        except:
            pass
        
    return {"swing": swing_list, "scalp": scalp_list}

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
        line=dict(color='#00d4ff', width=3, dash='dot'),
        marker=dict(size=5, color='#00d4ff', symbol='circle')
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
            arrowcolor="#00d4ff",
            font=dict(size=12, color="white"),
            bgcolor="#1e1e1e",
            bordercolor="#00d4ff",
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

# --- 7. MAIN APPLICATION ---
if not st.session_state.logged_in:
    st.markdown("<div class='main-title'><h1>⚡ INFINITE AI EDITION TERMINAL v26.0 (Advanced Risk)</h1><p>Professional Trading Intelligence</p></div>", unsafe_allow_html=True)
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

    # --- SIDEBAR WITH SESSION DASHBOARD ---
    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    st.sidebar.caption(f"Credits: {user_info.get('UsageCount', 0)}/{user_info.get('HybridLimit', 10)}")
    
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
    
    nav_options = ["Terminal", "Market Scanner", "Ongoing Trades"]
    if user_info.get("Role") == "Admin":
        nav_options.append("Admin Panel")
    app_mode = st.sidebar.radio("Navigation", nav_options)
    
    assets = {
        "Forex": [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCHF=X", "USDCAD=X", "NZDUSD=X",
            "EURJPY=X", "GBPJPY=X", "EURGBP=X", "EURCHF=X", "CADJPY=X", "AUDJPY=X", "NZDJPY=X",
            "GBPAUD=X", "GBPCAD=X", "EURCAD=X", "AUDCAD=X", "AUDNZD=X", "EURNZD=X"
        ],
        "Crypto": [
            "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT", "ADA-USDT", "DOGE-USDT",
            "MATIC-USDT", "DOT-USDT", "LINK-USDT", "AVAX-USDT", "UNI-USDT", "LTC-USDT", "BCH-USDT"
        ],
        "Metals": ["XAUUSD=X", "XAGUSD=X", "XPTUSD=X", "XPDUSD=X"]
    }

    if app_mode == "Terminal":
        st.sidebar.divider()
        market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
        pair = st.sidebar.selectbox("Select Asset", assets[market], format_func=lambda x: x.replace("=X", "").replace("-USD", "").replace("-USDT", ""))
        tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h", "1d", "1wk"], index=2)

        news_items = get_market_news(pair)
        news_impact = calculate_news_impact(news_items)
        
        st.sidebar.markdown("### 📰 Market News")
        tz = pytz.timezone('Asia/Colombo')
        current_time_str = datetime.now(tz).strftime("%H:%M:%S")
        st.sidebar.caption(f"Last updated: {current_time_str}")
        st.sidebar.progress(news_impact)
        if news_impact > 70:
            st.sidebar.caption("⚠️ HIGH VOLATILITY EXPECTED")
        else:
            st.sidebar.caption("✅ Market Stable")
        
        for news in news_items:
            time_display = f"<span class='news-time'>{news['time']}</span>" if news['time'] else ""
            st.sidebar.markdown(f"<div class='news-card {get_sentiment_class(news['title'])}'>{news['title']}{time_display}</div>", unsafe_allow_html=True)

        df = yf.download(get_yf_symbol(pair), period=get_data_period(tf), interval=tf, progress=False)
        
        if not df.empty and len(df) > 50:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            curr_p = float(df['Close'].iloc[-1])
            st.title(f"{pair.replace('=X', '').replace('-USD', '').replace('-USDT', '')} Terminal - {curr_p:.5f}")
            
            sigs, current_atr, conf_score = calculate_advanced_signals(df, tf, news_items)  # Pass news
            
            signal_dir = sigs['SK'][1]
            if signal_dir == "bull":
                st.markdown(f"<div class='notif-container notif-buy'>🔔 <b>BUY SIGNAL:</b> Accuracy {abs(conf_score)}%</div>", unsafe_allow_html=True)
            elif signal_dir == "bear":
                st.markdown(f"<div class='notif-container notif-sell'>🔔 <b>SELL SIGNAL:</b> Accuracy {abs(conf_score)}%</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='notif-container notif-wait'>📡 Neutral Market (Accuracy {abs(conf_score)}%)</div>", unsafe_allow_html=True)

            # Signal grid
            r1c1, r1c2, r1c3 = st.columns(3)
            r1c1.markdown(f"<div class='sig-box {sigs['TREND'][1]}'>TREND: {sigs['TREND'][0]}</div>", unsafe_allow_html=True)
            r1c2.markdown(f"<div class='sig-box {sigs['SMC'][1]}'>SMC: {sigs['SMC'][0]}</div>", unsafe_allow_html=True)
            r1c3.markdown(f"<div class='sig-box {sigs['ELLIOTT'][1]}'>WAVE: {sigs['ELLIOTT'][0]}</div>", unsafe_allow_html=True)
            
            r2c1, r2c2, r2c3 = st.columns(3)
            r2c1.markdown(f"<div class='sig-box {sigs['LIQ'][1]}'>{sigs['LIQ'][0]}</div>", unsafe_allow_html=True)
            r2c2.markdown(f"<div class='sig-box {sigs['PATT'][1]}'>{sigs['PATT'][0]}</div>", unsafe_allow_html=True)
            r2c3.markdown(f"<div class='sig-box {sigs['ICT'][1]}'>ICT: {sigs['ICT'][0]}</div>", unsafe_allow_html=True)
            
            r3c1, r3c2, r3c3 = st.columns(3)
            r3c1.markdown(f"<div class='sig-box {sigs['RSI'][1]}'>{sigs['RSI'][0]}</div>", unsafe_allow_html=True)
            r3c2.markdown(f"<div class='sig-box {sigs['FIB'][1]}'>FIB: {sigs['FIB'][0]}</div>", unsafe_allow_html=True)
            r3c3.markdown(f"<div class='sig-box {sigs['VOLATILITY'][1]}'>{sigs['VOLATILITY'][0]}</div>", unsafe_allow_html=True)
            
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(f"### 🎯 Hybrid AI Signal Card")
            parsed = st.session_state.ai_parsed_data
            
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)
            
            st.markdown("---")
            
            st.markdown("### 🔮 AI Forecast Chart")
            forecast_placeholder = st.empty()
            
            if st.button("🚀 Analyze with Gemini + Puter + News", use_container_width=True):
                with forecast_placeholder.container():
                    st.markdown("<div class='forecast-loading'><span class='loading-icon'>⚡</span> Analyzing with AI... Generating Forecast...</div>", unsafe_allow_html=True)
                
                live_price = get_live_price(pair) or curr_p
                # Pass df to infinite_algorithmic_engine for risk-optimized SL/TP
                result, provider, confirmation, reason = get_hybrid_analysis(pair, {'price': live_price}, sigs, news_items, current_atr, st.session_state.user, tf, df)
                st.session_state.ai_parsed_data = parse_ai_response(result)
                st.session_state.ai_result = result.split("DATA:")[0] if "DATA:" in result else result
                st.session_state.active_provider = provider
                st.session_state.ai_confirmation = confirmation
                st.session_state.ai_reason = reason
                
                try:
                    entry = float(st.session_state.ai_parsed_data['ENTRY']) if st.session_state.ai_parsed_data['ENTRY'] != 'N/A' else live_price
                    sl = float(st.session_state.ai_parsed_data['SL']) if st.session_state.ai_parsed_data['SL'] != 'N/A' else live_price * 0.99
                    tp = float(st.session_state.ai_parsed_data['TP']) if st.session_state.ai_parsed_data['TP'] != 'N/A' else live_price * 1.01
                except:
                    entry = live_price
                    sl = live_price * 0.99
                    tp = live_price * 1.01
                
                forecast_fig = create_forecast_chart(df, entry, sl, tp, st.session_state.ai_parsed_data.get('FORECAST', ''))
                st.session_state.forecast_chart = forecast_fig
                
                forecast_placeholder.empty()
                st.rerun()

            if "ai_result" in st.session_state:
                st.markdown(f"**🤖 Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)
                
                # Display AI confirmation card
                if st.session_state.get("ai_confirmation"):
                    conf = st.session_state.ai_confirmation
                    reason = st.session_state.get("ai_reason", "")
                    if conf == "APPROVE":
                        st.markdown(f"<div class='confirm-card confirm-approve'><span class='confirm-icon'>✅</span> <b>AI CONFIRMATION: APPROVE</b><br>{reason}</div>", unsafe_allow_html=True)
                    elif conf == "REJECT":
                        st.markdown(f"<div class='confirm-card confirm-reject'><span class='confirm-icon'>❌</span> <b>AI CONFIRMATION: REJECT</b><br>{reason}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='confirm-card confirm-neutral'><span class='confirm-icon'>🤔</span> <b>AI CONFIRMATION: {conf}</b><br>{reason}</div>", unsafe_allow_html=True)
                
                if st.session_state.forecast_chart is not None:
                    st.plotly_chart(st.session_state.forecast_chart, use_container_width=True)
                    if st.session_state.ai_parsed_data.get('FORECAST') != 'N/A':
                        st.info(f"📈 Forecast: {st.session_state.ai_parsed_data['FORECAST']}")
        else:
            st.error("Insufficient data for this pair/timeframe. Please try another.")

    elif app_mode == "Market Scanner":
        st.title("📡 Global Market Scanner (Multi-Timeframe)")
        
        st.markdown("<div class='scan-header'><h3>🔍 Select Markets to Scan</h3></div>", unsafe_allow_html=True)
        market_choice = st.selectbox(
            "Choose market(s) to scan",
            options=["All", "Forex", "Crypto", "Metals"],
            index=0,
            key="market_selector"
        )
        st.session_state.selected_market = market_choice
        
        if market_choice == "All":
            scan_assets = assets["Forex"] + assets["Crypto"] + assets["Metals"]
        else:
            scan_assets = assets[market_choice]
        
        st.info(f"Selected markets: **{market_choice}** ({len(scan_assets)} assets)")
        
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
            if st.button("🚀 Start Scan", type="primary", use_container_width=True):
                with st.spinner(f"Scanning {market_choice} for High Probability Setups (>{min_acc}%)..."):
                    active_trades = load_user_trades(user_info['Username'], status='Active')
                    results = scan_market(scan_assets, active_trades, min_accuracy=min_acc)
                    st.session_state.scan_results = results
                    
                    if not results['swing'] and not results['scalp']:
                        st.warning(f"No signals found above {min_acc}% accuracy.")
                    else:
                        st.success(f"Scan Complete! Found {len(results['swing'])} Swing & {len(results['scalp'])} Scalp setups.")
        
        with col2:
            if st.button("🗑️ Clear Results", use_container_width=True):
                st.session_state.scan_results = {"swing": [], "scalp": []}
                st.rerun()
        
        st.markdown("---")
        
        res = st.session_state.scan_results
        
        # Helper to get current session
        current_session = get_current_session()
        
        # Swing
        st.subheader("🐢 SWING TRADES (4H)")
        if res['swing']:
            for idx, sig in enumerate(res['swing']):
                max_diff = abs(sig['entry'] - sig['sl'])
                if max_diff > 0:
                    progress = 1 - (abs(sig['live_price'] - sig['entry']) / max_diff)
                    progress = max(0, min(1, progress))
                else:
                    progress = 0
                
                # Unique key for AI confirmation
                trade_key = f"{sig['pair']}_{sig['tf']}_{sig['dir']}_{sig['entry']:.5f}"
                ai_data = st.session_state.ai_confirmations.get(trade_key)
                
                # Create columns: trade info (3), progress (1), deep (1), track (1), AI (1)
                col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
                with col1:
                    color = "#00ff00" if sig['dir'] == "BUY" else "#ff4b4b"
                    session_tag = f"<span style='color:#00d4ff; font-size:0.9em;'> [{current_session}]</span>" if current_session else ""
                    st.markdown(f"""
                    <div style='background:#1e1e1e; padding:10px; border-radius:8px; border-left:5px solid {color};'>
                        <b>{sig['pair']} | {sig['dir']}{session_tag}</b><br>
                        Entry: {sig['entry']:.4f} | SL: {sig['sl']:.4f} | TP: {sig['tp']:.4f}<br>
                        Live: {sig['live_price']:.4f} | Accuracy: {sig['conf']}%
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.progress(progress, text="Approach")
                with col3:
                    if st.button("🔍 Deep", key=f"swing_deep_{idx}"):
                        st.session_state.selected_trade = sig
                        st.session_state.deep_analysis_result = None
                        st.session_state.deep_analysis_provider = None
                        st.session_state.deep_forecast_chart = None
                        st.session_state.deep_confirmation = None
                        st.session_state.deep_reason = None
                        st.rerun()
                with col4:
                    if st.button("📌 Track", key=f"swing_track_{idx}"):
                        if save_trade_to_ongoing(sig, user_info['Username']):
                            st.success("Trade saved to Ongoing Trades!")
                            time.sleep(1)
                            st.rerun()
                with col5:
                    if ai_data:
                        conf, reason = ai_data
                        badge_class = "ai-approve" if conf == "APPROVE" else "ai-reject" if conf == "REJECT" else ""
                        badge_text = "✅" if conf == "APPROVE" else "❌" if conf == "REJECT" else "🤔"
                        st.markdown(f"<span class='ai-badge {badge_class}' title='{reason}'>{badge_text} {conf}</span>", unsafe_allow_html=True)
                    else:
                        if st.button("🤖 AI", key=f"ai_swing_{idx}"):
                            with st.spinner("AI Confirming..."):
                                confirmation, reason = quick_ai_confirm(sig, user_info)
                                st.session_state.ai_confirmations[trade_key] = (confirmation, reason)
                            st.rerun()
        else:
            st.info("No Swing setups found.")
        
        st.markdown("---")
        
        # Scalp
        st.subheader("🐇 SCALP TRADES (15M)")
        if res['scalp']:
            for idx, sig in enumerate(res['scalp']):
                max_diff = abs(sig['entry'] - sig['sl'])
                if max_diff > 0:
                    progress = 1 - (abs(sig['live_price'] - sig['entry']) / max_diff)
                    progress = max(0, min(1, progress))
                else:
                    progress = 0
                
                trade_key = f"{sig['pair']}_{sig['tf']}_{sig['dir']}_{sig['entry']:.5f}"
                ai_data = st.session_state.ai_confirmations.get(trade_key)
                
                col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
                with col1:
                    color = "#00ff00" if sig['dir'] == "BUY" else "#ff4b4b"
                    session_tag = f"<span style='color:#00d4ff; font-size:0.9em;'> [{current_session}]</span>" if current_session else ""
                    st.markdown(f"""
                    <div style='background:#1e1e1e; padding:10px; border-radius:8px; border-left:5px solid {color};'>
                        <b>{sig['pair']} | {sig['dir']}{session_tag}</b><br>
                        Entry: {sig['entry']:.4f} | SL: {sig['sl']:.4f} | TP: {sig['tp']:.4f}<br>
                        Live: {sig['live_price']:.4f} | Accuracy: {sig['conf']}%
                    </div>
                    """, unsafe_allow_html=True)
                with col2:
                    st.progress(progress, text="Approach")
                with col3:
                    if st.button("🔍 Deep", key=f"scalp_deep_{idx}"):
                        st.session_state.selected_trade = sig
                        st.session_state.deep_analysis_result = None
                        st.session_state.deep_analysis_provider = None
                        st.session_state.deep_forecast_chart = None
                        st.session_state.deep_confirmation = None
                        st.session_state.deep_reason = None
                        st.rerun()
                with col4:
                    if st.button("📌 Track", key=f"scalp_track_{idx}"):
                        if save_trade_to_ongoing(sig, user_info['Username']):
                            st.success("Trade saved to Ongoing Trades!")
                            time.sleep(1)
                            st.rerun()
                with col5:
                    if ai_data:
                        conf, reason = ai_data
                        badge_class = "ai-approve" if conf == "APPROVE" else "ai-reject" if conf == "REJECT" else ""
                        badge_text = "✅" if conf == "APPROVE" else "❌" if conf == "REJECT" else "🤔"
                        st.markdown(f"<span class='ai-badge {badge_class}' title='{reason}'>{badge_text} {conf}</span>", unsafe_allow_html=True)
                    else:
                        if st.button("🤖 AI", key=f"ai_scalp_{idx}"):
                            with st.spinner("AI Confirming..."):
                                confirmation, reason = quick_ai_confirm(sig, user_info)
                                st.session_state.ai_confirmations[trade_key] = (confirmation, reason)
                            st.rerun()
        else:
            st.info("No Scalp setups found.")
        
        # Deep analysis display
        if st.session_state.selected_trade:
            st.markdown("---")
            st.subheader(f"🔬 Deep Analysis: {st.session_state.selected_trade['pair']} ({st.session_state.selected_trade['tf']})")
            
            if st.session_state.deep_analysis_result is None:
                with st.spinner("Running deep analysis with Gemini + Puter..."):
                    # Fetch historical data for chart
                    try:
                        symbol_orig = st.session_state.selected_trade.get('symbol_orig', st.session_state.selected_trade['pair'])
                        if "Swing" in st.session_state.selected_trade['tf']:
                            interval = "4h"
                            period = "3mo"
                        else:
                            interval = "15m"
                            period = "1mo"
                        df_hist = yf.download(get_yf_symbol(symbol_orig), period=period, interval=interval, progress=False)
                        if not df_hist.empty and len(df_hist) > 10:
                            if isinstance(df_hist.columns, pd.MultiIndex):
                                df_hist.columns = df_hist.columns.get_level_values(0)
                        else:
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
            
            # Display confirmation card
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
        
        tab1, tab2 = st.tabs(["🟢 Active Trades", "📜 History"])
        
        with tab1:
            active_trades = check_and_update_trades(user_info['Username'])
            if active_trades:
                for trade in active_trades:
                    color = "#00ff00" if trade['Direction'] == "BUY" else "#ff4b4b"
                    pair = trade['Pair']
                    live = get_live_price(pair)
                    live_display = f"{live:.4f}" if live else "N/A"
                    
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
                    with col2:
                        if st.button("🗑️ Delete", key=f"del_active_{trade['row_num']}"):
                            if delete_trade_by_row_number(trade['row_num']):
                                st.success("Trade deleted.")
                                st.rerun()
            else:
                st.info("No active ongoing trades.")
        
        with tab2:
            st.subheader("Closed Trades History")
            closed_trades = load_user_trades(user_info['Username'], status=['SL Hit', 'TP Hit'])
            if closed_trades:
                closed_trades.sort(key=lambda x: x.get('ClosedDate', ''), reverse=True)
                for trade in closed_trades:
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
                        if st.button("🗑️ Delete", key=f"del_closed_{trade['row_num']}"):
                            if delete_trade_by_row_number(trade['row_num']):
                                st.success("Trade deleted.")
                                st.rerun()
            else:
                st.info("No closed trades found.")
        
        if st.button("Refresh & Check Status"):
            st.rerun()

    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Center & User Management")
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
                        new_u_limit = st.number_input("Initial Hybrid Limit", value=10, min_value=1)
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
                        new_limit_val = st.number_input("New Hybrid Limit", min_value=0, value=int(curr_user_data.get('HybridLimit', 10)))
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

    # Footer
    st.markdown("---")
    st.markdown("<div class='footer'>⚡ Infinite AI Terminal v26.0 (Advanced Risk) | Professional Trading Interface | Data delayed by market conditions</div>", unsafe_allow_html=True)

    if auto_refresh:
        time.sleep(60)
        st.rerun()
