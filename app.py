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
    .summary-card { background: rgba(255, 255, 255, 0.07); border-radius: 10px; padding: 15px; border: 1px solid #444; text-align: center; }
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

@st.cache_data(ttl=3600)
def get_ai_analysis(prompt):
    try:
        keys = st.secrets["GEMINI_KEYS"]
        genai.configure(api_key=keys[0])
        model = genai.GenerativeModel('gemini-3-flash-preview')
        response = model.generate_content(prompt)
        return response.text
    except: return "AI Error: Sync Error. කරුණාකර Manual Sync ඔබන්න."

def safe_float(value):
    return float(value.iloc[0]) if isinstance(value, pd.Series) else float(value)

# --- 3. LOGIN LOGIC ---
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
    role = str(user.get("Role", "")).lower().strip()

    # Admin Panel
    if role == "admin":
        with st.sidebar.expander("🛠️ Admin: Add User", expanded=False):
            new_u = st.text_input("New Username")
            new_p = st.text_input("New Password")
            if st.button("Create Account"):
                sheet = get_user_sheet()
                if sheet:
                    exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                    sheet.append_row([new_u, new_p, "user", exp])
                    st.success(f"User {new_u} added!")

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
            st.sidebar.markdown(f"<div class='red-folder'>{news['event']}<br><small>Starts in: {h:02d}h {m:02d}m {s:02d}s</small></div>", unsafe_allow_html=True)

    st.sidebar.divider()
    live_mode = st.sidebar.toggle("🚀 LIVE MODE", value=True)
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
        c1, c2 = st.columns([2,1])
        with c1: st.title(f"📊 {pair} Analysis")
        with c2: st.markdown(f"<br>LIVE PRICE: <span class='{price_class}'>{curr_price:.5f}</span>", unsafe_allow_html=True)

        # --- 6. CHART ---
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=0, b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # --- 7. PROGRESS & SUMMARY (CHART එකට යටින්) ---
        st.divider()
        
        signal_prompt = f"Give a sniper trade signal for {pair} at {curr_price}. ENTRY: (price), SL: (price), TP: (price). Sinhala explanation."
        analysis = get_ai_analysis(signal_prompt)
        
        entry_p = re.search(r"ENTRY[:\s]+([\d.]+)", analysis, re.IGNORECASE)
        sl_p = re.search(r"SL[:\s]+([\d.]+)", analysis, re.IGNORECASE)
        tp_p = re.search(r"TP[:\s]+([\d.]+)", analysis, re.IGNORECASE)

        col_sig, col_prog = st.columns([2, 1])

        with col_sig:
            st.subheader("📝 Sniper Trade Summary")
            s1, s2, s3 = st.columns(3)
            with s1: st.markdown(f"<div class='summary-card'><b>ENTRY</b><br><span style='color:#00d4ff; font-size:22px;'>{entry_p.group(1) if entry_p else 'N/A'}</span></div>", unsafe_allow_html=True)
            with s2: st.markdown(f"<div class='summary-card'><b>STOP LOSS</b><br><span style='color:#ff4b4b; font-size:22px;'>{sl_p.group(1) if sl_p else 'N/A'}</span></div>", unsafe_allow_html=True)
            with s3: st.markdown(f"<div class='summary-card'><b>TAKE PROFIT</b><br><span style='color:#00ff00; font-size:22px;'>{tp_p.group(1) if tp_p else 'N/A'}</span></div>", unsafe_allow_html=True)

        with col_prog:
            st.subheader("🎯 Distance to Entry")
            if entry_p:
                target = float(entry_p.group(1))
                diff = abs(curr_price - target)
                threshold = 500.0 if "BTC" in pair else 0.0050
                progress_val = max(0.0, min(1.0, 1.0 - (diff / threshold)))
                st.write(f"Current Gap: `{diff:.5f}`")
                st.progress(progress_val)
                if diff < (0.0001 if "USD" in pair else 1.0):
                    st.success("🚀 ENTRY ZONE REACHED!")

        st.markdown(f"<div class='entry-box'><b>Detailed AI Analysis:</b><br>{analysis}</div>", unsafe_allow_html=True)

        # --- 8. NEWS & SMC ---
        st.divider()
        st.subheader("📰 Insights & SMC Education")
        cn1, cn2 = st.columns(2)
        with cn1:
            st.info("💡 Fundamental Analysis")
            news_res = get_ai_analysis(f"Market news for {pair} today. Sinhala.")
            st.write(news_res)
        with cn2:
            st.warning("📐 SMC Technical Concepts")
            st.image("https://www.tradingview.com/x/Y8p5R5Nn/", caption="SMC Market Structure Guide")
            st.image("https://fvg-indicator.com/wp-content/uploads/2023/06/fvg-bearish-bullish.png", caption="FVG Concept Guide")

    st.markdown('<div class="footer">Infinite System v3.1 | Auto-Refresh: 60s | © 2026</div>', unsafe_allow_html=True)

    if live_mode:
        time.sleep(60)
        st.rerun()
