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

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System v5.0 | Ultimate", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .price-up { color: #00ff00; font-size: 22px; font-weight: bold; }
    .price-down { color: #ff4b4b; font-size: 22px; font-weight: bold; }
    .entry-box { background: rgba(0, 212, 255, 0.05); border: 1px solid #00d4ff; padding: 15px; border-radius: 10px; margin-top: 10px; }
    .summary-card { background: #181a20; border-radius: 8px; padding: 10px; border: 1px solid #333; text-align: center; }
    .signal-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 10px; }
    .sig-box { padding: 8px; border-radius: 5px; font-size: 12px; text-align: center; font-weight: bold; border: 1px solid #444; }
    .bull { background-color: #004d40; color: #00ff00; border-color: #00ff00; }
    .bear { background-color: #4a1414; color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background-color: #262626; color: #888; }
    .stProgress > div > div > div > div { background-color: #00d4ff; }
</style>
""", unsafe_allow_html=True)

# --- 2. USER MANAGEMENT SYSTEM (ADMIN/USER) ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        return gspread.authorize(creds).open("Forex_User_DB").sheet1
    except: return None

def check_login(username, password):
    if username == "admin" and password == "admin123":
        return {"Username": "Admin", "Role": "Admin"}
        
    sheet = get_user_sheet()
    if sheet:
        try:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i["Username"]) == username), None)
            if user and str(user["Password"]) == password:
                return user
        except: return None
    return None

# --- 3. ADVANCED SIGNAL ENGINE ---
def calculate_advanced_signals(df):
    signals = {}
    c = df['Close'].iloc[-1]
    h = df['High'].iloc[-1]
    l = df['Low'].iloc[-1]
    
    # 1. SMC (Market Structure)
    highs = df['High'].rolling(10).max()
    lows = df['Low'].rolling(10).min()
    if c > highs.iloc[-2]: signals['SMC'] = ("Bullish BOS", "bull")
    elif c < lows.iloc[-2]: signals['SMC'] = ("Bearish BOS", "bear")
    else: signals['SMC'] = ("Internal Struct", "neutral")

    # 2. ICT (FVG)
    if df['Low'].iloc[-1] > df['High'].iloc[-3]: signals['ICT'] = ("Bullish FVG", "bull")
    elif df['High'].iloc[-1] < df['Low'].iloc[-3]: signals['ICT'] = ("Bearish FVG", "bear")
    else: signals['ICT'] = ("No FVG", "neutral")

    # 3. Fibonacci
    period_high = df['High'].rolling(50).max().iloc[-1]
    period_low = df['Low'].rolling(50).min().iloc[-1]
    fib_618 = period_high - ((period_high - period_low) * 0.618)
    if abs(c - fib_618) < (c * 0.0005): signals['FIB'] = ("Golden Zone", "bull")
    else: signals['FIB'] = ("Ranging", "neutral")

    # 4. RSI (Retail)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs)).iloc[-1]
    
    if rsi > 70: signals['RETAIL'] = ("Overbought (Sell)", "bear")
    elif rsi < 30: signals['RETAIL'] = ("Oversold (Buy)", "bull")
    else: signals['RETAIL'] = (f"Neutral ({int(rsi)})", "neutral")

    # 5. Liquidity
    if l < df['Low'].iloc[-10:-1].min(): signals['LIQ'] = ("Liquidity Grab (L)", "bull")
    elif h > df['High'].iloc[-10:-1].max(): signals['LIQ'] = ("Liquidity Grab (H)", "bear")
    else: signals['LIQ'] = ("Holding", "neutral")

    # 6. Trendline
    ema_50 = df['Close'].rolling(50).mean().iloc[-1]
    if c > ema_50: signals['TREND'] = ("Uptrend", "bull")
    else: signals['TREND'] = ("Downtrend", "bear")

    # 7. SK Strategy
    score = 0
    if signals['SMC'][1] == "bull": score += 1
    if signals['TREND'][1] == "bull": score += 1
    if rsi < 40: score += 1
    if score >= 2: signals['SK'] = ("SK Buy Setup", "bull")
    elif score <= -2: signals['SK'] = ("SK Sell Setup", "bear")
    else: signals['SK'] = ("Waiting...", "neutral")

    # 8. Patterns
    if df['Close'].iloc[-1] > df['Open'].iloc[-1] and df['Close'].iloc[-2] < df['Open'].iloc[-2] and df['Close'].iloc[-1] > df['Open'].iloc[-2]:
        signals['PATT'] = ("Engulfing", "bull")
    else:
        signals['PATT'] = ("None", "neutral")

    return signals

# --- 4. AI ENGINE ---
def get_ai_analysis(prompt, asset_data):
    if "GEMINI_KEYS" in st.secrets:
        keys = st.secrets["GEMINI_KEYS"]
        for key in keys:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel('gemini-3-flash-preview')
                response = model.generate_content(prompt)
                return response.text
            except: continue
    
    sl = asset_data['price'] * 0.995
    tp = asset_data['price'] * 1.01
    return f"ENTRY: {asset_data['price']}\nSL: {sl}\nTP: {tp}\n\n⚠️ AI Offline. Manual Calculation."

# --- 5. MAIN APPLICATION ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>🔐 INFINITE SYSTEM LOGIN</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            submit = st.form_submit_button("Access Terminal")
            if submit:
                user = check_login(u, p)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Invalid Credentials")
else:
    # --- FIXED SIDEBAR LOGIC ---
    user_info = st.session_state.get('user', {})
    username = user_info.get('Username', 'Trader')
    st.sidebar.title(f"👤 {username}")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()
    
    market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
    assets = {
        "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD"],
        "Metals": ["XAUUSD=X", "XAGUSD=X"]
    }
    pair = st.sidebar.selectbox("Select Asset", assets[market])
    tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h", "1d"], index=2)
    live = st.sidebar.checkbox("🔴 Live Data Refresh", value=True)

    # DATA PROCESSING
    df = yf.download(pair, period="5d", interval=tf, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        curr_p = float(df['Close'].iloc[-1])
        
        # HEADER
        c1, c2 = st.columns([3, 1])
        with c1:
            st.title(f"{pair}")
            st.caption(f"Timeframe: {tf} | Strategy: Infinite AI Hybrid")
        with c2:
            st.markdown(f"<div style='text-align:right; font-size:30px;' class='price-up'>{curr_p:.4f}</div>", unsafe_allow_html=True)

        # SIGNALS
        sigs = calculate_advanced_signals(df)
        st.markdown("### 📡 Market Scanner")
        r1 = st.columns(4)
        r2 = st.columns(4)
        
        keys = list(sigs.keys())
        for i in range(4):
            r1[i].markdown(f"<div class='sig-box {sigs[keys[i]][1]}'>{keys[i]}: {sigs[keys[i]][0]}</div>", unsafe_allow_html=True)
            r2[i].markdown(f"<div class='sig-box {sigs[keys[i+4]][1]}'>{keys[i+4]}: {sigs[keys[i+4]][0]}</div>", unsafe_allow_html=True)

        # CHART
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=10,b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # AI LOGIC
        st.divider()
        c_ai, c_res = st.columns([1, 2])
        with c_ai:
            st.subheader("🧠 AI Sniper")
            if st.button("🚀 Analyze & Find Entry", use_container_width=True):
                with st.spinner("Scanning..."):
                    prompt = f"Analyze {pair} at {curr_p}. SMC: {sigs['SMC'][0]}, ICT: {sigs['ICT'][0]}, RSI: {sigs['RETAIL'][0]}. ENTRY: [val], SL: [val], TP: [val]. Reason in Sinhala."
                    st.session_state.ai_result = get_ai_analysis(prompt, {'price': curr_p})
            
        with c_res:
            if "ai_result" in st.session_state:
                res = st.session_state.ai_result
                entry_match = re.search(r"ENTRY[:\s]+([\d.]+)", res, re.IGNORECASE)
                entry_price = float(entry_match.group(1)) if entry_match else curr_p
                
                diff = abs(curr_p - entry_price)
                prog = max(0.0, min(1.0, 1.0 - (diff / (curr_p * 0.005))))
                
                st.write(f"**Zone Accuracy:** {int(prog*100)}%")
                st.progress(prog)
                st.markdown(f"<div class='entry-box'>{res}</div>", unsafe_allow_html=True)

    if live:
        time.sleep(60)
        st.rerun()
