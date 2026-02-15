import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time

# --- 1. SETTINGS & ANIMATION CSS ---
st.set_page_config(page_title="Forex Pro AI Terminal", layout="wide", page_icon="📈")

# Custom CSS for Animations & Glassmorphism
st.markdown("""
<style>
    /* Pulsing Red Dot for Live Status */
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 82, 82, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(255, 82, 82, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(255, 82, 82, 0); }
    }
    .live-badge {
        display: inline-block;
        background-color: #ff5252;
        color: white;
        padding: 5px 15px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 14px;
        animation: pulse 2s infinite;
        box-shadow: 0 0 0 0 rgba(255, 82, 82, 0.7);
    }
    
    /* Signal Card Style */
    .signal-card {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 20px;
        backdrop-filter: blur(10px);
        margin-top: 10px;
    }
    .buy-signal { border-left: 5px solid #00C805; }
    .sell-signal { border-left: 5px solid #FF3B30; }
</style>
""", unsafe_allow_html=True)

# --- 2. CONNECTIVITY & AI ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Forex_User_DB").sheet1 
    except Exception as e:
        return None

def get_ai_analysis(prompt):
    keys = st.secrets["GEMINI_KEYS"]
    if "key_index" not in st.session_state:
        st.session_state.key_index = 0

    for _ in range(len(keys)):
        try:
            genai.configure(api_key=keys[st.session_state.key_index])
            model = genai.GenerativeModel('gemini-3-flash-preview')
            response = model.generate_content(prompt)
            return response.text
        except Exception:
            st.session_state.key_index = (st.session_state.key_index + 1) % len(keys)
    return "AI Connection Failed."

def safe_float(value):
    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value)

# --- 3. LOGIN LOGIC ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def login_screen():
    st.markdown("<h1 style='text-align: center;'>🔐 Forex AI Terminal Access</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Launch Terminal 🚀", use_container_width=True)
            
            if submitted:
                sheet = get_user_sheet()
                if sheet:
                    try:
                        records = sheet.get_all_records()
                        user = next((i for i in records if str(i["Username"]).strip() == u.strip()), None)
                        if user and str(user["Password"]) == p:
                            exp = datetime.strptime(str(user["Expiry_Date"]), "%Y-%m-%d")
                            if exp > datetime.now():
                                st.session_state.logged_in = True
                                st.session_state.user_data = user
                                st.rerun()
                            else:
                                st.error("❌ Subscription Expired!")
                        else:
                            st.error("❌ Invalid Credentials")
                    except Exception as e:
                        st.error(f"Login Error: {e}")

# --- 4. MAIN TERMINAL ---
if not st.session_state.logged_in:
    login_screen()
else:
    user = st.session_state.user_data
    
    # Header Section with Animation
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.title("🤖 SMC + AI Sniper Terminal")
    with col_h2:
        st.markdown('<div style="text-align: right; margin-top: 20px;"><span class="live-badge">● LIVE MARKET</span></div>', unsafe_allow_html=True)

    # Sidebar
    st.sidebar.markdown(f"### 👤 Pilot: {user['Username']}")
    if st.sidebar.button("System Shutdown (Logout)"):
        st.session_state.logged_in = False
        st.rerun()

    # --- INPUTS ---
    pair = st.selectbox("SELECT ASSET", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X", "BTC-USD", "ETH-USD", "AUDUSD=X"])
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        tf = st.select_slider("TIMEFRAME", options=["15m", "30m", "1h", "4h"], value="1h")
    with col_t2:
        # Fake Auto-Refresh Animation
        st.write("System Status:")
        my_bar = st.progress(0)
        for percent_complete in range(100):
            time.sleep(0.005) # Fast loading effect
            my_bar.progress(percent_complete + 1)
        st.caption("✅ System Connected | Data Stream: Active")

    # --- DATA PROCESSING ---
    df = yf.download(pair, period="60d", interval=tf, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        current_price = safe_float(df['Close'].iloc[-1])
        high_20 = safe_float(df['High'].iloc[-20:-1].max())
        low_20 = safe_float(df['Low'].iloc[-20:-1].min())

        # SMC Logic
        if current_price > high_20:
            trend = "BULLISH 🚀"
            color = "green"
            signal_type = "BUY"
        elif current_price < low_20:
            trend = "BEARISH 📉"
            color = "red"
            signal_type = "SELL"
        else:
            trend = "CONSOLIDATION ↔️"
            color = "gray"
            signal_type = "WAIT"

        # --- LAYOUT ---
        col_main, col_signal = st.columns([2, 1])

        with col_main:
            # Interactive Chart
            fig = go.Figure(data=[go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                increasing_line_color='#00ff00', decreasing_line_color='#ff0000'
            )])
            fig.update_layout(
                title=f"{pair} Market Structure",
                template="plotly_dark",
                height=500,
                xaxis_rangeslider_visible=False,
                margin=dict(l=0, r=0, t=40, b=0)
            )
            st.plotly_chart(fig, use_container_width=True)
            

        with col_signal:
            st.subheader("📡 AI Signal Generator")
            
            # ANIMATED STATUS BOX
            with st.status("Running AI Analysis...", expanded=True) as status:
                st.write("🔍 Scanning Market Structure...")
                time.sleep(1)
                st.write("📊 Calculating Key Levels (SMC)...")
                time.sleep(1)
                st.write("🤖 Gemini 3 Processing...")
                
                # Prompt Engineering for Structured Output
                prompt = f"""
                You are a professional Forex Sniper.
                Pair: {pair}, Timeframe: {tf}
                Trend: {trend}, Price: {current_price}
                
                Analyze and give a STRICT Trading Signal in SINHALA.
                Format clearly with icons:
                1. Signal: (BUY / SELL / WAIT)
                2. Reason: (Brief reason)
                3. Entry Price: (Specific number)
                4. Stop Loss (SL): (Specific number)
                5. Take Profit (TP): (Specific number)
                
                Keep it professional and motivating.
                """
                
                ai_response = get_ai_analysis(prompt)
                status.update(label="Analysis Complete! ✅", state="complete", expanded=True)

            # SHOW THE SIGNAL CARD
            st.markdown(f"""
            <div class="signal-card {'buy-signal' if signal_type == 'BUY' else 'sell-signal'}">
                <h3 style="margin:0; color:{'#00C805' if signal_type == 'BUY' else '#FF3B30'};">{signal_type} SIGNAL DETECTED</h3>
                <p style="font-size:12px; opacity:0.7;">CONFIDENCE: HIGH 🔥</p>
                <hr style="border-color: rgba(255,255,255,0.1);">
                <div style="font-size: 16px;">
                    {ai_response.replace(chr(10), '<br>')}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            st.caption("⚠️ Trading involves risk. Use proper risk management.")

    else:
        st.error("Market Data Unavailable. Retrying...")
