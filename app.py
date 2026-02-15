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

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System | Pro AI Terminal", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .price-up { color: #00ff00; font-size: 24px; font-weight: bold; }
    .price-down { color: #ff0000; font-size: 24px; font-weight: bold; }
    .footer { position: fixed; bottom: 0; width: 100%; text-align: center; color: #00d4ff; padding: 10px; background: rgba(0,0,0,0.8); z-index: 100;}
    .entry-box { background: rgba(0, 212, 255, 0.05); border: 1px solid #00d4ff; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
    .summary-card { background: rgba(255, 255, 255, 0.07); border-radius: 10px; padding: 15px; border: 1px solid #444; text-align: center; height: 110px; }
    .signal-label { font-size: 28px; font-weight: bold; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 10px; }
    .buy-signal { background-color: rgba(0, 255, 0, 0.2); color: #00ff00; border: 2px solid #00ff00; }
    .sell-signal { background-color: rgba(255, 0, 0, 0.2); color: #ff0000; border: 2px solid #ff0000; }
    .red-folder { background: rgba(255, 0, 0, 0.15); border: 1px solid #ff4b4b; padding: 12px; border-radius: 8px; margin-bottom: 8px; color: #ff4b4b; font-weight: bold; border-left: 5px solid #ff0000;}
</style>
""", unsafe_allow_html=True)

# --- 2. DATABASE & AI FUNCTIONS ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        cred_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(cred_info, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Forex_User_DB").sheet1 
    except: return None

# Fixed Manual Sync Logic using st.session_state for manual trigger
@st.cache_data(ttl=86400)
def get_ai_analysis(prompt, pair, price, trigger_time):
    try:
        keys = st.secrets["GEMINI_KEYS"]
        genai.configure(api_key=keys[0])
        model = genai.GenerativeModel('gemini-3-flash-preview')
        response = model.generate_content(prompt)
        return response.text
    except: return "AI Error: කරුණාකර 'Manual AI Sync' ඔබන්න."

def safe_float(value):
    return float(value.iloc[0]) if isinstance(value, pd.Series) else float(value)

# --- 3. LOGIN & SESSION ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "last_price" not in st.session_state: st.session_state.last_price = 0.0
if "sync_token" not in st.session_state: st.session_state.sync_token = time.time()

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
    # --- 4. SIDEBAR ---
    st.sidebar.markdown("### 🚨 High Impact News")
    sl_tz = pytz.timezone('Asia/Colombo')
    now_sl = datetime.now(sl_tz)
    
    news_events = [
        {"event": "JPY: GDP Growth Rate", "time": datetime(2026, 2, 16, 5, 20, tzinfo=sl_tz)},
        {"event": "USD: Presidents' Day", "time": datetime(2026, 2, 16, 8, 0, tzinfo=sl_tz)},
        {"event": "EUR: Eurogroup Meetings", "time": datetime(2026, 2, 16, 14, 30, tzinfo=sl_tz)}
    ]

    for news in news_events:
        diff = news["time"] - now_sl
        if diff.total_seconds() > 0:
            h, rem = divmod(int(diff.total_seconds()), 3600)
            m, s = divmod(rem, 60)
            st.sidebar.markdown(f"<div class='red-folder'>{news['event']}<br><small>{h:02d}h {m:02d}m {s:02d}s</small></div>", unsafe_allow_html=True)

    st.sidebar.divider()
    live_mode = st.sidebar.toggle("🚀 LIVE MODE (Auto-Refresh Price)", value=True)
    pair = st.sidebar.selectbox("Asset", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X", "BTC-USD"])
    tf_choice = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=4)
    
    # --- 5. DATA FETCH ---
    df = yf.download(pair, period="1mo", interval=tf_choice, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        curr_price = safe_float(df['Close'].iloc[-1])
        price_class = "price-up" if curr_price >= st.session_state.last_price else "price-down"
        st.session_state.last_price = curr_price

        # Header
        c_h1, c_h2, c_h3 = st.columns([2,1,1])
        with c_h1: st.title(f"📊 {pair} Terminal")
        with c_h2: st.markdown(f"LIVE PRICE:<br><span class='{price_class}'>{curr_price:.5f}</span>", unsafe_allow_html=True)
        with c_h3: 
            if st.button("🔄 Manual AI Sync"):
                st.session_state.sync_token = time.time() # Update token to bypass cache
                st.rerun()

        # --- 6. CHART (RESIZED) ---
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=380, margin=dict(l=0, r=0, t=0, b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # --- 7. SNIPER SUMMARY & PROGRESS ---
        st.divider()
        
        prompt = f"Sniper signal for {pair} at {curr_price}. Start with 'DIRECTION: BUY' or 'DIRECTION: SELL'. Format: ENTRY: (price), SL: (price), TP: (price). In Sinhala."
        analysis = get_ai_analysis(prompt, pair, curr_price, st.session_state.sync_token)

        # Detection Logic
        dir_match = re.search(r"DIRECTION[:\s]+(BUY|SELL)", analysis, re.IGNORECASE)
        entry_match = re.search(r"ENTRY[:\s]+([\d.]+)", analysis, re.IGNORECASE)
        sl_match = re.search(r"SL[:\s]+([\d.]+)", analysis, re.IGNORECASE)
        tp_match = re.search(r"TP[:\s]+([\d.]+)", analysis, re.IGNORECASE)

        direction = dir_match.group(1).upper() if dir_match else "N/A"
        e_val = entry_match.group(1) if entry_match else "N/A"
        s_val = sl_match.group(1) if sl_match else "N/A"
        t_val = tp_match.group(1) if tp_match else "N/A"

        # Signal Label (Buy/Sell)
        if direction != "N/A":
            css_class = "buy-signal" if direction == "BUY" else "sell-signal"
            st.markdown(f"<div class='signal-label {css_class}'>SNIPER {direction} ORDER</div>", unsafe_allow_html=True)

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1: st.markdown(f"<div class='summary-card'><b>ENTRY</b><br><span style='color:#00d4ff; font-size:22px;'>{e_val}</span></div>", unsafe_allow_html=True)
        with col_s2: st.markdown(f"<div class='summary-card'><b>STOP LOSS</b><br><span style='color:#ff4b4b; font-size:22px;'>{s_val}</span></div>", unsafe_allow_html=True)
        with col_s3: st.markdown(f"<div class='summary-card'><b>TAKE PROFIT</b><br><span style='color:#00ff00; font-size:22px;'>{t_val}</span></div>", unsafe_allow_html=True)

        if e_val != "N/A":
            diff = abs(curr_price - float(e_val))
            threshold = 500.0 if "BTC" in pair else 0.0050
            progress = max(0.0, min(1.0, 1.0 - (diff / threshold)))
            st.write(f"**Distance to Entry:** `{diff:.5f}`")
            st.progress(progress)

        st.markdown(f"<div class='entry-box'><b>AI Breakdown:</b><br>{analysis}</div>", unsafe_allow_html=True)

        # --- 8. INSIGHTS & SMC ---
        st.divider()
        st.subheader("📰 Insights & SMC")
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            st.info("💡 Fundamental Sentiment")
            st.write(get_ai_analysis(f"Brief news for {pair} today. Sinhala.", pair, "fixed", st.session_state.sync_token))
        with col_n2:
            st.warning("📐 Technical Concept")
            st.image("https://www.tradingview.com/x/Y8p5R5Nn/", caption="SMC Structure")

    st.markdown('<div class="footer">Infinite System v3.3 | Manual Sync Fixed | © 2026</div>', unsafe_allow_html=True)

    if live_mode:
        time.sleep(60)
        st.rerun()
