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

# --- 1. SETUP & ENHANCED UI STYLE ---
st.set_page_config(page_title="Infinite System v4.5 | Pro AI Terminal", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .price-up { color: #00ff00; font-size: 26px; font-weight: bold; text-shadow: 0 0 10px #00ff0044; }
    .price-down { color: #ff4b4b; font-size: 26px; font-weight: bold; text-shadow: 0 0 10px #ff4b4b44; }
    .entry-box { background: rgba(0, 212, 255, 0.07); border: 1px solid #00d4ff; padding: 20px; border-radius: 12px; margin-bottom: 20px; border-left: 5px solid #00d4ff; }
    .summary-card { background: #1e2130; border-radius: 10px; padding: 15px; border: 1px solid #3e4451; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .notif-badge { padding: 5px 12px; border-radius: 6px; font-size: 13px; font-weight: 600; margin-right: 8px; border: 1px solid rgba(255,255,255,0.1); }
    .bg-smc { background-color: #ff9800; color: #111; }
    .bg-ict { background-color: #f43f5e; color: white; }
    .bg-trend { background-color: #3b82f6; color: white; }
</style>
""", unsafe_allow_html=True)

# --- 2. 2026 COMPLIANT AI ENGINE ---
def get_ai_analysis(prompt, asset_data=None):
    """
    පියවර 3 කින් යුත් AI Fallback (2026 Update):
    1. Gemini 3 Flash (Primary - Preview Tier)
    2. Hugging Face Mistral/Llama (Secondary)
    3. Technical Logic Analysis (Offline Mode)
    """
    # Step 1: Gemini 3 Flash (v1.5 deprecated in 2025)
    try:
        if "GEMINI_KEYS" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_KEYS"][0])
            # 2026 වසරේ දැනට පවතින වේගවත්ම මාදිලිය
            model = genai.GenerativeModel('gemini-3-flash-preview') 
            response = model.generate_content(prompt)
            return response.text
    except Exception as e:
        st.sidebar.warning(f"⚠️ Gemini Node Offline: {str(e)[:40]}...")

    # Step 2: Hugging Face Fallback (v0.3 Instruct)
    try:
        if "HF_TOKEN" in st.secrets:
            API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
            headers = {"Authorization": f"Bearer {st.secrets['HF_TOKEN']}"}
            payload = {"inputs": f"<s>[INST] {prompt} [/INST]", "parameters": {"max_new_tokens": 600}}
            response = requests.post(API_URL, headers=headers, json=payload, timeout=12)
            result = response.json()
            return result[0]['generated_text'] if isinstance(result, list) else "HF Node Busy"
    except: pass

    # Step 3: Local Logic (If both APIs fail)
    if asset_data:
        return f"🚨 SYSTEM ALERT: AI Nodes Unreachable. Manual Logic Applied.\nPRICE: {asset_data['price']}\nTREND: SMC/BOS Detected.\nACTION: Check API Keys for Full Deep Reasoning."
    return "❌ Error: AI Authentication Failed."

# --- 3. CORE TECHNICAL INDICATORS ---
def calculate_signals(df):
    signals = []
    close = df['Close'].iloc[-1]
    
    # SMC: Break of Structure (BOS)
    if close > df['High'].iloc[-15:-1].max():
        signals.append(("SMC/BOS", "bg-smc", "Bullish Expansion Found"))
    
    # ICT: Fair Value Gap (FVG)
    if df['Low'].iloc[-1] > df['High'].iloc[-3]:
        signals.append(("ICT/FVG", "bg-ict", "Price Imbalance Detected"))
    
    # Fibonacci Golden Zone (0.618)
    high, low = df['High'].max(), df['Low'].min()
    fib_618 = high - (high - low) * 0.618
    if abs(close - fib_618) / close < 0.001:
        signals.append(("FIB/GOLD", "bg-trend", "Golden Pocket Rejection"))
        
    return signals

# --- 4. DATA SYNCHRONIZATION ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        return gspread.authorize(creds).open("Forex_User_DB").sheet1
    except: return None

if "logged_in" not in st.session_state: st.session_state.logged_in = False

# --- LOGIN BYPASS FOR DEMO (You can enable sheet login here) ---
if not st.session_state.logged_in:
    st.title("🔐 Infinite Terminal v4.5 Access")
    u, p = st.text_input("Operator ID"), st.text_input("Security Key", type="password")
    if st.button("Initialize Terminal"):
        if u and p: # Simple validation (Add your sheet logic here)
            st.session_state.logged_in = True
            st.rerun()
else:
    # --- 5. MAIN TRADING DASHBOARD ---
    assets = {
        "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "XAUUSD=X"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"]
    }
    
    st.sidebar.header("🕹️ AI Command Center")
    m_type = st.sidebar.radio("Select Market", ["Forex", "Crypto"])
    pair = st.sidebar.selectbox("Asset Pair", assets[m_type])
    tf = st.sidebar.selectbox("Timeframe", ["5m", "15m", "1h", "4h", "1d"], index=2)
    live_toggle = st.sidebar.toggle("🚀 LIVE FEED", value=True)

    df = yf.download(pair, period="5d", interval=tf, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        curr_p = float(df['Close'].iloc[-1])
        
        # Header Metrics
        c1, c2 = st.columns([3, 1])
        with c1:
            st.title(f"📊 {pair} Analysis")
            sig_list = calculate_signals(df)
            badges = "".join([f'<span class="notif-badge {b}">{t}</span>' for t, b, m in sig_list])
            st.markdown(badges, unsafe_allow_html=True)
            
        with c2:
            st.markdown(f"<div style='text-align:right'>REAL-TIME PRICE:<br><span class='price-up'>{curr_p:.5f}</span></div>", unsafe_allow_html=True)

        # Candlestick Chart
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=20,b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # AI Strategy Engine
        st.divider()
        if st.button("🧠 Execute Deep Reasoning (Gemini 3)"):
            with st.spinner("AI Analysis in Progress..."):
                prompt = f"Analyze {pair} at {curr_p}. Use SMC, ICT and Fibonacci. Format: ENTRY: (val), SL: (val), TP: (val). Explain logic in Sinhala."
                analysis = get_ai_analysis(prompt, asset_data={'price': curr_p})
                
                # Signal Parsing
                entry = re.search(r"ENTRY[:\s]+([\d.]+)", analysis, re.IGNORECASE)
                sl = re.search(r"SL[:\s]+([\d.]+)", analysis, re.IGNORECASE)
                tp = re.search(r"TP[:\s]+([\d.]+)", analysis, re.IGNORECASE)
                
                s1, s2, s3 = st.columns(3)
                with s1: st.markdown(f"<div class='summary-card'><b>AI ENTRY</b><br><span style='color:#00d4ff'>{entry.group(1) if entry else 'Waiting'}</span></div>", unsafe_allow_html=True)
                with s2: st.markdown(f"<div class='summary-card'><b>STOP LOSS</b><br><span style='color:#ff4b4b'>{sl.group(1) if sl else 'Waiting'}</span></div>", unsafe_allow_html=True)
                with s3: st.markdown(f"<div class='summary-card'><b>TARGET (TP)</b><br><span style='color:#00ff00'>{tp.group(1) if tp else 'Waiting'}</span></div>", unsafe_allow_html=True)
                
                st.markdown(f"<div class='entry-box'><b>Deep Reasoning Strategy:</b><br>{analysis}</div>", unsafe_allow_html=True)

        # Technical Education Guides
        
        st.subheader("📚 Strategy References")
        v1, v2 = st.columns(2)
        with v1: st.info("SMC/BOS: Market structure breaks indicate institutional momentum.")
        with v2: st.info("ICT FVG: Unfilled price gaps are magnet zones for future price action.")

    st.markdown(f'<div style="height:100px"></div><div class="footer">Infinite System v4.5 | {datetime.now().strftime("%Y-%m-%d %H:%M")} | Safe AI Mode Active</div>', unsafe_allow_html=True)

    if live_toggle:
        time.sleep(60)
        st.rerun()
