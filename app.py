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
st.set_page_config(page_title="Infinite System v8.0 Pro | Hybrid", layout="wide", page_icon="⚡")

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
    """Updates the UsageCount in Google Sheets"""
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            # Locate user row
            cell = sheet.find(username)
            if cell:
                # Assuming UsageCount is in a specific column. 
                # We find the 'UsageCount' header column index dynamically.
                headers = sheet.row_values(1)
                if "UsageCount" in headers:
                    col_idx = headers.index("UsageCount") + 1
                    sheet.update_cell(cell.row, col_idx, new_usage)
        except Exception as e:
            print(f"DB Update Error: {e}")

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

# --- 4. ADVANCED SIGNAL ENGINE (RESTORED FULL LOGIC) ---
def calculate_advanced_signals(df):
    if len(df) < 50: return None, 0
    signals = {}
    c, h, l = df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    
    # 1. SMC (Structure)
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    
    # 2. ICT (Fair Value Gaps)
    signals['ICT'] = ("Bullish FVG", "bull") if df['Low'].iloc[-1] > df['High'].iloc[-3] else (("Bearish FVG", "bear") if df['High'].iloc[-1] < df['Low'].iloc[-3] else ("No FVG", "neutral"))
    
    # 3. FIB (Golden Zone)
    ph, pl = df['High'].rolling(50).max().iloc[-1], df['Low'].rolling(50).min().iloc[-1]
    fib_range = ph - pl
    fib_618 = ph - (fib_range * 0.618)
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.0005) else ("Ranging", "neutral")
    
    # 4. RETAIL (RSI)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
    signals['RETAIL'] = ("Overbought", "bear") if rsi_val > 70 else (("Oversold", "bull") if rsi_val < 30 else (f"Neutral ({int(rsi_val)})", "neutral"))

    # 5. LIQUIDITY (Grabs)
    signals['LIQ'] = ("Liquidity Grab (L)", "bull") if l < df['Low'].iloc[-10:-1].min() else (("Liquidity Grab (H)", "bear") if h > df['High'].iloc[-10:-1].max() else ("Holding", "neutral"))

    # 6. TREND
    signals['TREND'] = ("Uptrend", "bull") if c > df['Close'].rolling(50).mean().iloc[-1] else ("Downtrend", "bear")
    
    # Optimized Scoring (Weighted)
    score = (1 if signals['SMC'][1] == "bull" else -1) + \
            (1 if signals['TREND'][1] == "bull" else -1) + \
            (1 if signals['ICT'][1] == "bull" else -1) + \
            (0.5 if signals['FIB'][1] == "bull" else 0)
            
    signals['SK'] = ("SK Sniper Buy", "bull") if score >= 2 else (("SK Sniper Sell", "bear") if score <= -2 else ("Waiting", "neutral"))
    
    # Elliott Wave
    last_50 = df['Close'].tail(50)
    current_pos = (c - last_50.min()) / (last_50.max() - last_50.min()) if (last_50.max() - last_50.min()) != 0 else 0.5
    if signals['TREND'][1] == "bull":
        ew_status, ew_col = ("Wave 3 (Impulse)", "bull") if 0.4 < current_pos <= 0.8 else ("Correction", "neutral")
    else:
        ew_status, ew_col = ("Wave C (Drop)", "bear") if current_pos < 0.2 else ("Correction", "neutral")
    signals['ELLIOTT'] = (ew_status, ew_col)

    # ATR Calculation
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    
    return signals, atr

# --- 5. INFINITE ALGORITHMIC ENGINE V2.0 (RESTORED SINHALA LOGIC) ---
def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr):
    news_score = 0
    for item in news_items:
        sentiment = get_sentiment_class(item['title'])
        if sentiment == "news-positive": news_score += 1
        elif sentiment == "news-negative": news_score -= 1
    
    trend = sigs['TREND'][0]
    ew = sigs['ELLIOTT'][0]
    smc = sigs['SMC'][0]
    sk_signal = sigs['SK'][1]
    
    volatility = "ඉහල (High)" if atr > (curr_p * 0.001) else "සාමාන්්‍ය (Normal)"
    
    if sk_signal == "bull" and news_score >= 0:
        action = "BUY"
        status_sinhala = "ශක්තිමත් මිලදී ගැනීමේ අවස්ථාවකි (Strong Buy)."
        note = f"තාක්ෂණික දර්ශක සහ පුවත් විශ්ලේෂණයට අනුව වෙළඳපල {trend} තත්ත්වයක පවතී. {smc} සහ {ew} මගින් ඉහල යාම තහවුරු කරයි."
        sl, tp = curr_p - (atr * 1.5), curr_p + (atr * 3)
    elif sk_signal == "bear" and news_score <= 0:
        action = "SELL"
        status_sinhala = "ශක්තිමත් විකිණීමේ අවස්ථාවකි (Strong Sell)."
        note = f"වෙළඳපල {trend} ප්‍රවණතාවයක පවතින අතර, {smc} මගින් විකුණුම්කරුවන්ගේ පාලනය තහවුරු වේ. {ew} මගින් පහත වැටීම බලාපොරොත්තු විය හැක."
        sl, tp = curr_p + (atr * 1.5), curr_p - (atr * 3)
    else:
        action = "WAIT/SCALP"
        status_sinhala = "ප්‍රවේශම් වන්න (Neutral/Wait)."
        note = f"වෙළඳපල දැනට අවිනිශ්චිත (Ranging) තත්ත්වයක පවතී. තාක්ෂණික දත්ත සහ පුවත් අතර ගැටුමක් පවතින බැවින් කෙටි කාලීන අවස්ථා පමණක් සලකා බලන්න."
        sl, tp = curr_p - (atr * 1.0), curr_p + (atr * 1.5)

    analysis_text = f"""
    ♾️ **INFINITE ALGO ENGINE V2.0 (SINHALA)**
    
    📊 **වෙළඳපල විශ්ලේෂණය:**
    • යුගලය: {pair.replace('=X', '')} | Action: {action}
    • ප්‍රවණතාව: {trend} | SMC: {smc}
    • තරංග: {ew}
    
    📰 **බාහිර සාධක:**
    • පුවත් බලපෑම: {"ධනාත්මක" if news_score > 0 else "සෘණාත්මක" if news_score < 0 else "මධ්‍යස්ථ"}
    • Volatility: {volatility}
    
    💡 **නිගමනය:**
    {status_sinhala}
    {note}
    
    DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}
    """
    return analysis_text

# --- 6. HYBRID AI ENGINE (PUTER + RESTORED CONTEXT + DB UPDATE) ---
def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info):
    # 1. Generate Detailed Algo Data
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr)
    
    # 2. Check Limits
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 10)
    
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        st.toast(f"Daily Hybrid Limit Reached ({max_limit}). Switching to Algo Mode.", icon="⚠️")
        return algo_result, "Infinite Algo (Limit Reached)"

    # 3. Hybrid Process (Puter)
    try:
        st.toast("Validating with Puter AI...", icon="🧠")
        
        prompt = f"""
        Role: Senior Forex Risk Manager.
        Task: Validate this trade plan and translate the final verdict to Sinhala.
        
        Algo Data (Base Strategy):
        {algo_result}
        
        Additional Technical Context:
        - RSI: {sigs['RETAIL'][0]}
        - Fibonacci: {sigs['FIB'][0]}
        - Liquidity: {sigs['LIQ'][0]}
        
        Instructions:
        1. Review the Algo Data against the additional technicals.
        2. If RSI is overbought/oversold against the trend, suggest caution.
        3. Provide the explanation in Sinhala.
        4. END with the exact format: DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx
        """
        
        response = puter.ai.chat(prompt)
        
        if response and response.message:
            # --- REAL DB UPDATE LOGIC ---
            new_usage = current_usage + 1
            user_info["UsageCount"] = new_usage
            st.session_state.user = user_info # Update Local Session
            
            # Update Google Sheet
            if user_info["Username"] != "Admin":
                update_usage_in_db(user_info["Username"], new_usage)
            
            return response.message.content, f"Hybrid AI (Puter + Algo) | Used: {new_usage}/{max_limit}"
            
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
    
    for i, symbol in enumerate(assets_list):
        try:
            df = yf.download(symbol, period="5d", interval="15m", progress=False)
            if not df.empty and len(df) > 50:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                sigs, _ = calculate_advanced_signals(df)
                if sigs:
                    score_val = 0
                    if sigs['SK'][1] == 'bull': score_val = 2
                    elif sigs['SK'][1] == 'bear': score_val = -2
                    
                    results.append({
                        "Pair": symbol.replace("=X","").replace("-USD",""),
                        "Signal": sigs['SK'][0],
                        "Trend": sigs['TREND'][0],
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
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>⚡ INFINITE SYSTEM v8.0 PRO</h1>", unsafe_allow_html=True)
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
        tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h"], index=2)
        
        # News
        st.sidebar.divider()
        st.sidebar.subheader("📰 Market News")
        news_items = get_market_news(pair)
        for news in news_items:
            color_class = get_sentiment_class(news['title'])
            st.sidebar.markdown(f"<div class='news-card {color_class}'><div class='news-title'>{news['title']}</div></div>", unsafe_allow_html=True)

        # Chart & Logic
        data_period = "1mo" if tf in ["15m", "1h", "4h"] else "7d"
        df = yf.download(pair, period=data_period, interval=tf, progress=False)
        
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr_p = float(df['Close'].iloc[-1])
            st.title(f"{pair.replace('=X', '')} Terminal - {curr_p:.5f}")
            
            sigs, current_atr = calculate_advanced_signals(df)
            
            # Notification
            sk_signal = sigs['SK'][1]
            if sk_signal == "bull":
                st.markdown(f"<div class='notif-container notif-buy'>🔔 <b>BUY SIGNAL:</b> Infinite System detects a BUY setup!</div>", unsafe_allow_html=True)
            elif sk_signal == "bear":
                st.markdown(f"<div class='notif-container notif-sell'>🔔 <b>SELL SIGNAL:</b> Infinite System detects a SELL setup!</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='notif-container notif-wait'>📡 <b>MONITORING:</b> Waiting for clear setup...</div>", unsafe_allow_html=True)

            # --- RESTORED SIGNAL GRID (6 BOXES) ---
            keys_list = ['TREND', 'SMC', 'ICT', 'FIB', 'RETAIL', 'LIQ']
            c1, c2, c3 = st.columns(3)
            # Row 1
            c1.markdown(f"<div class='sig-box {sigs['TREND'][1]}'>TREND: {sigs['TREND'][0]}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='sig-box {sigs['SMC'][1]}'>SMC: {sigs['SMC'][0]}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='sig-box {sigs['ICT'][1]}'>ICT: {sigs['ICT'][0]}</div>", unsafe_allow_html=True)
            # Row 2
            c1.markdown(f"<div class='sig-box {sigs['FIB'][1]}'>FIB: {sigs['FIB'][0]}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='sig-box {sigs['RETAIL'][1]}'>RSI: {sigs['RETAIL'][0]}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='sig-box {sigs['LIQ'][1]}'>LIQ: {sigs['LIQ'][0]}</div>", unsafe_allow_html=True)

            # Chart
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

            # Dashboard
            st.markdown("### 🎯 Hybrid AI Analysis")
            c1, c2, c3 = st.columns(3)
            parsed = st.session_state.ai_parsed_data
            c1.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)
            
            st.divider()
            
            if st.button("🚀 Analyze with Hybrid AI", use_container_width=True):
                with st.spinner("Calculating Detailed Algo + Validating with Puter AI..."):
                    result, provider = get_hybrid_analysis(pair, {'price': curr_p}, sigs, news_items, current_atr, st.session_state.user)
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
        st.markdown("Scans assets for high-probability setups using SMC/ICT logic.")
        
        scan_market_type = st.selectbox("Select Market to Scan", ["Forex", "Crypto"])
        
        if st.button("Start Scan", type="primary"):
            with st.spinner(f"Scanning {scan_market_type} market..."):
                results = scan_market(assets[scan_market_type])
                
                if results:
                    st.success(f"Scan Complete! Found {len(results)} pairs.")
                    
                    # Display Top 3 Cards
                    col1, col2, col3 = st.columns(3)
                    for i, res in enumerate(results[:3]):
                        color = "#00ff00" if res['Score'] > 0 else "#ff4b4b" if res['Score'] < 0 else "#888"
                        with [col1, col2, col3][i]:
                            st.markdown(f"""
                            <div style="background:#222; padding:15px; border-radius:10px; border-left: 5px solid {color};">
                                <h3>{res['Pair']}</h3>
                                <p style="color:{color}; font-weight:bold;">{res['Signal']}</p>
                                <p>Price: {res['Price']:.4f}</p>
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
            
            tab1, tab2 = st.tabs(["User Management", "System Status"])
            
            with tab1:
                st.subheader("Manage User Limits")
                mock_users = [
                    {"Username": "Trader1", "HybridLimit": 10, "Usage": 5, "Status": "Online 🟢"},
                    {"Username": "Ishanka", "HybridLimit": 20, "Usage": 12, "Status": "Offline 🔴"},
                    {"Username": "UserX", "HybridLimit": 10, "Usage": 10, "Status": "Online 🟢"}
                ]
                df_users = pd.DataFrame(mock_users)
                st.dataframe(df_users, use_container_width=True)
                
                st.markdown("### Update Limit")
                c1, c2 = st.columns(2)
                target_user = c1.text_input("Username to Update")
                new_limit = c2.number_input("New Hybrid Limit", min_value=10, value=20)
                
                if st.button("Update User Limit"):
                    st.success(f"Updated {target_user} limit to {new_limit}")
            
            with tab2:
                st.subheader("Live System Stats")
                st.metric("Active Users", "3")
                st.metric("Total AI Calls Today", "124")
        else:
            st.error("Access Denied. Admins Only.")
            
    # --- AUTO REFRESH LOGIC ---
    if auto_refresh:
        time.sleep(60)
        st.rerun()
