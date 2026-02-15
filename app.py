import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import time
import re
import requests

# --- 1. CONFIGURATION & UI STYLE ---
st.set_page_config(page_title="Infinite System v4.0", layout="wide", page_icon="📈")

st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1a1c24; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    .signal-badge { padding: 5px 12px; border-radius: 5px; font-weight: bold; font-size: 13px; margin-right: 5px; }
    .smc { background-color: #ff9800; color: black; }
    .ict { background-color: #e91e63; color: white; }
    .fib { background-color: #4caf50; color: white; }
    .footer { position: fixed; bottom: 0; width: 100%; text-align: center; color: #555; padding: 10px; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# --- 2. AI ENGINE (GEMINI 3 + FALLBACK) ---
def get_ai_prediction(prompt, current_price):
    """
    පියවර 3 කින් යුත් ආරක්ෂිත AI මෙහෙයුම:
    1. Gemini 3 Flash (Primary)
    2. Hugging Face (Secondary)
    3. Rule-based Technical Analysis (Last Resort)
    """
    # Step 1: Gemini 3 Flash
    try:
        if "GEMINI_KEYS" in st.secrets:
            # සැමවිටම අලුත්ම Model එක භාවිතා කරන්න
            genai.configure(api_key=st.secrets["GEMINI_KEYS"][0])
            model = genai.GenerativeModel('gemini-3-flash-preview') 
            response = model.generate_content(prompt)
            if response.text: return response.text
    except Exception as e:
        st.sidebar.error(f"Gemini Error: {str(e)[:40]}")

    # Step 2: Hugging Face Fallback
    try:
        if "HF_TOKEN" in st.secrets:
            API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
            headers = {"Authorization": f"Bearer {st.secrets['HF_TOKEN']}"}
            payload = {"inputs": f"Analyze this trade: {prompt}", "parameters": {"max_new_tokens": 300}}
            res = requests.post(API_URL, headers=headers, json=payload, timeout=10)
            return res.json()[0]['generated_text']
    except:
        pass

    # Step 3: Emergency Static Analysis
    return f"🚨 AI Offline. Manual Signal: ENTRY NEAR {current_price}, TREND: NEUTRAL. Check API connections."

# --- 3. CORE TECHNICAL ANALYSIS LOGIC ---
def detect_strategies(df):
    signals = []
    last_close = df['Close'].iloc[-1]
    
    # SMC: Break of Structure (BOS)
    if last_close > df['High'].iloc[-10:-1].max():
        signals.append(("BOS", "smc", "Bullish Structure Break"))
    
    # ICT: Fair Value Gap (FVG) detection
    if df['Low'].iloc[-1] > df['High'].iloc[-3]:
        signals.append(("FVG", "ict", "Bullish Fair Value Gap"))
        
    # Fibonacci: Golden Zone (0.618)
    high = df['High'].max()
    low = df['Low'].min()
    fib_618 = high - (high - low) * 0.618
    if abs(last_close - fib_618) / last_close < 0.002:
        signals.append(("FIB", "fib", "Price at 0.618 Golden Zone"))
        
    return signals

# --- 4. DATA SYNCHRONIZATION ---
def fetch_data(symbol, tf):
    try:
        data = yf.download(symbol, period="5d", interval=tf, progress=False)
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        return data
    except: return pd.DataFrame()

# --- 5. USER INTERFACE & LOGIN ---
if "auth" not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Infinite Terminal Login")
    user = st.text_input("User ID")
    pw = st.text_input("Access Key", type="password")
    if st.button("Unlock System"):
        # මෙතැනදී ඔබේ Google Sheet එකට සම්බන්ධ වීමට ඉහත function එක භාවිතා කළ හැක
        if user == "admin" and pw == "1234": # Simple logic for demo
            st.session_state.auth = True
            st.rerun()
else:
    # --- MAIN TERMINAL ---
    st.sidebar.title("🎮 Command Center")
    market = st.sidebar.selectbox("Market", ["Forex", "Crypto"])
    assets = {"Forex": ["EURUSD=X", "GBPUSD=X", "XAUUSD=X"], "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD"]}
    pair = st.sidebar.selectbox("Asset Pair", assets[market])
    timeframe = st.sidebar.selectbox("Timeframe", ["5m", "15m", "1h", "4h", "1d"], index=2)
    
    df = fetch_data(pair, timeframe)
    
    if not df.empty:
        curr_p = df['Close'].iloc[-1]
        
        # Dashboard Header
        c1, c2, c3 = st.columns([2,1,1])
        with c1:
            st.title(f"📊 {pair} Real-Time Analysis")
            sigs = detect_strategies(df)
            for tag, cls, msg in sigs:
                st.markdown(f'<span class="signal-badge {cls}">{tag}</span> {msg}', unsafe_allow_html=True)
        
        with c2: st.metric("Live Price", f"{curr_p:.5f}")
        with c3: st.metric("Volatility", f"{df['High'].iloc[-1] - df['Low'].iloc[-1]:.5f}")

        # Charting
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # AI Deep Analysis Section
        if st.button("🚀 Run Gemini 3 Pro-Analysis"):
            with st.spinner("AI Thinking (Deep Reasoning)..."):
                prompt = f"""
                Analyze {pair} at {curr_p} using:
                - SMC: Look for Liquidity sweeps and BOS.
                - ICT: Identify Killzones and FVG.
                - Fibonacci: Check 0.618 and 0.786 levels.
                - Strategy: SK Strategy pattern identification.
                Output: Provide ENTRY, SL, and 3 TP levels. Explain the logic in Sinhala.
                """
                analysis = get_ai_prediction(prompt, curr_p)
                
                st.subheader("📝 Smart Strategy Output")
                st.info(analysis)
                
                # Auto-parse Entry/SL/TP (Regex)
                entry_match = re.search(r"ENTRY:\s*([\d.]+)", analysis)
                if entry_match:
                    st.success(f"Sniper Entry Detected: {entry_match.group(1)}")

    st.markdown('<div class="footer">Infinite System v4.0 | Powered by Gemini 3 Flash | 2026</div>', unsafe_allow_html=True)
