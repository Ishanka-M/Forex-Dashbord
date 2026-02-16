import streamlit as st
import yfinance as yf
import pandas as pd
import puter  # Gemini/HF වෙනුවට Puter භාවිතා කරයි
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import re
import numpy as np
import xml.etree.ElementTree as ET
import requests

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System v8.0 | Hybrid Pro", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .theory-box { background: rgba(255, 255, 255, 0.05); border-radius: 10px; padding: 15px; border-left: 5px solid #00d4ff; margin-bottom: 20px; }
    .theory-title { color: #00d4ff; font-weight: bold; font-size: 16px; margin-bottom: 5px; }
    .theory-text { color: #ccc; font-size: 13px; line-height: 1.4; }
    .sig-box { padding: 10px; border-radius: 6px; font-size: 12px; text-align: center; font-weight: bold; border: 1px solid #444; margin-bottom: 5px; }
    .bull { background-color: #004d40; color: #00ff00; border-color: #00ff00; }
    .bear { background-color: #4a1414; color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background-color: #262626; color: #888; }
    .entry-box { background: rgba(0, 212, 255, 0.07); border: 2px solid #00d4ff; padding: 15px; border-radius: 12px; margin-top: 10px; color: white; white-space: pre-wrap; }
    .trade-metric { background: #222; border: 1px solid #444; border-radius: 8px; padding: 10px; text-align: center; }
    .notif-container { padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 10px solid; background: #121212; }
    .notif-buy { border-color: #00ff00; color: #00ff00; box-shadow: 0 0 15px rgba(0, 255, 0, 0.2); }
    .notif-sell { border-color: #ff4b4b; color: #ff4b4b; box-shadow: 0 0 15px rgba(255, 75, 75, 0.2); }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# --- 2. DB & AUTH HELPER FUNCTIONS ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("Forex_User_DB").sheet1
        try: chat_sheet = client.open("Forex_User_DB").worksheet("Chat")
        except: chat_sheet = None
        return sheet, chat_sheet
    except: return None, None

def update_db_usage(username, new_count):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell: sheet.update_cell(cell.row, 4, new_count)
        except: pass

def check_login(username, password):
    if username == "admin" and password == "admin123":
        return {"Username": "Admin", "Role": "Admin", "HybridLimit": 999, "UsageCount": 0}
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i.get("Username")) == username), None)
            if user and str(user.get("Password")) == password: return user
        except: return None
    return None

# --- 3. ADVANCED SIGNAL ENGINE (Integrated v7 Theories) ---
def calculate_advanced_signals(df):
    if len(df) < 50: return None, 0
    signals = {}
    c, h, l = df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    
    # SMC & ICT
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    signals['ICT'] = ("Bullish FVG", "bull") if df['Low'].iloc[-1] > df['High'].iloc[-3] else (("Bearish FVG", "bear") if df['High'].iloc[-1] < df['Low'].iloc[-3] else ("No FVG", "neutral"))
    
    # Fibonacci Golden Zone (61.8%)
    ph, pl = df['High'].rolling(50).max().iloc[-1], df['Low'].rolling(50).min().iloc[-1]
    fib_618 = ph - ((ph - pl) * 0.618)
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.0005) else ("Ranging", "neutral")
    
    # Liquidity Grabs
    prev_low = df['Low'].iloc[-10:-1].min()
    prev_high = df['High'].iloc[-10:-1].max()
    signals['LIQ'] = ("Liquidity Grab (L)", "bull") if l < prev_low else (("Liquidity Grab (H)", "bear") if h > prev_high else ("Holding", "neutral"))
    
    # Trend & RSI
    signals['TREND'] = ("Uptrend", "bull") if c > df['Close'].rolling(50).mean().iloc[-1] else ("Downtrend", "bear")
    
    # Elliott Wave Analysis
    last_50 = df['Close'].tail(50)
    pos = (c - last_50.min()) / (last_50.max() - last_50.min()) if (last_50.max() - last_50.min()) != 0 else 0.5
    if signals['TREND'][1] == "bull":
        ew = ("Wave 5 (Exhaustion)", "bear") if pos > 0.8 else (("Wave 3 (Impulse)", "bull") if 0.4 < pos <= 0.8 else ("Wave 1", "bull"))
    else:
        ew = ("Wave C (Final Drop)", "bull") if pos < 0.2 else (("Wave A (Correction)", "bear") if pos < 0.6 else ("Wave B", "neutral"))
    signals['ELLIOTT'] = ew

    # SK Sniper Scoring
    score = (1 if signals['SMC'][1] == "bull" else -1) + (1 if signals['TREND'][1] == "bull" else -1) + (1 if signals['ICT'][1] == "bull" else -1)
    signals['SK'] = ("SK Sniper Buy", "bull") if score >= 2 else (("SK Sniper Sell", "bear") if score <= -2 else ("Waiting", "neutral"))
    
    # ATR for SL/TP
    tr = pd.concat([df['High']-df['Low'], abs(df['High']-df['Close'].shift()), abs(df['Low']-df['Close'].shift())], axis=1).max(axis=1)
    return signals, tr.rolling(14).mean().iloc[-1]

# --- 4. ALGO ENGINE (Sinhala Report Generation) ---
def infinite_algorithmic_engine(pair, curr_p, sigs, atr):
    trend, smc, ew, sk_signal = sigs['TREND'][0], sigs['SMC'][0], sigs['ELLIOTT'][0], sigs['SK'][1]
    
    if sk_signal == "bull":
        status = "ශක්තිමත් මිලදී ගැනීමේ අවස්ථාවකි (Strong Buy)."
        sl, tp = curr_p - (atr * 1.5), curr_p + (atr * 3)
    elif sk_signal == "bear":
        status = "ශක්තිමත් විකිණීමේ අවස්ථාවකි (Strong Sell)."
        sl, tp = curr_p + (atr * 1.5), curr_p - (atr * 3)
    else:
        status = "ප්‍රවේශම් වන්න (Neutral/Wait)."
        sl, tp = curr_p - atr, curr_p + atr

    return f"""
♾️ **INFINITE ALGO ENGINE V2.0**
වෙළඳ යුගලය: {pair.replace('=X', '')}
ප්‍රවණතාව: {trend} | ව්‍යුහය (SMC): {smc}
තරංග විශ්ලේෂණය: {ew}

💡 **නිගමනය:** {status}

DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}
"""

# --- 5. HYBRID AI INTERFACE ---
def get_hybrid_analysis(pair, curr_p, sigs, atr, user_info):
    algo_report = infinite_algorithmic_engine(pair, curr_p, sigs, atr)
    
    limit = int(user_info.get("HybridLimit", 10))
    usage = int(user_info.get("UsageCount", 0))
    
    if usage >= limit and user_info.get("Role") != "Admin":
        return algo_report, f"Pure Algo (Limit Reached)"

    try:
        prompt = f"Role: Senior Forex Expert. Validate this trade plan and explain IN DETAIL strictly in SINHALA. Ensure you mention SMC and Elliott Wave status. Then end with the data format.\n\nPlan:\n{algo_report}"
        response = puter.ai.chat(prompt)
        if response and response.message:
            # Update Usage
            new_usage = usage + 1
            update_db_usage(user_info['Username'], new_usage)
            st.session_state.user['UsageCount'] = new_usage
            return response.message.content, f"Hybrid AI | {new_usage}/{limit}"
    except: pass
    return algo_report, "Algo Fallback"

# --- 6. MAIN APPLICATION UI ---
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
    st.sidebar.metric("Hybrid Credits", f"{max(0, int(user_info.get('HybridLimit',0)) - int(user_info.get('UsageCount',0)))}")
    
    app_mode = st.sidebar.radio("Navigation", ["Terminal", "Market Scanner", "Trader Chat"])
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # --- TERMINAL VIEW ---
    if app_mode == "Terminal":
        st.markdown(f"""
        <div class="theory-box">
            <div class="theory-title">⚙️ Infinite Core Algorithm (v8.0 Pro Hybrid)</div>
            <div class="theory-text">
                <b>SMC & ICT:</b> Market Structure (BOS) සහ FVG මගින් ආයතනික චලනයන් හඳුනා ගනී.<br>
                <b>Elliott Wave:</b> වෙළඳපල දැනට පවතින තරංගය (Wave 1-5 / A-C) හරහා Exhaustion මට්ටම් පරීක්ෂා කරයි.<br>
                <b>Fibonacci:</b> 61.8% Golden Zone හරහා ප්‍රත්‍යාවර්තන (Reversals) සහතික කරයි.
            </div>
        </div>
        """, unsafe_allow_html=True)

        market = st.sidebar.selectbox("Market", ["Forex", "Crypto", "Metals"])
        assets = {"Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X"], "Crypto": ["BTC-USD", "ETH-USD"], "Metals": ["XAUUSD=X"]}
        pair = st.sidebar.selectbox("Pair", assets[market])
        tf = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h"])

        df = yf.download(pair, period="1mo", interval=tf, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr_p = float(df['Close'].iloc[-1])
            sigs, current_atr = calculate_advanced_signals(df)
            
            # Notifications
            if sigs['SK'][1] == "bull": st.markdown("<div class='notif-container notif-buy'>🔔 <b>BUY ALERT:</b> High probability setup!</div>", unsafe_allow_html=True)
            elif sigs['SK'][1] == "bear": st.markdown("<div class='notif-container notif-sell'>🔔 <b>SELL ALERT:</b> High probability setup!</div>", unsafe_allow_html=True)

            # Signal Dashboard
            cols = st.columns(4)
            theory_keys = ['SMC', 'ICT', 'FIB', 'LIQ', 'ELLIOTT', 'RETAIL', 'TREND', 'SK']
            for i, k in enumerate(theory_keys):
                cols[i % 4].markdown(f"<div class='sig-box {sigs[k][1]}'>{k}: {sigs[k][0]}</div>", unsafe_allow_html=True)

            # Chart
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=380, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

            # Trade Plan Metrics
            st.markdown("### 🎯 Hybrid Trade Plan")
            t_c1, t_c2, t_c3 = st.columns(3)
            parsed = st.session_state.ai_parsed_data
            t_c1.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
            t_c2.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
            t_c3.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)

            if st.button("🚀 Run Hybrid AI Analysis", use_container_width=True):
                with st.spinner("Processing All Theories..."):
                    result, prov = get_hybrid_analysis(pair, curr_p, sigs, current_atr, st.session_state.user)
                    st.session_state.ai_result = result
                    # Regex parse DATA: ENTRY=... SL=... TP=...
                    matches = re.search(r"ENTRY=([\d\.]+)\s*\|\s*SL=([\d\.]+)\s*\|\s*TP=([\d\.]+)", result)
                    if matches:
                        st.session_state.ai_parsed_data = {"ENTRY": matches.group(1), "SL": matches.group(2), "TP": matches.group(3)}
                    st.session_state.active_provider = prov
                    st.rerun()

            if "ai_result" in st.session_state:
                st.markdown(f"**Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    # --- MARKET SCANNER VIEW ---
    elif app_mode == "Market Scanner":
        st.title("📡 AI Market Scanner")
        if st.button("Start Global Scan"):
            scan_list = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "XAUUSD=X", "BTC-USD", "ETH-USD"]
            for s in scan_list:
                df_s = yf.download(s, period="5d", interval="15m", progress=False)
                if not df_s.empty:
                    if isinstance(df_s.columns, pd.MultiIndex): df_s.columns = df_s.columns.get_level_values(0)
                    s_sigs, _ = calculate_advanced_signals(df_s)
                    color = "#00ff00" if s_sigs['SK'][1] == "bull" else "#ff4b4b" if s_sigs['SK'][1] == "bear" else "#888"
                    st.markdown(f"""
                    <div style="background:#222; padding:10px; border-radius:5px; border-left: 5px solid {color}; margin-bottom:5px;">
                        <b>{s.replace('=X','')}</b>: {s_sigs['SK'][0]} | Trend: {s_sigs['TREND'][0]}
                    </div>
                    """, unsafe_allow_html=True)

    # --- TRADER CHAT VIEW ---
    elif app_mode == "Trader Chat":
        st.title("💬 Global Trader Room")
        st.info("Chat is currently in Session Mode. Connect GSheet to persist data.")
        for msg in st.session_state.chat_history:
            st.markdown(f"**{msg['user']}**: {msg['text']}")
        
        with st.form("chat"):
            m = st.text_input("Message")
            if st.form_submit_button("Send"):
                st.session_state.chat_history.append({"user": user_info['Username'], "text": m})
                st.rerun()
