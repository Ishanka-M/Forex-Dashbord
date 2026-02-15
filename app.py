import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import feedparser

# --- 1. SETTINGS & CONFIG ---
st.set_page_config(page_title="Forex Pro AI System", layout="wide")

# --- 2. GOOGLE SHEETS CONNECTION ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Forex_User_DB").sheet1 
    except Exception as e:
        st.error(f"Database Error: {e}")
        return None

# --- 3. AI LOGIC (GEMINI 3 FLASH) ---
def get_ai_analysis(prompt):
    keys = st.secrets["GEMINI_KEYS"]
    if "key_index" not in st.session_state:
        st.session_state.key_index = 0

    for _ in range(len(keys)):
        try:
            genai.configure(api_key=keys[st.session_state.key_index])
            # 2026 නවතම Model එක
            model = genai.GenerativeModel('gemini-3-flash-preview')
            response = model.generate_content(prompt)
            return response.text
        except Exception:
            st.session_state.key_index = (st.session_state.key_index + 1) % len(keys)
    return "AI සේවා කාර්යබහුලයි. කරුණාකර විනාඩියකින් උත්සාහ කරන්න."

# --- 4. DATA HELPER (CHART FIX) ---
def safe_float(value):
    # දත්ත තනි අංකයක් බවට පත් කිරීම (Series error විසඳීම)
    if isinstance(value, pd.Series):
        return float(value.iloc[0])
    return float(value)

# --- 5. MAIN APP FLOW ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def login_screen():
    st.title("🔐 Forex Pro Login")
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login Now", use_container_width=True):
            sheet = get_user_sheet()
            if sheet:
                try:
                    records = sheet.get_all_records()
                    user = next((i for i in records if str(i["Username"]).strip() == u.strip()), None)
                    if user and str(user["Password"]) == p:
                        # Date Check
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

if not st.session_state.logged_in:
    login_screen()
else:
    # --- DASHBOARD ---
    user = st.session_state.user_data
    role = str(user.get("Role", "")).lower().strip() # Admin check fix
    
    # Sidebar
    st.sidebar.title(f"👤 {user['Username']}")
    st.sidebar.info(f"Role: {role.capitalize()}")
    
    # --- ADMIN PANEL (Fixed) ---
    if role == "admin":
        with st.sidebar.expander("🛠️ Admin Controls", expanded=True):
            new_u = st.text_input("New User:")
            new_p = st.text_input("New Pass:")
            days = st.number_input("Days:", value=30, step=1)
            if st.button("Add Member"):
                sheet = get_user_sheet()
                if sheet:
                    exp_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                    sheet.append_row([new_u, new_p, "user", exp_date])
                    st.success("User Added Successfully!")

    if st.sidebar.button("Logout", type="primary"):
        st.session_state.logged_in = False
        st.rerun()

    # --- TRADING SECTION ---
    st.title("📈 Smart Money AI Dashboard")

    # NEW PAIRS ADDED
    pair_options = [
        "EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X", 
        "AUDUSD=X", "USDCAD=X", "NZDUSD=X", "BTC-USD", "ETH-USD"
    ]
    pair = st.selectbox("Select Asset Pair", pair_options)
    tf = st.select_slider("Timeframe", options=["15m", "1h", "4h", "1d"], value="1h")

    # Data Loading
    with st.spinner("Fetching Market Data..."):
        try:
            df = yf.download(pair, period="60d", interval=tf, progress=False)
            
            # --- CRITICAL FIX FOR YFINANCE MULTI-INDEX ---
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            if not df.empty:
                # Calculations with safe_float
                current_price = safe_float(df['Close'].iloc[-1])
                high_20 = safe_float(df['High'].iloc[-20:-1].max())
                low_20 = safe_float(df['Low'].iloc[-20:-1].min())

                # Market Structure Logic
                if current_price > high_20:
                    status = "BULLISH (UP) 🟢"
                    color = "green"
                elif current_price < low_20:
                    status = "BEARISH (DOWN) 🔴"
                    color = "red"
                else:
                    status = "RANGING ↔️"
                    color = "gray"

                # UI Layout
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Chart
                    fig = go.Figure(data=[go.Candlestick(
                        x=df.index,
                        open=df['Open'], high=df['High'],
                        low=df['Low'], close=df['Close'],
                        name=pair
                    )])
                    fig.update_layout(
                        title=f"{pair} ({tf}) Analysis",
                        yaxis_title="Price",
                        xaxis_rangeslider_visible=False,
                        template="plotly_dark",
                        height=500,
                        margin=dict(l=0, r=0, t=30, b=0)
                    )
                    st.plotly_chart(fig, use_container_width=True) # or width="stretch"

                with col2:
                    st.subheader("Market Insight")
                    st.markdown(f"### Status: :{color}[{status}]")
                    st.metric("Current Price", f"{current_price:.5f}")
                    
                    st.divider()
                    st.write("🤖 **AI Prediction**")
                    if st.button("Generate Signal"):
                        with st.spinner("Analyzing..."):
                            prompt = f"""
                            Act as a professional Forex trader.
                            Asset: {pair}
                            Timeframe: {tf}
                            Current Price: {current_price}
                            Market Structure: {status}
                            High (20 candles): {high_20}
                            Low (20 candles): {low_20}
                            
                            Provide a trading signal (Buy/Sell/Wait) with Entry, Stop Loss, and Take Profit levels.
                            Reply in SINHALA language briefly.
                            """
                            st.success(get_ai_analysis(prompt))

            else:
                st.error("No data received from market.")

        except Exception as e:
            st.error(f"Chart Error: {e}")
