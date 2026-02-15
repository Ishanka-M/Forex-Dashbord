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
    .notif-badge { padding: 4px 10px; border-radius: 5px; font-size: 12px; font-weight: bold; margin-right: 5px; }
    .bg-smc { background-color: #ff9800; color: black; }
    .bg-ict { background-color: #e91e63; color: white; }
    .bg-liq { background-color: #9c27b0; color: white; }
    .bg-trend { background-color: #2196f3; color: white; }
</style>
""", unsafe_allow_html=True)

# --- 2. ADVANCED API FALLBACK & UTILS ---
def get_ai_analysis(prompt):
    # Method 1: Try Gemini
    try:
        keys = st.secrets["GEMINI_KEYS"]
        genai.configure(api_key=keys[0])
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # Method 2: Fallback to Hugging Face
        try:
            hf_token = st.secrets["HF_TOKEN"]
            API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
            headers = {"Authorization": f"Bearer {hf_token}"}
            payload = {"inputs": f"<s>[INST] {prompt} [/INST]"}
            response = requests.post(API_URL, headers=headers, json=payload)
            return response.json()[0]['generated_text']
        except:
            return "⚠️ AI Sync Error: Both Gemini & Hugging Face unreachable."

def get_alpha_vantage_data(symbol):
    # Hourly update logic (Limited to 25/day)
    try:
        api_key = st.secrets["ALPHA_VANTAGE_KEY"]
        url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}'
        r = requests.get(url)
        return r.json()
    except: return None

def calculate_technical_signals(df):
    # Simple logic for Dashboard Notifications
    signals = []
    close = df['Close'].iloc[-1]
    
    # SMC/ICT/Liquidity logic (Simplified for UI)
    if df['High'].iloc[-1] > df['High'].iloc[-5:].max(): signals.append(("LIQUIDITY", "bg-liq", "Buy-side Liquidity Taken"))
    if df['Close'].iloc[-1] > df['Close'].rolling(20).mean().iloc[-1]: signals.append(("TREND", "bg-trend", "Bullish Trend (S&R)"))
    
    # FVG Detection
    if df['Low'].iloc[-1] > df['High'].iloc[-3]: signals.append(("ICT/FVG", "bg-ict", "Bullish Fair Value Gap Detected"))
    
    # Fibonacci (0.618 level check)
    low, high = df['Low'].min(), df['High'].max()
    fib_618 = high - (high - low) * 0.618
    if abs(close - fib_618) < 0.0010: signals.append(("FIB", "bg-smc", "Price at 0.618 Golden Ratio"))
    
    return signals

# --- 3. DATABASE SETUP ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        cred_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(cred_info, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Forex_User_DB").sheet1 
    except: return None

# --- 4. LOGIN LOGIC ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "last_price" not in st.session_state: st.session_state.last_price = 0.0

if not st.session_state.logged_in:
    st.title("🔐 Infinite System Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Access Terminal"):
        sheet = get_user_sheet()
        if sheet:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i["Username"]) == u), None)
            if user and str(user["Password"]) == p:
                st.session_state.logged_in = True
                st.session_state.user_data = user
                st.rerun()

if st.session_state.logged_in:
    user = st.session_state.user_data
    # System Hourly Update Simulation
    if "last_sync" not in st.session_state or (datetime.now() - st.session_state.last_sync).seconds > 3600:
        st.session_state.last_sync = datetime.now()
        # මෙතනදී Alpha Vantage හරහා user account values update කල හැක

    # --- 5. SIDEBAR & ASSETS ---
    st.sidebar.markdown("### 🚨 High Impact News")
    # (News logic remains same...)
    
    pair = st.sidebar.selectbox("Asset (Forex & Crypto)", 
        ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X", "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD"])
    tf_choice = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=4)
    live_mode = st.sidebar.toggle("🚀 LIVE MODE", value=True)

    # --- 6. DATA & DASHBOARD NOTIFICATIONS ---
    df = yf.download(pair, period="1mo", interval=tf_choice, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        curr_price = float(df['Close'].iloc[-1])
        
        # UI Top Row
        c1, c2 = st.columns([2,1])
        with c1: 
            st.title(f"📊 {pair} Pro Analysis")
            # Smart Notifications
            tech_signals = calculate_technical_signals(df)
            notif_html = ""
            for tag, color, msg in tech_signals:
                notif_html += f'<span class="notif-badge {color}">{tag}: {msg}</span>'
            st.markdown(notif_html, unsafe_allow_html=True)
            
        with c2: 
            price_class = "price-up" if curr_price >= st.session_state.last_price else "price-down"
            st.markdown(f"<br>LIVE PRICE: <span class='{price_class}'>{curr_price:.5f}</span>", unsafe_allow_html=True)
            st.session_state.last_price = curr_price

        # --- 7. CHART ---
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=0, b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # --- 8. AI STRATEGY ENGINE (SMC, SK, ICT, RETAIL) ---
        st.divider()
        strategy_prompt = f"""
        Analyze {pair} at {curr_price} using:
        1. SMC (Market Structure, BOS, CHoCH)
        2. ICT (Killzones, FVG, Order Blocks)
        3. Fibonacci levels & SK Strategy
        4. Retail Sentiment vs Liquidity Grab
        5. Patterns & Indicators (RSI, MACD)
        Give a sniper trade signal: ENTRY, SL, TP. 
        Language: Sinhala.
        """
        analysis = get_ai_analysis(strategy_prompt)
        
        # UI Summary Cards
        entry_p = re.search(r"ENTRY[:\s]+([\d.]+)", analysis, re.IGNORECASE)
        sl_p = re.search(r"SL[:\s]+([\d.]+)", analysis, re.IGNORECASE)
        tp_p = re.search(r"TP[:\s]+([\d.]+)", analysis, re.IGNORECASE)

        col_sig, col_prog = st.columns([2, 1])
        with col_sig:
            st.subheader("📝 Professional Strategy Summary")
            s1, s2, s3 = st.columns(3)
            with s1: st.markdown(f"<div class='summary-card'><b>ENTRY (Level)</b><br><span style='color:#00d4ff; font-size:22px;'>{entry_p.group(1) if entry_p else 'N/A'}</span></div>", unsafe_allow_html=True)
            with s2: st.markdown(f"<div class='summary-card'><b>STOP LOSS</b><br><span style='color:#ff4b4b; font-size:22px;'>{sl_p.group(1) if sl_p else 'N/A'}</span></div>", unsafe_allow_html=True)
            with s3: st.markdown(f"<div class='summary-card'><b>TAKE PROFIT</b><br><span style='color:#00ff00; font-size:22px;'>{tp_p.group(1) if tp_p else 'N/A'}</span></div>", unsafe_allow_html=True)

        with col_prog:
            st.subheader("🎯 Market Intelligence")
            st.write(f"Trend Strength: {'High' if len(tech_signals) > 2 else 'Medium'}")
            st.progress(min(len(tech_signals) * 25, 100))

        st.markdown(f"<div class='entry-box'><b>Multi-Strategy AI Deep Analysis:</b><br>{analysis}</div>", unsafe_allow_html=True)

        # --- 9. SMC & EDUCATIONAL VISUALS ---
        st.divider()
        st.subheader("📐 Technical Layouts")
        cn1, cn2 = st.columns(2)
        with cn1:
            st.info("💡 SMC/ICT Market Structure")
            st.image("https://www.tradingview.com/x/Y8p5R5Nn/", caption="Structure Break Analysis")
        with cn2:
            st.warning("📊 Retail vs Liquidity")
            st.image("https://fvg-indicator.com/wp-content/uploads/2023/06/fvg-bearish-bullish.png", caption="FVG/Liquidity Zones")

    st.markdown('<div class="footer">Infinite System v3.5 | SMC & ICT Integrated | © 2026</div>', unsafe_allow_html=True)

    if live_mode:
        time.sleep(60)
        st.rerun()
