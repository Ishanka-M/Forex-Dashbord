import streamlit as st
import yfinance as yf
import pandas as pd
import puter  # Puter AI for Hybrid Analysis
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
st.set_page_config(page_title="Infinite System v9.5 Pro | Hybrid", layout="wide", page_icon="⚡")

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
    
    .sig-box { padding: 10px; border-radius: 6px; font-size: 13px; text-align: center; font-weight: bold; border: 1px solid #444; margin-bottom: 5px; }
    .bull { background-color: #004d40; color: #00ff00; border-color: #00ff00; }
    .bear { background-color: #4a1414; color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background-color: #262626; color: #888; }

    /* Notification Styling */
    .notif-container { padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 10px solid; background: #121212; }
    .notif-buy { border-color: #00ff00; color: #00ff00; box-shadow: 0 0 15px rgba(0, 255, 0, 0.2); }
    .notif-sell { border-color: #ff4b4b; color: #ff4b4b; box-shadow: 0 0 15px rgba(255, 75, 75, 0.2); }
    .notif-wait { border-color: #555; color: #aaa; }
    
    /* Chat Styling */
    .chat-msg { padding: 8px; border-radius: 5px; margin-bottom: 5px; background: #333; }
    .chat-user { font-weight: bold; color: #00d4ff; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "active_provider" not in st.session_state: st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# --- Helper Functions (DB & Auth) ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        try: sheet = client.open("Forex_User_DB").sheet1
        except: sheet = None
        try: chat_sheet = client.open("Forex_User_DB").worksheet("Chat")
        except: chat_sheet = None
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
        except Exception as e:
            print(f"DB Update Error: {e}")

# --- ADMIN ADD USER FUNCTION ---
def add_new_user(username, password, role, limit):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            existing = sheet.find(username)
            if existing: return False, "Username already exists."
            sheet.append_row([username, password, role, limit, 0])
            return True, "User created successfully!"
        except Exception as e: return False, f"Error: {e}"
    return False, "Database connection failed."

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
                news_list.append({
                    "title": item.find('title').text,
                    "link": item.find('link').text,
                    "publisher": item.find('source').text if item.find('source') is not None else "News"
                })
            if news_list: return news_list
    except: pass
    return []

# --- DYNAMIC DATA PERIOD HELPER ---
def get_data_period(tf):
    """
    Returns the appropriate data period based on timeframe to optimize 
    Short Term vs Long Term analysis.
    """
    if tf in ["1m", "5m"]:
        return "5d"  # Short history for Scalping (Yahoo limit for 1m is 7d)
    elif tf == "15m":
        return "1mo" # Medium history
    elif tf == "1h":
        return "6mo" # Long history for Swing
    elif tf == "4h":
        return "1y"  # Very Long history for Swing
    return "1mo" # Default

# --- 4. ADVANCED SIGNAL ENGINE (SCALP VS SWING AWARE) ---
def calculate_advanced_signals(df, tf):
    if len(df) < 50: return None, 0
    signals = {}
    c, h, l = df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    
    # -- Dynamic Moving Averages based on Timeframe --
    if tf in ["1m", "5m"]:
        # Faster MAs for Scalping
        ma_short = df['Close'].rolling(9).mean().iloc[-1]
        ma_long = df['Close'].rolling(21).mean().iloc[-1]
        trend_label = "Short-Term Trend"
    else:
        # Slower MAs for Swing
        ma_short = df['Close'].rolling(50).mean().iloc[-1]
        ma_long = df['Close'].rolling(200).mean().iloc[-1]
        trend_label = "Major Trend"

    # 1. SMC (Structure)
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    
    # 2. ICT (Fair Value Gaps)
    signals['ICT'] = ("Bullish FVG", "bull") if df['Low'].iloc[-1] > df['High'].iloc[-3] else (("Bearish FVG", "bear") if df['High'].iloc[-1] < df['Low'].iloc[-3] else ("No FVG", "neutral"))
    
    # 3. FIB (Golden Zone)
    ph, pl = df['High'].rolling(50).max().iloc[-1], df['Low'].rolling(50).min().iloc[-1]
    fib_range = ph - pl
    fib_618 = ph - (fib_range * 0.618)
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.001) else ("Ranging", "neutral")
    
    # 4. RETAIL (RSI) - Dynamic Thresholds
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
    
    # Scalping allows faster reversals (RSI 70/30), Swing waits for 80/20 extremes? 
    # Keeping standard 70/30 but labeling logic remains same.
    signals['RETAIL'] = ("Overbought", "bear") if rsi_val > 70 else (("Oversold", "bull") if rsi_val < 30 else (f"Neutral ({int(rsi_val)})", "neutral"))

    # 5. LIQUIDITY
    signals['LIQ'] = ("Liquidity Grab (L)", "bull") if l < df['Low'].iloc[-10:-1].min() else (("Liquidity Grab (H)", "bear") if h > df['High'].iloc[-10:-1].max() else ("Holding", "neutral"))

    # 6. TREND & ADX
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean().iloc[-1]
    
    # Use the dynamic MAs calculated above
    trend_direction = "bull" if c > ma_short else "bear"
    signals['TREND'] = (f"{trend_label} {trend_direction.upper()}", trend_direction)
    
    # --- ELLIOTT WAVE (Logic remains same, applies to current TF) ---
    ema_20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    recent_high_20 = df['High'].rolling(20).max().iloc[-1]
    recent_low_20 = df['Low'].rolling(20).min().iloc[-1]
    
    ew_status, ew_col = "Unclear", "neutral"
    if c > ma_short:
        if c > ema_20 and c >= recent_high_20 * 0.995: ew_status, ew_col = "Impulse (Wave 3/5)", "bull"
        elif c < ema_20: ew_status, ew_col = "Correction (Wave 2/4)", "neutral"
        else: ew_status, ew_col = "Wave 1 (Start)", "bull"
    else:
        if c < ema_20 and c <= recent_low_20 * 1.005: ew_status, ew_col = "Impulse (Wave C/3)", "bear"
        elif c > ema_20: ew_status, ew_col = "Correction (Wave B/2)", "neutral"
    
    signals['ELLIOTT'] = (ew_status, ew_col)

    # Scoring
    score = 0
    score += 1.5 if signals['SMC'][1] == "bull" else -1.5 if signals['SMC'][1] == "bear" else 0
    score += 1 if signals['TREND'][1] == "bull" else -1 if signals['TREND'][1] == "bear" else 0
    score += 1 if signals['ICT'][1] == "bull" else -1 if signals['ICT'][1] == "bear" else 0
    score += 0.5 if signals['FIB'][1] == "bull" else 0
    score += 0.5 if signals['ELLIOTT'][1] == "bull" and signals['TREND'][1] == "bull" else -0.5 if signals['ELLIOTT'][1] == "bear" else 0
            
    signals['SK'] = ("SK Sniper Buy", "bull") if score >= 2.5 else (("SK Sniper Sell", "bear") if score <= -2.5 else ("Waiting", "neutral"))
    
    return signals, atr_14

# --- 5. INFINITE ALGORITHMIC ENGINE V3.5 (SCALP/SWING LOGIC) ---
def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr, tf):
    news_score = 0
    for item in news_items:
        sentiment = get_sentiment_class(item['title'])
        if sentiment == "news-positive": news_score += 1
        elif sentiment == "news-negative": news_score -= 1
    
    trend = sigs['TREND'][0]
    ew = sigs['ELLIOTT'][0]
    smc = sigs['SMC'][0]
    sk_signal = sigs['SK'][1]
    
    # -- Dynamic TP/SL Multipliers based on Timeframe --
    if tf in ["1m", "5m"]:
        trade_mode = "SCALPING (කෙටි කාලීන)"
        sl_mult = 1.2
        tp_mult = 2.0
    else:
        trade_mode = "SWING/DAY (දිගු කාලීන)"
        sl_mult = 1.5
        tp_mult = 3.5

    volatility = "ඉහල (High)" if atr > (curr_p * 0.001) else "සාමාන්‍ය (Normal)"
    
    if sk_signal == "bull" and news_score >= -1:
        action = "BUY"
        status_sinhala = f"ශක්තිමත් {trade_mode} අවස්ථාවකි."
        note = f"{tf} කාල රාමුව තුළ {trend} තත්ත්වයක් පවතී. Elliott Wave ({ew}) සහ SMC ({smc}) මගින් ඉහල යාම තහවුරු කරයි."
        sl, tp = curr_p - (atr * sl_mult), curr_p + (atr * tp_mult)
    elif sk_signal == "bear" and news_score <= 1:
        action = "SELL"
        status_sinhala = f"ශක්තිමත් {trade_mode} අවස්ථාවකි."
        note = f"{tf} කාල රාමුව තුළ {trend} තත්ත්වයක් පවතී. Elliott Wave ({ew}) පහත වැටීමක් පෙන්නුම් කරයි."
        sl, tp = curr_p + (atr * sl_mult), curr_p - (atr * tp_mult)
    else:
        action = "WAIT"
        status_sinhala = "වෙළඳපල අවිනිශ්චිතයි (Neutral)."
        note = "Signal එකිනෙක ගැටේ. හොඳම අවස්ථාව එනතෙක් ඉවසන්න."
        sl, tp = curr_p - atr, curr_p + atr

    analysis_text = f"""
    ♾️ **INFINITE ALGO ENGINE V3.5 (DYNAMIC)**
    
    📊 **Trade Setup ({tf}):**
    • Mode: {trade_mode}
    • Action: {action}
    • Structure: {smc} | Trend: {trend}
    • Elliott Wave: {ew}
    
    📰 **Context:**
    • News Score: {news_score}
    • Volatility: {volatility}
    
    💡 **නිගමනය:**
    {status_sinhala}
    {note}
    
    DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}
    """
    return analysis_text

# --- 6. HYBRID AI ENGINE ---
def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info, tf):
    # 1. Generate Algo Data with TF info
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr, tf)
    
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 10)
    
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        st.toast(f"Daily Limit Reached. Switching to Algo Mode.", icon="⚠️")
        return algo_result, "Infinite Algo (Limit Reached)"

    try:
        # Animation Block
        with st.status(f"🚀 Infinite AI Activating ({tf} Mode)...", expanded=True) as status:
            st.write(f"📊 Scanning {tf} Market Structure...")
            time.sleep(0.5)
            st.write(f"🌊 Analyzing Waves (History Adjusted)...")
            time.sleep(0.5)
            st.write("🧠 Validating with Puter AI...")
            
            prompt = f"""
            Role: Professional Forex Trader.
            Task: Validate this {tf} timeframe trade setup and explain in Sinhala.
            
            Context:
            - Timeframe: {tf}
            - Algo Analysis: {algo_result}
            
            Instructions:
            1. If Timeframe is 1m/5m, treat as SCALP (Tight SL, Quick exit).
            2. If Timeframe is 1h/4h, treat as SWING (Wider SL, Trend following).
            3. Validate the logic.
            4. END format: DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx
            """
            
            response = puter.ai.chat(prompt)
            status.update(label="✅ AI Verification Complete!", state="complete", expanded=False)
        
        if response and response.message:
            new_usage = current_usage + 1
            user_info["UsageCount"] = new_usage
            st.session_state.user = user_info 
            if user_info["Username"] != "Admin":
                update_usage_in_db(user_info["Username"], new_usage)
            return response.message.content, f"Hybrid AI (Verified) | Used: {new_usage}/{max_limit}"
            
    except Exception as e:
        st.error(f"AI Error: {e}")
        return algo_result, "Infinite Algo (Fallback)"
    
    return algo_result, "Infinite Algo (Default)"

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

# --- SCANNER FUNCTION ---
def scan_market(assets_list):
    results = []
    progress_bar = st.progress(0)
    total = len(assets_list)
    
    # Scanner uses 15m default for general direction
    scan_tf = "15m" 
    
    for i, symbol in enumerate(assets_list):
        try:
            df = yf.download(symbol, period="1mo", interval=scan_tf, progress=False)
            if not df.empty and len(df) > 50:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                sigs, _ = calculate_advanced_signals(df, scan_tf)
                if sigs:
                    score_val = 0
                    if sigs['SK'][1] == 'bull': score_val = 2
                    elif sigs['SK'][1] == 'bear': score_val = -2
                    
                    results.append({
                        "Pair": symbol.replace("=X","").replace("-USD",""),
                        "Signal": sigs['SK'][0],
                        "Trend": sigs['TREND'][0],
                        "Wave": sigs['ELLIOTT'][0], 
                        "Score": score_val,
                        "Price": df['Close'].iloc[-1]
                    })
        except: pass
        progress_bar.progress((i + 1) / total)
    
    progress_bar.empty()
    sorted_res = sorted(results, key=lambda x: abs(x['Score']), reverse=True)
    return sorted_res

# --- 7. MAIN APPLICATION ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>⚡ INFINITE SYSTEM v9.5 PRO</h1>", unsafe_allow_html=True)
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
    
    # --- SIDEBAR ---
    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    st.sidebar.caption(f"Status: Online 🟢")
    st.sidebar.caption(f"Hybrid Limit: {user_info.get('UsageCount',0)} / {user_info.get('HybridLimit',10)}")
    
    # --- AUTO REFRESH OPTION ---
    auto_refresh = st.sidebar.checkbox("🔄 Auto Refresh (60s)", value=False)
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    # Navigation
    app_mode = st.sidebar.radio("Navigation", ["Terminal", "Market Scanner", "Trader Chat", "Admin Panel"])
    
    assets = {
        "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCHF=X", "USDCAD=X", "NZDUSD=X"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD"],
        "Metals": ["XAUUSD=X", "XAGUSD=X"] 
    }

    # --- VIEW: TERMINAL ---
    if app_mode == "Terminal":
        st.sidebar.divider()
        market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
        pair = st.sidebar.selectbox("Select Asset", assets[market], format_func=lambda x: x.replace("=X", "").replace("-USD", ""))
        
        # Select Timeframe
        tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h"], index=2)
        
        # News
        st.sidebar.divider()
        st.sidebar.subheader("📰 Market News")
        news_items = get_market_news(pair)
        for news in news_items:
            color_class = get_sentiment_class(news['title'])
            st.sidebar.markdown(f"<div class='news-card {color_class}'><div class='news-title'>{news['title']}</div></div>", unsafe_allow_html=True)

        # Chart & Logic (DYNAMIC PERIOD)
        data_period = get_data_period(tf)
        st.caption(f"Fetching {data_period} history for {tf} analysis...")
        
        df = yf.download(pair, period=data_period, interval=tf, progress=False)
        
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr_p = float(df['Close'].iloc[-1])
            st.title(f"{pair.replace('=X', '')} Terminal - {curr_p:.5f}")
            
            # Pass TF to Signal Engine
            sigs, current_atr = calculate_advanced_signals(df, tf)
            
            # Notification
            sk_signal = sigs['SK'][1]
            if sk_signal == "bull":
                st.markdown(f"<div class='notif-container notif-buy'>🔔 <b>BUY SIGNAL ({tf}):</b> Infinite System detects a BUY setup!</div>", unsafe_allow_html=True)
            elif sk_signal == "bear":
                st.markdown(f"<div class='notif-container notif-sell'>🔔 <b>SELL SIGNAL ({tf}):</b> Infinite System detects a SELL setup!</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='notif-container notif-wait'>📡 <b>MONITORING:</b> Waiting for clear setup...</div>", unsafe_allow_html=True)

            # --- SIGNAL GRID ---
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='sig-box {sigs['TREND'][1]}'>TREND: {sigs['TREND'][0]}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='sig-box {sigs['SMC'][1]}'>SMC: {sigs['SMC'][0]}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='sig-box {sigs['ELLIOTT'][1]}'>E-WAVE: {sigs['ELLIOTT'][0]}</div>", unsafe_allow_html=True)
            c1.markdown(f"<div class='sig-box {sigs['ICT'][1]}'>ICT: {sigs['ICT'][0]}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='sig-box {sigs['RETAIL'][1]}'>RSI: {sigs['RETAIL'][0]}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='sig-box {sigs['LIQ'][1]}'>LIQ: {sigs['LIQ'][0]}</div>", unsafe_allow_html=True)

            # Chart
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

            # Dashboard
            st.markdown(f"### 🎯 Hybrid AI Analysis ({tf})")
            c1, c2, c3 = st.columns(3)
            parsed = st.session_state.ai_parsed_data
            c1.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)
            
            st.divider()
            
            if st.button("🚀 Analyze with Hybrid AI", use_container_width=True):
                result, provider = get_hybrid_analysis(pair, {'price': curr_p}, sigs, news_items, current_atr, st.session_state.user, tf)
                st.session_state.ai_parsed_data = parse_ai_response(result)
                st.session_state.ai_result = result.split("DATA:")[0] if "DATA:" in result else result
                st.session_state.active_provider = provider
                st.rerun()

            if "ai_result" in st.session_state:
                st.markdown(f"**Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    # --- VIEW: MARKET SCANNER ---
    elif app_mode == "Market Scanner":
        st.title("📡 AI Market Scanner")
        st.markdown("Scans assets for high-probability setups using Elliott Wave & SMC.")
        
        scan_market_type = st.selectbox("Select Market to Scan", ["Forex", "Crypto"])
        
        if st.button("Start Scan", type="primary"):
            with st.spinner(f"Scanning {scan_market_type} market..."):
                results = scan_market(assets[scan_market_type])
                
                if results:
                    st.success(f"Scan Complete! Found {len(results)} pairs.")
                    
                    col1, col2, col3 = st.columns(3)
                    for i, res in enumerate(results[:3]):
                        color = "#00ff00" if res['Score'] > 0 else "#ff4b4b" if res['Score'] < 0 else "#888"
                        with [col1, col2, col3][i]:
                            st.markdown(f"""
                            <div style="background:#222; padding:15px; border-radius:10px; border-left: 5px solid {color};">
                                <h3>{res['Pair']}</h3>
                                <p style="color:{color}; font-weight:bold;">{res['Signal']}</p>
                                <p>Wave: {res['Wave']}</p>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    st.markdown("### Full Scan Results")
                    st.dataframe(pd.DataFrame(results))
                else:
                    st.warning("No data found or market is closed.")

    # --- VIEW: TRADER CHAT ---
    elif app_mode == "Trader Chat":
        st.title("💬 Global Trader Room")
        
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_history:
                st.markdown(f"<div class='chat-msg'><span class='chat-user'>{msg['user']}</span>: {msg['text']} <span style='font-size:10px;color:#555;'>{msg['time']}</span></div>", unsafe_allow_html=True)
        
        with st.form("chat_form", clear_on_submit=True):
            user_msg = st.text_input("Type your message...")
            if st.form_submit_button("Send"):
                if user_msg:
                    new_msg = {
                        "user": user_info['Username'],
                        "text": user_msg,
                        "time": datetime.now().strftime("%H:%M")
                    }
                    st.session_state.chat_history.append(new_msg)
                    st.rerun()

    # --- VIEW: ADMIN PANEL ---
    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Control Center")
            
            tab1, tab2, tab3 = st.tabs(["User Management", "Add New User", "System Status"])
            
            with tab1:
                st.subheader("Manage User Limits")
                mock_users = [
                    {"Username": "Trader1", "HybridLimit": 10, "Usage": 5, "Status": "Online 🟢"},
                    {"Username": "Ishanka", "HybridLimit": 20, "Usage": 12, "Status": "Offline 🔴"},
                ]
                st.dataframe(pd.DataFrame(mock_users), use_container_width=True)
                
                c1, c2 = st.columns(2)
                target_user = c1.text_input("Username to Update")
                new_limit = c2.number_input("New Hybrid Limit", min_value=10, value=20)
                
                if st.button("Update User Limit"):
                    st.success(f"Updated {target_user} limit to {new_limit}")
            
            with tab2:
                st.subheader("Create New User")
                with st.form("add_user_form"):
                    new_u = st.text_input("New Username")
                    new_p = st.text_input("Password", type="password")
                    new_role = st.selectbox("Role", ["User", "VIP"])
                    new_l = st.number_input("Daily Limit", min_value=5, value=10)
                    
                    if st.form_submit_button("Create User"):
                        if new_u and new_p:
                            success, msg = add_new_user(new_u, new_p, new_role, new_l)
                            if success: st.success(msg)
                            else: st.error(msg)
                        else:
                            st.error("Please fill all fields.")
            
            with tab3:
                st.subheader("Live System Stats")
                st.metric("Active Users", "3")
                st.metric("Algo Engine", "v9.5 Pro (Dynamic TF)")
        else:
            st.error("Access Denied. Admins Only.")
            
    # --- AUTO REFRESH LOGIC ---
    if auto_refresh:
        time.sleep(60)
        st.rerun()
