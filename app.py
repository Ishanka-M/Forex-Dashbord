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
    .price-up { color: #00ff00; font-size: 24px; font-weight: bold; animation: fadein 0.5s; }
    .price-down { color: #ff0000; font-size: 24px; font-weight: bold; animation: fadein 0.5s; }
    .footer { position: fixed; bottom: 0; width: 100%; text-align: center; color: #00d4ff; padding: 10px; background: rgba(0,0,0,0.8); z-index: 100;}
    .entry-box { background: rgba(0, 212, 255, 0.05); border: 1px solid #00d4ff; padding: 20px; border-radius: 10px; margin-bottom: 20px; line-height: 1.6;}
    .news-card { background: rgba(255, 255, 255, 0.05); border-left: 5px solid #ffcc00; padding: 15px; border-radius: 5px; margin-top: 10px;}
    .red-folder { background: rgba(255, 0, 0, 0.15); border: 1px solid #ff4b4b; padding: 12px; border-radius: 8px; margin-bottom: 8px; color: #ff4b4b; font-weight: bold; border-left: 5px solid #ff0000;}
    @keyframes fadein { from { opacity: 0; } to { opacity: 1; } }
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
    except: return "AI Error: කරුණාකර Manual Sync ඔබන්න."

def safe_float(value):
    return float(value.iloc[0]) if isinstance(value, pd.Series) else float(value)

# --- 3. SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "last_price" not in st.session_state: st.session_state.last_price = 0.0

# --- 4. LOGIN LOGIC ---
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

    # --- 5. SIDEBAR: RED FOLDER & LIVE MODE ---
    st.sidebar.markdown("### 🚨 High Impact News (Red Folder)")
    sl_tz = pytz.timezone('Asia/Colombo')
    now_sl = datetime.now(sl_tz)
    
    # 2026 Feb 16 actual news schedule
    news_events = [
        {"event": "JPY: GDP Growth Rate (Preliminary)", "time": datetime(2026, 2, 16, 5, 20, tzinfo=sl_tz)},
        {"event": "USD: Presidents' Day (Bank Holiday)", "time": datetime(2026, 2, 16, 8, 0, tzinfo=sl_tz)},
        {"event": "EUR: Eurogroup Meetings", "time": datetime(2026, 2, 16, 14, 30, tzinfo=sl_tz)}
    ]

    for news in news_events:
        diff = news["time"] - now_sl
        if diff.total_seconds() > 0:
            h, rem = divmod(int(diff.total_seconds()), 3600)
            m, s = divmod(rem, 60)
            st.sidebar.markdown(f"<div class='red-folder'>{news['event']}<br><small>ඉතිරි කාලය: {h:02d}h {m:02d}m {s:02d}s</small></div>", unsafe_allow_html=True)
        else:
            st.sidebar.markdown(f"<div class='red-folder' style='background:rgba(128,128,128,0.2); border-color:gray; color:gray;'>{news['event']} (PASSED/ACTIVE)</div>", unsafe_allow_html=True)

    st.sidebar.divider()
    live_mode = st.sidebar.toggle("🚀 LIVE MODE (Auto-Refresh)", value=True)
    if live_mode:
        st.sidebar.caption("Refreshing every 60s...")

    # --- 6. TERMINAL SETTINGS ---
    st.sidebar.subheader("Terminal Settings")
    pair = st.sidebar.selectbox("Select Asset", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X", "BTC-USD"], index=0)
    tf_choice = st.sidebar.selectbox("Select Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=4)
    
    period_map = {"1m": "1d", "5m": "5d", "15m": "5d", "30m": "5d", "1h": "1mo", "4h": "1mo", "1d": "6mo"}
    df = yf.download(pair, period=period_map[tf_choice], interval=tf_choice, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        curr_price = safe_float(df['Close'].iloc[-1])
        price_class = "price-up" if curr_price >= st.session_state.last_price else "price-down"
        st.session_state.last_price = curr_price

        # UI Header
        c1, c2, c3 = st.columns([2,1,1])
        with c1: st.title(f"📊 {pair} ({tf_choice})")
        with c2: st.markdown(f"LIVE PRICE:<br><span class='{price_class}'>{curr_price:.5f}</span>", unsafe_allow_html=True)
        with c3:
            if st.button("🔄 Manual AI Sync"):
                st.cache_data.clear()
                st.rerun()

        # --- 7. CHART & SNIPER ENTRY ---
        col_chart, col_signal = st.columns([2, 1])
        with col_chart:
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=10, r=10, t=10, b=10), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_signal:
            st.subheader("🎯 Sniper Entry Control")
            signal_prompt = f"Trade signal for {pair} at {curr_price} on {tf_choice}. Provide ENTRY, SL, TP. Explain in Sinhala (SMC context)."
            analysis = get_ai_analysis(signal_prompt)
            st.markdown(f"<div class='entry-box'>{analysis}</div>", unsafe_allow_html=True)
            
            try:
                entry_match = re.search(r"ENTRY[:\s]+([\d.]+)", analysis, re.IGNORECASE)
                if entry_match:
                    entry_p = float(entry_match.group(1))
                    diff_val = abs(curr_price - entry_p)
                    thresh = 500.0 if "BTC" in pair else 0.0050
                    prog = max(0.0, min(1.0, 1.0 - (diff_val / thresh)))
                    st.write(f"**Distance to Entry:** `{diff_val:.5f}`")
                    st.progress(prog)
                    if diff_val < (0.0001 if "USD" in pair else 1.0):
                        st.toast("🚀 ENTRY POINT REACHED!", icon="🔥")
                        st.balloons()
            except: pass

        st.divider()

        # --- 8. AI INSIGHTS & SMC DIAGRAMS ---
        st.subheader("📰 AI Deep Market Insights & SMC Visuals")
        col_n1, col_n2 = st.columns([1, 1])
        
        with col_n1:
            st.info("💡 **Fundamental & Sentiment Analysis**")
            news_prompt = f"Summarize fundamental impact for {pair} today {now_sl.date()}. Explain why banks are moving price. In Sinhala."
            news_res = get_ai_analysis(news_prompt)
            st.markdown(f"<div class='news-card'>{news_res}</div>", unsafe_allow_html=True)
        
        with col_n2:
            st.warning("📐 **SMC / ICT Technical Concepts**")
            st.write("වර්තමාන Market Structure එක තේරුම් ගැනීමට මෙම Diagrams අධ්‍යයනය කරන්න:")
            
            # --- Diagram Section (Syntax Fixed) ---
            st.markdown("#### 1. Market Structure (BOS & ChoCH)")
            st.image("https://www.tradingview.com/x/Y8p5R5Nn/", caption="BOS & ChoCH: Trend එක වෙනස් වන ආකාරය")
            
            st.divider()
            
            st.markdown("#### 2. Order Block & Liquidity Sweep")
            st.image("https://www.tradingview.com/x/z8V6E0Zk/", caption="Institutions ඇතුළු වන කලාප")

            st.divider()
            
            st.markdown("#### 3. Fair Value Gap (FVG)")
            st.image("https://fvg-indicator.com/wp-content/uploads/2023/06/fvg-bearish-bullish.png", caption="Market Imbalance (පරතරය)")

    # Footer
    st.markdown('<div class="footer">Infinite System v2.6 | Auto-Refreshed | © 2026</div>', unsafe_allow_html=True)

    # --- 9. AUTO REFRESH LOGIC ---
    if live_mode:
        time.sleep(60)
        st.rerun()
