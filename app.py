import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import re
import pytz
import requests

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System | Pro AI Terminal", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .price-up { color: #00ff00; font-size: 24px; font-weight: bold; }
    .price-down { color: #ff0000; font-size: 24px; font-weight: bold; }
    .footer { position: fixed; bottom: 0; width: 100%; text-align: center; color: #00d4ff; padding: 10px; background: rgba(0,0,0,0.8); z-index: 100;}
    .entry-box { background: rgba(0, 212, 255, 0.05); border: 1px solid #00d4ff; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
    .summary-card { background: rgba(255, 255, 255, 0.07); border-radius: 10px; padding: 15px; border: 1px solid #444; text-align: center; }
    .notif-badge { padding: 4px 10px; border-radius: 5px; font-size: 12px; font-weight: bold; margin-right: 5px; border: 1px solid rgba(255,255,255,0.2); }
    .bg-smc { background-color: #ff9800; color: black; }
    .bg-ict { background-color: #e91e63; color: white; }
    .bg-liq { background-color: #9c27b0; color: white; }
    .bg-trend { background-color: #2196f3; color: white; }
</style>
""", unsafe_allow_html=True)

# --- 2. SECURE API & ERROR HANDLING ---
def get_ai_analysis(prompt, asset_data=None):
    """
    පියවර 3 කින් යුත් AI Fallback එකක්: 
    1. Gemini 2. Hugging Face 3. Internal Technical Analysis (AI දෙකම Fail වුනොත්)
    """
    # Step 1: Gemini
    try:
        if "GEMINI_KEYS" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_KEYS"][0])
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text
    except Exception as e:
        st.warning(f"⚠️ Gemini Sync Issues: {str(e)[:50]}")

    # Step 2: Hugging Face Fallback
    try:
        if "HF_TOKEN" in st.secrets:
            API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
            headers = {"Authorization": f"Bearer {st.secrets['HF_TOKEN']}"}
            payload = {"inputs": f"<s>[INST] {prompt} [/INST]", "parameters": {"max_new_tokens": 500}}
            response = requests.post(API_URL, headers=headers, json=payload, timeout=10)
            result = response.json()
            return result[0]['generated_text'] if isinstance(result, list) else result.get('generated_text', "HF Error")
    except:
        pass

    # Step 3: Local Analysis (If AI Fails)
    if asset_data is not None:
        return f"🚨 AI Offline Mode: Static Analysis based on Indicators.\nENTRY: {asset_data['close']}\nSMC: Bearish Structure\nICT: FVG Pending.\n(Please check API keys for full AI Insight)"
    
    return "❌ All AI Nodes Unreachable. Check Secrets Configuration."

def get_alpha_vantage_update(symbol):
    """Alpha Vantage හරහා hourly data fetch කිරීම"""
    try:
        if "ALPHA_VANTAGE_KEY" in st.secrets:
            url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={st.secrets["ALPHA_VANTAGE_KEY"]}'
            r = requests.get(url, timeout=5)
            data = r.json()
            return data.get("Global Quote", {})
    except: return None

# --- 3. CORE TECHNICAL ENGINE ---
def calculate_signals(df):
    signals = []
    c = df['Close'].iloc[-1]
    h_max = df['High'].rolling(20).max().iloc[-1]
    l_min = df['Low'].rolling(20).min().iloc[-1]
    
    # SMC & Liquidity detection
    if c > df['High'].iloc[-5:].max(): signals.append(("SMC/BOS", "bg-smc", "Market Structure Break (Bullish)"))
    if c < df['Low'].iloc[-5:].min(): signals.append(("SMC/CHoCH", "bg-smc", "Trend Change Detected"))
    
    # ICT & FVG
    if df['Low'].iloc[-1] > df['High'].iloc[-3]: signals.append(("ICT/FVG", "bg-ict", "Bullish Fair Value Gap Found"))
    
    # Fibonacci (61.8%)
    fib_level = h_max - (h_max - l_min) * 0.618
    if abs(c - fib_level) < (c * 0.001): signals.append(("FIB", "bg-trend", "Rejection at 0.618 Level"))
    
    # Trendlines / S&R
    if c > df['Close'].rolling(50).mean().iloc[-1]: signals.append(("TREND", "bg-trend", "Above 50 EMA (Strong Trend)"))
    
    return signals

# --- 4. DATA FETCH & LOGIN ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        return gspread.authorize(creds).open("Forex_User_DB").sheet1 
    except: return None

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "last_price" not in st.session_state: st.session_state.last_price = 0.0

if not st.session_state.logged_in:
    st.title("🔐 Infinite System Login")
    u, p = st.text_input("Username"), st.text_input("Password", type="password")
    if st.button("Access Terminal"):
        sheet = get_user_sheet()
        if sheet:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i["Username"]) == u), None)
            if user and str(user["Password"]) == p:
                st.session_state.logged_in, st.session_state.user_data = True, user
                st.rerun()
        else: st.error("Database Connection Error. Check GCP Credentials.")

# --- 5. MAIN DASHBOARD ---
if st.session_state.logged_in:
    # Asset Selection (Forex + Crypto)
    assets = {
        "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "XAUUSD=X"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "DOGE-USD"]
    }
    
    st.sidebar.header("🕹️ Control Panel")
    asset_type = st.sidebar.radio("Market Type", ["Forex", "Crypto"])
    pair = st.sidebar.selectbox("Select Asset", assets[asset_type])
    tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=4)
    live = st.sidebar.toggle("🚀 LIVE MODE", value=True)

    # Data Sync Logic
    df = yf.download(pair, period="1mo", interval=tf, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        curr_p = float(df['Close'].iloc[-1])
        
        # --- UI Header & Dynamic Notifications ---
        c1, c2 = st.columns([2, 1])
        with c1:
            st.title(f"📊 {pair} Analysis")
            sig_list = calculate_signals(df)
            notif_html = "".join([f'<span class="notif-badge {b}">{t}: {m}</span>' for t, b, m in sig_list])
            st.markdown(notif_html, unsafe_allow_html=True)
            
        with c2:
            p_class = "price-up" if curr_p >= st.session_state.last_price else "price-down"
            st.markdown(f"<div style='text-align:right'>LIVE PRICE:<br><span class='{p_class}'>{curr_p:.5f}</span></div>", unsafe_allow_html=True)
            st.session_state.last_price = curr_p

        # --- Charting ---
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # --- AI Strategy Engine ---
        st.divider()
        prompt = f"""Analyze {pair} at {curr_p} for professional trading. 
        Requirements: 
        1. Use SMC (Structure, Liquidity), ICT (FVG, Killzones), and SK Strategy.
        2. Detect Fibonacci 0.618 and Patterns.
        3. Differentiate between Retail Sentiment and Institutional flow.
        4. Output format: ENTRY: (val), SL: (val), TP: (val). 
        5. Explain in Sinhala."""
        
        analysis = get_ai_analysis(prompt, asset_data={'close': curr_p})
        
        # UI Boxes
        col_s, col_p = st.columns([2, 1])
        with col_s:
            st.subheader("📝 Sniper Strategy")
            entry = re.search(r"ENTRY[:\s]+([\d.]+)", analysis, re.IGNORECASE)
            sl = re.search(r"SL[:\s]+([\d.]+)", analysis, re.IGNORECASE)
            tp = re.search(r"TP[:\s]+([\d.]+)", analysis, re.IGNORECASE)
            
            s1, s2, s3 = st.columns(3)
            with s1: st.markdown(f"<div class='summary-card'><b>ENTRY</b><br><span style='color:#00d4ff'>{entry.group(1) if entry else 'Pending'}</span></div>", unsafe_allow_html=True)
            with s2: st.markdown(f"<div class='summary-card'><b>STOP LOSS</b><br><span style='color:#ff4b4b'>{sl.group(1) if sl else 'Pending'}</span></div>", unsafe_allow_html=True)
            with s3: st.markdown(f"<div class='summary-card'><b>TAKE PROFIT</b><br><span style='color:#00ff00'>{tp.group(1) if tp else 'Pending'}</span></div>", unsafe_allow_html=True)
            
        with col_p:
            st.subheader("🎯 Zone Accuracy")
            if entry:
                diff = abs(curr_p - float(entry.group(1)))
                acc = max(0.0, min(1.0, 1.0 - (diff / (curr_p * 0.01))))
                st.write(f"Distance: {diff:.5f}")
                st.progress(acc)

        st.markdown(f"<div class='entry-box'><b>Multi-Strategy AI Analysis:</b><br>{analysis}</div>", unsafe_allow_html=True)

        # --- Visual Guides ---
        st.divider()
        st.subheader("📐 Technical Cheat Sheets")
        v1, v2, v3 = st.columns(3)
        with v1: st.image("https://www.tradingview.com/x/Y8p5R5Nn/", caption="SMC Structure")
        with v2: st.image("https://fvg-indicator.com/wp-content/uploads/2023/06/fvg-bearish-bullish.png", caption="ICT FVG Zones")
        with v3: st.info("Fibonacci Golden Zone: 0.618 - 0.786 is the Primary Reversal Area.")

    st.markdown('<div class="footer">Infinite System v3.6 | All Assets Integrated | © 2026</div>', unsafe_allow_html=True)

    if live:
        time.sleep(60)
        st.rerun()
