import streamlit as st
import yfinance as yf
import pandas as pd
import puter  # Gemini/HF වෙනුවට Puter භාවිතා කරයි
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import time
import re
import numpy as np
import xml.etree.ElementTree as ET
import requests

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System v8.0 | Puter Hybrid", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .price-up { color: #00ff00; font-size: 22px; font-weight: bold; }
    .price-down { color: #ff4b4b; font-size: 22px; font-weight: bold; }
    .entry-box { background: rgba(0, 212, 255, 0.07); border: 2px solid #00d4ff; padding: 15px; border-radius: 12px; margin-top: 10px; color: white; }
    .trade-metric { background: #222; border: 1px solid #444; border-radius: 8px; padding: 10px; text-align: center; }
    .trade-metric h4 { margin: 0; color: #aaa; font-size: 14px; }
    .trade-metric h2 { margin: 5px 0 0 0; color: #fff; font-size: 20px; font-weight: bold; }
    
    .news-card { background: #1e1e1e; padding: 10px; margin-bottom: 8px; border-radius: 5px; }
    .news-positive { border-left: 4px solid #00ff00; }
    .news-negative { border-left: 4px solid #ff4b4b; }
    .news-neutral { border-left: 4px solid #00d4ff; }
    
    .news-title { font-weight: bold; font-size: 14px; color: #ececec; }
    .news-pub { font-size: 11px; color: #888; }
    
    /* Global Chat Styling with Auto-scroll behavior */
    .chat-container { 
        height: 400px; 
        overflow-y: auto; 
        display: flex; 
        flex-direction: column-reverse; /* Newest at bottom */
        background: #111; 
        padding: 10px; 
        border-radius: 8px;
        border: 1px solid #333;
    }
    .chat-msg { padding: 8px; border-radius: 5px; margin-bottom: 5px; background: #333; border-left: 3px solid #00d4ff; }
    .chat-user { font-weight: bold; color: #00d4ff; font-size: 12px; }
    .notif-container { padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 10px solid; background: #121212; }
    .notif-buy { border-color: #00ff00; color: #00ff00; box-shadow: 0 0 15px rgba(0, 255, 0, 0.2); }
    .notif-sell { border-color: #ff4b4b; color: #ff4b4b; box-shadow: 0 0 15px rgba(255, 75, 75, 0.2); }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "active_provider" not in st.session_state: st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}

# --- Helper Functions (DB & Auth) ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("Forex_User_DB")
        sheet = spreadsheet.sheet1
        try: chat_sheet = spreadsheet.worksheet("Chat")
        except: chat_sheet = spreadsheet.add_worksheet(title="Chat", rows="100", cols="3")
        return sheet, chat_sheet
    except: return None, None

def check_login(username, password):
    if username == "admin" and password == "admin123": 
        return {"Username": "Admin", "Role": "Admin", "HybridLimit": 9999, "UsageCount": 0}
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i.get("Username")) == username), None)
            if user and str(user.get("Password")) == password:
                return user
        except: return None
    return None

# NEW: Function to sync usage count to Google Sheets
def update_gsheet_usage(username, count):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            sheet.update_cell(cell.row, 4, count) # Assuming Column 4 is UsageCount
        except: pass

# --- Signal Engines & Analysis ---
def get_sentiment_class(title):
    title_lower = title.lower()
    negative_words = ['crash', 'drop', 'fall', 'plunge', 'loss', 'down', 'bear', 'weak', 'inflation', 'war', 'crisis', 'retreat', 'slump']
    positive_words = ['surge', 'rise', 'jump', 'gain', 'bull', 'up', 'strong', 'growth', 'profit', 'record', 'soar', 'rally', 'beat']
    if any(word in title_lower for word in negative_words): return "news-negative"
    elif any(word in title_lower for word in positive_words): return "news-positive"
    else: return "news-neutral"

def get_market_news(symbol):
    news_list = []
    clean_sym = symbol.replace("=X", "").replace("-USD", "")
    try:
        url = f"https://news.google.com/rss/search?q={clean_sym}+forex+market&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for item in root.findall('.//item')[:3]:
                news_list.append({"title": item.find('title').text, "link": item.find('link').text, "publisher": item.find('source').text if item.find('source') is not None else "News"})
            return news_list
    except: pass
    return []

def calculate_advanced_signals(df):
    if len(df) < 50: return None, 0
    signals = {}
    c = df['Close'].iloc[-1]
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    signals['ICT'] = ("Bullish FVG", "bull") if df['Low'].iloc[-1] > df['High'].iloc[-3] else (("Bearish FVG", "bear") if df['High'].iloc[-1] < df['Low'].iloc[-3] else ("No FVG", "neutral"))
    signals['TREND'] = ("Uptrend", "bull") if c > df['Close'].rolling(50).mean().iloc[-1] else ("Downtrend", "bear")
    score = (1 if signals['SMC'][1] == "bull" else -1) + (1 if signals['TREND'][1] == "bull" else -1) + (1 if signals['ICT'][1] == "bull" else -1)
    signals['SK'] = ("SK Sniper Buy", "bull") if score >= 2 else (("SK Sniper Sell", "bear") if score <= -2 else ("Waiting", "neutral"))
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    return signals, atr

def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr):
    trend, sk_signal = sigs['TREND'][0], sigs['SK'][1]
    if sk_signal == "bull":
        action, sl, tp = "BUY", curr_p - (atr * 1.5), curr_p + (atr * 3)
    elif sk_signal == "bear":
        action, sl, tp = "SELL", curr_p + (atr * 1.5), curr_p - (atr * 3)
    else:
        action, sl, tp = "WAIT", curr_p - atr, curr_p + atr
    
    return f"Pair: {pair} | Action: {action} | DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}"

def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info):
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr)
    current_usage, max_limit = user_info.get("UsageCount", 0), user_info.get("HybridLimit", 10)
    
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return algo_result, "Infinite Algo (Pure Mode - Unlimited)"

    try:
        prompt = f"Validate this trade: {algo_result}. Explanation in Sinhala. END with DATA: ENTRY=x | SL=x | TP=x"
        response = puter.ai.chat(prompt)
        if response and response.message:
            # Update Usage locally and in GSheet
            new_count = current_usage + 1
            st.session_state.user["UsageCount"] = new_count
            update_gsheet_usage(user_info['Username'], new_count)
            return response.message.content, f"Hybrid AI | Used: {new_count}/{max_limit}"
    except: pass
    return algo_result, "Infinite Algo (Fallback)"

def parse_ai_response(text):
    data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
    try:
        e = re.search(r"ENTRY\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        s = re.search(r"SL\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        t = re.search(r"TP\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        if e: data["ENTRY"] = e.group(1)
        if s: data["SL"] = s.group(1)
        if t: data["TP"] = t.group(1)
    except: pass
    return data

def scan_market(assets_list):
    results = []
    for symbol in assets_list:
        try:
            df = yf.download(symbol, period="5d", interval="15m", progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                sigs, _ = calculate_advanced_signals(df)
                if sigs:
                    results.append({"Pair": symbol.replace("=X",""), "Signal": sigs['SK'][0], "Price": df['Close'].iloc[-1], "Score": 2 if sigs['SK'][1]=='bull' else -2})
        except: pass
    return sorted(results, key=lambda x: abs(x['Score']), reverse=True)

# --- MAIN APP ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>⚡ INFINITE SYSTEM v8.0</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login_form"):
            u, p = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Access Terminal"):
                user = check_login(u, p)
                if user:
                    st.session_state.logged_in, st.session_state.user = True, user
                    st.rerun()
                else: st.error("Invalid Credentials")
else:
    user_info = st.session_state.user
    st.sidebar.title(f"👤 {user_info.get('Username')}")
    st.sidebar.caption(f"Hybrid Limit: {user_info.get('UsageCount',0)} / {user_info.get('HybridLimit',10)}")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    app_mode = st.sidebar.radio("Navigation", ["Terminal", "Market Scanner", "Trader Chat", "Admin Panel"])
    assets = {"Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"], "Crypto": ["BTC-USD", "ETH-USD"], "Metals": ["XAUUSD=X"]}

    if app_mode == "Terminal":
        market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
        pair = st.sidebar.selectbox("Select Asset", assets[market])
        tf = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h"])
        
        df = yf.download(pair, period="1mo", interval=tf, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr_p = float(df['Close'].iloc[-1])
            st.title(f"{pair.replace('=X', '')} Terminal - {curr_p:.5f}")
            sigs, atr = calculate_advanced_signals(df)
            
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

            c1, c2, c3 = st.columns(3)
            parsed = st.session_state.ai_parsed_data
            c1.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)

            if st.button("🚀 Analyze with Hybrid AI", use_container_width=True):
                news_items = get_market_news(pair)
                result, provider = get_hybrid_analysis(pair, {'price': curr_p}, sigs, news_items, atr, user_info)
                st.session_state.ai_parsed_data = parse_ai_response(result)
                st.session_state.ai_result = result.split("DATA:")[0]
                st.session_state.active_provider = provider
                st.rerun()
            
            if "ai_result" in st.session_state:
                st.markdown(f"**Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    elif app_mode == "Market Scanner":
        st.title("📡 AI Market Scanner")
        if st.button("Start Scan", type="primary"):
            results = scan_market(assets["Forex"] + assets["Crypto"])
            st.dataframe(pd.DataFrame(results))

    elif app_mode == "Trader Chat":
        st.title("💬 Global Trader Room")
        _, chat_sheet = get_user_sheet()
        
        # Load messages from Global GSheet
        if chat_sheet:
            messages = chat_sheet.get_all_records()
            chat_html = "".join([f"<div class='chat-msg'><span class='chat-user'>{m['user']}</span>: {m['text']} <span style='font-size:10px;color:#555;'>{m['time']}</span></div>" for m in messages[-50:]])
            # Displaying in a container with reverse-column for auto-scroll effect
            st.markdown(f"<div class='chat-container'>{chat_html}</div>", unsafe_allow_html=True)

        with st.form("chat_form", clear_on_submit=True):
            user_msg = st.text_input("Type your message...")
            if st.form_submit_button("Send") and user_msg:
                new_row = [user_info['Username'], user_msg, datetime.now().strftime("%H:%M")]
                chat_sheet.append_row(new_row)
                st.rerun()

    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Panel")
            sheet, _ = get_user_sheet()
            
            # Reset Logic
            if st.button("🔄 Reset Daily Usage (All Users)"):
                records = sheet.get_all_records()
                for i in range(2, len(records) + 2):
                    sheet.update_cell(i, 4, 0) # Set UsageCount column to 0
                st.success("All usage counts have been reset to 0.")

            st.subheader("User Management")
            if sheet:
                users_data = sheet.get_all_records()
                st.dataframe(pd.DataFrame(users_data))
                
                with st.form("update_limit"):
                    target = st.text_input("Username")
                    new_lim = st.number_input("New Limit", min_value=0)
                    if st.form_submit_button("Update Limit"):
                        cell = sheet.find(target)
                        sheet.update_cell(cell.row, 3, new_lim) # Col 3 is HybridLimit
                        st.success(f"Updated {target}")
        else:
            st.error("Access Denied.")
