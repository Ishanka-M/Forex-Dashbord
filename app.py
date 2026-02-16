import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import re
import requests
import numpy as np
import xml.etree.ElementTree as ET

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System v7.0 | Gemini 3 Flash", layout="wide", page_icon="⚡")

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
    .sig-box { padding: 10px; border-radius: 6px; font-size: 13px; text-align: center; font-weight: bold; border: 1px solid #444; margin-bottom: 5px; }
    .bull { background-color: #004d40; color: #00ff00; border-color: #00ff00; }
    .bear { background-color: #4a1414; color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background-color: #262626; color: #888; }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: 
    st.session_state.logged_in = False
if "active_provider" not in st.session_state: 
    st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state:
    st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}

# --- Helper Functions (Preserved) ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        return gspread.authorize(creds).open("Forex_User_DB").sheet1
    except: return None

def check_login(username, password):
    if username == "admin" and password == "admin123": return {"Username": "Admin", "Role": "Admin"}
    sheet = get_user_sheet()
    if sheet:
        try:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i.get("Username")) == username), None)
            if user and str(user.get("Password")) == password: return user
        except: return None
    return None

def create_user(new_username, new_password):
    sheet = get_user_sheet()
    if sheet:
        try:
            existing_users = sheet.col_values(1)
            if new_username in existing_users: return False, "User already exists!"
            sheet.append_row([new_username, new_password, "User", str(datetime.now())])
            return True, "User created successfully!"
        except Exception as e: return False, f"Error: {e}"
    return False, "Database Connection Failed"

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
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        url = f"https://news.google.com/rss/search?q={clean_sym}+forex+market&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for item in root.findall('.//item')[:5]:
                news_list.append({
                    "title": item.find('title').text,
                    "link": item.find('link').text,
                    "publisher": item.find('source').text if item.find('source') is not None else "Financial News"
                })
            if news_list: return news_list
    except: pass
    try:
        ticker = yf.Ticker(symbol)
        yf_news = ticker.news
        if yf_news: return yf_news[:5]
    except: pass
    return []

def get_alpha_vantage_data(pair):
    if "ALPHA_VANTAGE_KEY" not in st.secrets: return "API Key Missing"
    try:
        if "=X" in pair:
            base, quote = pair[:3], pair[3:6]
            url = f'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={base}&to_currency={quote}&apikey={st.secrets["ALPHA_VANTAGE_KEY"]}'
        else:
            base = pair.split("-")[0]
            url = f'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={base}&to_currency=USD&apikey={st.secrets["ALPHA_VANTAGE_KEY"]}'
        r = requests.get(url, timeout=10)
        return r.json().get("Realtime Currency Exchange Rate", "No data available")
    except: return "Conn Error"

# --- 4. ADVANCED SIGNAL ENGINE (WITH ELLIOTT WAVE) ---
def calculate_advanced_signals(df):
    signals = {}
    c, h, l = df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    
    # Existing Theories
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    signals['ICT'] = ("Bullish FVG", "bull") if df['Low'].iloc[-1] > df['High'].iloc[-3] else (("Bearish FVG", "bear") if df['High'].iloc[-1] < df['Low'].iloc[-3] else ("No FVG", "neutral"))
    ph, pl = df['High'].rolling(50).max().iloc[-1], df['Low'].rolling(50).min().iloc[-1]
    fib_618 = ph - ((ph - pl) * 0.618)
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.0005) else ("Ranging", "neutral")
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi_val = 100 - (100 / (1 + (gain / loss))).iloc[-1]
    signals['RETAIL'] = ("Overbought", "bear") if rsi_val > 70 else (("Oversold", "bull") if rsi_val < 30 else (f"Neutral ({int(rsi_val)})", "neutral"))
    
    signals['LIQ'] = ("Liquidity Grab (L)", "bull") if l < df['Low'].iloc[-10:-1].min() else (("Liquidity Grab (H)", "bear") if h > df['High'].iloc[-10:-1].max() else ("Holding", "neutral"))
    signals['TREND'] = ("Uptrend", "bull") if c > df['Close'].rolling(50).mean().iloc[-1] else ("Downtrend", "bear")
    
    score = (1 if signals['SMC'][1] == "bull" else -1) + (1 if signals['TREND'][1] == "bull" else -1)
    signals['SK'] = ("SK Sniper Buy", "bull") if score >= 1 else (("SK Sniper Sell", "bear") if score <= -1 else ("Waiting", "neutral"))
    signals['PATT'] = ("Engulfing", "bull") if (df['Close'].iloc[-1] > df['Open'].iloc[-1] and df['Close'].iloc[-1] > df['Open'].iloc[-2]) else ("None", "neutral")

    # --- NEW: ELLIOTT WAVE THEORY LOGIC ---
    # Simplified detection based on 3-bar and 10-bar fractals
    last_50 = df['Close'].tail(50)
    max_50, min_50 = last_50.max(), last_50.min()
    current_pos = (c - min_50) / (max_50 - min_50) if (max_50 - min_50) != 0 else 0.5
    
    if signals['TREND'][1] == "bull":
        if current_pos > 0.8: ew_status, ew_col = "Wave 5 (Exhaustion)", "bear"
        elif 0.4 < current_pos <= 0.8: ew_status, ew_col = "Wave 3 (Strong Impulse)", "bull"
        else: ew_status, ew_col = "Wave 1 (Initial)", "bull"
    else:
        if current_pos < 0.2: ew_status, ew_col = "Wave C (Final Drop)", "bull"
        elif 0.2 <= current_pos < 0.6: ew_status, ew_col = "Wave A (Correction)", "bear"
        else: ew_status, ew_col = "Wave B (Bear Rally)", "neutral"
    
    signals['ELLIOTT'] = (ew_status, ew_col)
    
    return signals

# --- 5. ENHANCED AI ENGINE ---
def query_huggingface_fallback(prompt):
    if "HF_TOKEN" not in st.secrets: return None
    API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
    headers = {"Authorization": f"Bearer {st.secrets['HF_TOKEN']}"}
    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": prompt, "parameters": {"max_new_tokens": 500}}, timeout=15)
        res = response.json()
        return res[0]['generated_text'] if isinstance(res, list) else None
    except: return None

def get_ai_analysis(prompt, asset_data):
    if "GEMINI_KEYS" in st.secrets:
        keys = st.secrets["GEMINI_KEYS"]
        if isinstance(keys, str): keys = [keys]
        for i, key in enumerate(keys):
            st.toast(f"Checking API Key {i+1}/7...", icon="🔍")
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel('gemini-2.0-flash-exp') 
                response = model.generate_content(prompt)
                if response and response.text:
                    return response.text, f"Gemini 3 Flash (Key #{i+1})"
            except Exception: continue

    st.toast("Switching to Fallback Engine (HF)...", icon="🔄")
    hf_result = query_huggingface_fallback(prompt)
    if hf_result: return hf_result, "HF Fallback (Mistral)"

    sl, tp = asset_data['price'] * 0.995, asset_data['price'] * 1.01
    return f"ANALYSIS: AI Critical Error.\nDATA: ENTRY={asset_data['price']} | SL={sl:.4f} | TP={tp:.4f}", "Offline"

def parse_ai_response(text):
    data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
    try:
        entry_match = re.search(r"ENTRY\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        sl_match = re.search(r"SL\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        tp_match = re.search(r"TP\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        if entry_match: data["ENTRY"] = entry_match.group(1)
        if sl_match: data["SL"] = sl_match.group(1)
        if tp_match: data["TP"] = tp_match.group(1)
    except: pass
    return data

# --- 6. MAIN APPLICATION ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>⚡ INFINITE SYSTEM v7.0</h1>", unsafe_allow_html=True)
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
    user_info = st.session_state.get('user', {})
    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    st.sidebar.divider()
    market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
    assets = {"Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"], "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD"], "Metals": ["XAUUSD=X"]}
    pair = st.sidebar.selectbox("Select Asset", assets[market], format_func=lambda x: x.replace("=X", "").replace("-USD", ""))
    tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h"], index=2)
    
    st.sidebar.divider()
    st.sidebar.subheader("📰 Market News")
    news_items = get_market_news(pair)
    if news_items:
        for news in news_items:
            n_link, n_title, n_pub = news.get('link', '#'), news.get('title', 'No Title'), news.get('publisher', 'Financial News')
            color_class = get_sentiment_class(n_title)
            st.sidebar.markdown(f"<div class='news-card {color_class}'><a href='{n_link}' target='_blank' style='text-decoration:none;'><div class='news-title'>{n_title}</div></a><div class='news-pub'>{n_pub}</div></div>", unsafe_allow_html=True)
        
    live = st.sidebar.checkbox("🔴 Real-time Refresh", value=True)
    df = yf.download(pair, period="5d", interval=tf, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        curr_p = float(df['Close'].iloc[-1])
        st.title(f"{pair.replace('=X', '')} Terminal - {curr_p:.5f}")

        # --- SIGNALS DISPLAY (Updated to include Elliott) ---
        sigs = calculate_advanced_signals(df)
        keys_list = list(sigs.keys()) # Now contains 9 signals
        
        cols = st.columns(3) # Adjusted for 9 boxes (3x3 grid)
        for i in range(3):
            cols[i].markdown(f"<div class='sig-box {sigs[keys_list[i]][1]}'>{keys_list[i]}: {sigs[keys_list[i]][0]}</div>", unsafe_allow_html=True)
            cols[i].markdown(f"<div class='sig-box {sigs[keys_list[i+3]][1]}'>{keys_list[i+3]}: {sigs[keys_list[i+3]][0]}</div>", unsafe_allow_html=True)
            cols[i].markdown(f"<div class='sig-box {sigs[keys_list[i+6]][1]}'>{keys_list[i+6]}: {sigs[keys_list[i+6]][0]}</div>", unsafe_allow_html=True)

        st.plotly_chart(go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])]).update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=20, b=0)), use_container_width=True)

        st.markdown("### 🎯 AI Trade Plan")
        t_c1, t_c2, t_c3 = st.columns(3)
        parsed = st.session_state.ai_parsed_data
        with t_c1: st.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
        with t_c2: st.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
        with t_c3: st.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)

        st.divider()
        c_ai, c_res = st.columns([1, 2])
        with c_ai:
            st.subheader("🚀 AI Sniper Analysis")
            if st.button("Generate Gemini 3 Analysis", use_container_width=True):
                with st.spinner("Analyzing News + Technicals + Elliott Wave..."):
                    news_titles = [n.get('title', '') for n in news_items[:3]]
                    news_context = " | ".join(news_titles) if news_titles else "No major news."
                    
                    # AI Prompt updated with Elliott Wave context
                    prompt = f"""
                    Analyze {pair} at Price: {curr_p} on {tf}.
                    Technicals: 
                    Trend: {sigs['TREND'][0]}
                    SMC: {sigs['SMC'][0]}
                    RSI: {sigs['RETAIL'][0]}
                    Elliott Wave: {sigs['ELLIOTT'][0]}
                    
                    News Context: {news_context}
                    
                    1. Provide trade confirmation in Sinhala, specifically considering Elliott Wave position.
                    2. Format levels at the end: DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx
                    """
                    result, provider = get_ai_analysis(prompt, {'price': curr_p})
                    st.session_state.ai_parsed_data = parse_ai_response(result)
                    st.session_state.ai_result = result.split("DATA:")[0] if "DATA:" in result else result
                    st.session_state.active_provider = provider
                    st.rerun()

        with c_res:
            if "ai_result" in st.session_state:
                st.markdown(f"**Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    if live:
        time.sleep(60)
        st.rerun()
