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
    .sig-box { padding: 10px; border-radius: 6px; font-size: 13px; text-align: center; font-weight: bold; border: 1px solid #444; margin-bottom: 5px; }
    .bull { background-color: #004d40; color: #00ff00; border-color: #00ff00; }
    .bear { background-color: #4a1414; color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background-color: #262626; color: #888; }

    /* Notification Styling */
    .notif-container {
        padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 10px solid; background: #121212;
    }
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

def update_db_usage(username, new_count):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell:
                sheet.update_cell(cell.row, 4, new_count)
        except: pass

def save_chat_to_db(user, msg, time_str):
    _, chat_sheet = get_user_sheet()
    if chat_sheet:
        try:
            chat_sheet.append_row([user, msg, time_str])
        except: pass

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

# --- 4. ADVANCED SIGNAL ENGINE (CORE) ---
def calculate_advanced_signals(df):
    if len(df) < 50: return None, 0
    signals = {}
    c, h, l = df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    
    # 1. SMC & ICT
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    signals['ICT'] = ("Bullish FVG", "bull") if df['Low'].iloc[-1] > df['High'].iloc[-3] else (("Bearish FVG", "bear") if df['High'].iloc[-1] < df['Low'].iloc[-3] else ("No FVG", "neutral"))
    
    # 2. Fibonacci (Golden Zone)
    ph, pl = df['High'].rolling(50).max().iloc[-1], df['Low'].rolling(50).min().iloc[-1]
    fib_618 = ph - ((ph - pl) * 0.618)
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.0005) else ("Ranging", "neutral")
    
    # 3. Liquidity
    prev_low = df['Low'].iloc[-10:-1].min()
    prev_high = df['High'].iloc[-10:-1].max()
    signals['LIQ'] = ("Liq Grab (L)", "bull") if l < prev_low else (("Liq Grab (H)", "bear") if h > prev_high else ("Stable", "neutral"))
    
    # 4. Trend & Elliott Wave
    signals['TREND'] = ("Uptrend", "bull") if c > df['Close'].rolling(50).mean().iloc[-1] else ("Downtrend", "bear")
    
    last_50 = df['Close'].tail(50)
    pos = (c - last_50.min()) / (last_50.max() - last_50.min()) if (last_50.max() - last_50.min()) != 0 else 0.5
    if signals['TREND'][1] == "bull":
        signals['ELLIOTT'] = ("Wave 3 (Imp)", "bull") if 0.4 < pos <= 0.8 else ("Correction", "neutral")
    else:
        signals['ELLIOTT'] = ("Wave C (Drop)", "bear") if pos < 0.2 else ("Correction", "neutral")

    # 5. Retail Sentiment (RSI based)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain/loss))).iloc[-1]
    signals['RETAIL'] = ("Oversold", "bull") if rsi < 30 else (("Overbought", "bear") if rsi > 70 else ("Neutral", "neutral"))

    # 6. SK Sniper Scoring
    score = (1 if signals['SMC'][1] == "bull" else -1) + (1 if signals['TREND'][1] == "bull" else -1) + (1 if signals['ICT'][1] == "bull" else -1)
    signals['SK'] = ("SK Sniper Buy", "bull") if score >= 2 else (("SK Sniper Sell", "bear") if score <= -2 else ("Waiting", "neutral"))
    
    # ATR
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
    return signals, tr.rolling(14).mean().iloc[-1]

# --- 5. INFINITE ALGORITHMIC ENGINE ---
def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr):
    trend = sigs['TREND'][0]
    sk_signal = sigs['SK'][1]
    
    news_score = 0
    for item in news_items:
        s = get_sentiment_class(item['title'])
        if s == "news-positive": news_score += 1
        elif s == "news-negative": news_score -= 1

    if sk_signal == "bull":
        action = "BUY"
        sl, tp = curr_p - (atr * 1.5), curr_p + (atr * 3)
        note = "Technical indicators suggest a strong UPWARD movement."
    elif sk_signal == "bear":
        action = "SELL"
        sl, tp = curr_p + (atr * 1.5), curr_p - (atr * 3)
        note = "Technical indicators suggest a strong DOWNWARD movement."
    else:
        action = "WAIT"
        sl, tp = curr_p - atr, curr_p + atr
        note = "Market is ranging. Wait for a clear breakout."

    analysis_text = f"""
    ♾️ **INFINITE ALGO ENGINE (PURE MODE)**
    Pair: {pair} | Action: {action}
    Trend: {trend} | SMC: {sigs['SMC'][0]}
    
    Sig Score: {sk_signal.upper()}
    News Bias: {"Bullish" if news_score > 0 else "Bearish" if news_score < 0 else "Neutral"}
    
    {note}
    
    DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}
    """
    return analysis_text

# --- 6. HYBRID AI ENGINE ---
def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info):
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr)
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 10)
    
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        st.toast(f"Limit Reached. Switching to Pure Mode.", icon="⚠️")
        return algo_result, "Infinite Algo (Pure Mode)"

    try:
        st.toast("Validating with Puter AI...", icon="🧠")
        prompt = f"Role: Senior Forex Risk Manager. Task: Validate this trade: {algo_result}. Context: News: {[n['title'] for n in news_items[:2]]}. Write the brief explanation strictly in Sinhala. END with: DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx"
        response = puter.ai.chat(prompt)
        
        if response and response.message:
            user_info["UsageCount"] += 1
            if user_info["Role"] != "Admin": update_db_usage(user_info["Username"], user_info["UsageCount"])
            st.session_state.user = user_info 
            return response.message.content, f"Hybrid AI | Credits: {user_info['UsageCount']}/{max_limit}"
    except: pass
    return algo_result, "Infinite Algo (Fallback)"

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
    for i, symbol in enumerate(assets_list):
        try:
            df = yf.download(symbol, period="5d", interval="15m", progress=False)
            if not df.empty and len(df) > 40:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                sigs, _ = calculate_advanced_signals(df)
                if sigs:
                    score_val = 2 if sigs['SK'][1] == 'bull' else (-2 if sigs['SK'][1] == 'bear' else 0)
                    results.append({"Pair": symbol.replace("=X",""), "Signal": sigs['SK'][0], "Trend": sigs['TREND'][0], "Score": score_val, "Price": df['Close'].iloc[-1]})
        except: pass
        progress_bar.progress((i + 1) / len(assets_list))
    progress_bar.empty()
    return sorted(results, key=lambda x: abs(x['Score']), reverse=True)

# --- 7. MAIN APPLICATION ---
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
    user_info = st.session_state.get('user', {})
    remaining = max(0, user_info.get('HybridLimit', 10) - user_info.get('UsageCount', 0))
    
    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    st.sidebar.metric("Hybrid Credits", f"{remaining}")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    app_mode = st.sidebar.radio("Navigation", ["Terminal", "Market Scanner", "Trader Chat", "Admin Panel"])
    assets = {
        "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCHF=X", "USDCAD=X", "NZDUSD=X"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"],
        "Metals": ["XAUUSD=X", "XAGUSD=X"] 
    }

    if app_mode == "Terminal":
        st.sidebar.divider()
        market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
        pair = st.sidebar.selectbox("Select Asset", assets[market], format_func=lambda x: x.replace("=X", ""))
        tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h"], index=2)
        
        news_items = get_market_news(pair)
        for news in news_items:
            st.sidebar.markdown(f"<div class='news-card {get_sentiment_class(news['title'])}'><div class='news-title'>{news['title']}</div></div>", unsafe_allow_html=True)

        df = yf.download(pair, period="1mo" if tf in ["15m", "1h", "4h"] else "7d", interval=tf, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr_p = float(df['Close'].iloc[-1])
            st.title(f"{pair.replace('=X', '')} - {curr_p:.5f}")
            
            sigs, current_atr = calculate_advanced_signals(df)
            
            # Notif
            sk_signal = sigs['SK'][1]
            if sk_signal != "neutral":
                color = "buy" if sk_signal == "bull" else "sell"
                st.markdown(f"<div class='notif-container notif-{color}'>🔔 <b>{sk_signal.upper()} SIGNAL DETECTED!</b></div>", unsafe_allow_html=True)

            # Chart
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

            # --- Technical Signals Row ---
            st.markdown("### ⚡ Technical Theory Signals")
            sig_cols = st.columns(4)
            theory_keys = ['SMC', 'ICT', 'FIB', 'LIQ', 'TREND', 'ELLIOTT', 'RETAIL', 'SK']
            for i, k in enumerate(theory_keys):
                if k in sigs:
                    sig_cols[i % 4].markdown(f"<div class='sig-box {sigs[k][1]}'>{k}: {sigs[k][0]}</div>", unsafe_allow_html=True)

            # Dashboard Metrics
            st.markdown("### 🎯 Hybrid AI Analysis")
            c1, c2, c3 = st.columns(3)
            parsed = st.session_state.ai_parsed_data
            c1.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)
            
            if st.button("🚀 Analyze with Hybrid AI", use_container_width=True):
                with st.spinner("Calculating..."):
                    result, provider = get_hybrid_analysis(pair, {'price': curr_p}, sigs, news_items, current_atr, st.session_state.user)
                    st.session_state.ai_parsed_data = parse_ai_response(result)
                    st.session_state.ai_result = result.split("DATA:")[0] if "DATA:" in result else result
                    st.session_state.active_provider = provider
                    st.rerun()

            if "ai_result" in st.session_state:
                st.markdown(f"**Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    elif app_mode == "Market Scanner":
        st.title("📡 AI Market Scanner")
        scan_type = st.selectbox("Market", ["Forex", "Crypto"])
        if st.button("Start Scan", type="primary"):
            results = scan_market(assets[scan_type])
            st.dataframe(pd.DataFrame(results))

    elif app_mode == "Trader Chat":
        st.title("💬 Global Trader Room")
        for msg in st.session_state.chat_history:
            st.markdown(f"<div class='chat-msg'><span class='chat-user'>{msg['user']}</span>: {msg['text']}</div>", unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            user_msg = st.text_input("Message")
            if st.form_submit_button("Send") and user_msg:
                new_m = {"user": user_info['Username'], "text": user_msg, "time": datetime.now().strftime("%H:%M")}
                st.session_state.chat_history.append(new_m)
                save_chat_to_db(user_info['Username'], user_msg, new_m['time'])
                st.rerun()

    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Panel")
            target = st.text_input("Username")
            new_lim = st.number_input("Limit", min_value=10, value=50)
            if st.button("Update"):
                sheet, _ = get_user_sheet()
                try:
                    cell = sheet.find(target)
                    sheet.update_cell(cell.row, 3, new_lim)
                    st.success("Done")
                except: st.error("Not found")
        else: st.error("Admin Only")
