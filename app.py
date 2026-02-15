import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import feedparser

# --- 1. CONFIGURATION ---
ST_WIDTH = "stretch" # New Streamlit 2026 Standard

# --- 2. GOOGLE SHEETS CONNECTION ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("Forex_User_DB").sheet1 
        return sheet
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return None

# --- 3. UPDATED GEMINI 3 LOGIC ---
def get_ai_analysis(prompt):
    keys = st.secrets["GEMINI_KEYS"]
    if "key_index" not in st.session_state:
        st.session_state.key_index = 0

    for _ in range(len(keys)):
        try:
            genai.configure(api_key=keys[st.session_state.key_index])
            # UPDATED TO GEMINI 3 FLASH (2026 Model)
            model = genai.GenerativeModel('gemini-3-flash-preview')
            response = model.generate_content(prompt)
            return response.text
        except Exception:
            st.session_state.key_index = (st.session_state.key_index + 1) % len(keys)
    return "කණගාටුයි, සියලුම AI සේවා (Gemini 3) මේ මොහොතේ කාර්යබහුලයි."

# --- 4. UI SETUP ---
st.set_page_config(page_title="Forex Pro AI 2026", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# LOGIN SCREEN
def login_screen():
    st.title("🔐 Forex Pro System Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Log In"):
        sheet = get_user_sheet()
        if sheet:
            records = sheet.get_all_records()
            user_data = next((item for item in records if item["Username"] == u), None)
            if user_data and str(user_data["Password"]) == p:
                exp_date = datetime.strptime(str(user_data["Expiry_Date"]), "%Y-%m-%d")
                if exp_date > datetime.now():
                    st.session_state.logged_in = True
                    st.session_state.user_data = user_data
                    st.rerun()
                else:
                    st.error("❌ කාලය අවසන් වී ඇත!")
            else:
                st.error("❌ දත්ත වැරදියි!")

if not st.session_state.logged_in:
    login_screen()
else:
    user = st.session_state.user_data
    
    # SIDEBAR
    st.sidebar.success(f"User: {user['Username']}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # ADMIN PANEL FIX
    if str(user.get("Role", "")).lower() == "admin":
        with st.expander("🛠️ Admin Control Panel"):
            nu = st.text_input("New User")
            np = st.text_input("New Pass")
            if st.button("Add User"):
                sheet = get_user_sheet()
                exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                sheet.append_row([nu, np, "user", exp])
                st.success("User Added!")

    # MAIN DASHBOARD
    st.title("📊 2026 Smart Money AI Dashboard")
    pair = st.sidebar.selectbox("Pair", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X"])
    df = yf.download(pair, period="60d", interval="1h")

    if not df.empty:
        # DATA HANDLING FIX FOR 2026 PANDAS
        last_c = float(df['Close'].iloc[-1])
        high_20 = float(df['High'].iloc[-20:-1].max())
        low_20 = float(df['Low'].iloc[-20:-1].min())

        struct = "Bullish 🟢" if last_c > high_20 else "Bearish 🔴" if last_c < low_20 else "Ranging ↔️"

        col1, col2 = st.columns([2, 1])
        with col1:
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, width=ST_WIDTH)
            st.info(f"Market Structure: {struct}")
            

        with col2:
            st.subheader("🤖 Gemini 3 AI Analysis")
            if st.button("Get AI Signal"):
                with st.spinner("Gemini 3 Analysis in progress..."):
                    prompt = f"Forex Pair: {pair}, Trend: {struct}, Price: {last_c}. Give a brief trade signal in Sinhala."
                    st.write(get_ai_analysis(prompt))
