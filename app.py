import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import feedparser

# --- 1. GOOGLE SHEETS සම්බන්ධතාවය ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("Forex_User_DB").sheet1 
        return sheet
    except Exception as e:
        st.error(f"Database දෝෂය: {e}")
        return None

# --- 2. GEMINI KEY ROTATION LOGIC ---
def get_ai_analysis(prompt):
    keys = st.secrets["GEMINI_KEYS"]
    if "key_index" not in st.session_state:
        st.session_state.key_index = 0

    for _ in range(len(keys)):
        try:
            genai.configure(api_key=keys[st.session_state.key_index])
            # අලුත්ම model එක භාවිතා කරමු
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text
        except Exception:
            st.session_state.key_index = (st.session_state.key_index + 1) % len(keys)
    return "කණගාටුයි, සියලුම AI සේවා මේ මොහොතේ කාර්යබහුලයි. පසුව උත්සාහ කරන්න."

# --- 3. UI සැකසුම් ---
st.set_page_config(page_title="Forex Pro Sinhala AI", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# LOGIN තිරය
def login_screen():
    st.title("🔐 Forex Pro පද්ධතියට ඇතුල් වන්න")
    user_input = st.text_input("Username")
    pass_input = st.text_input("Password", type="password")
    if st.button("Log In"):
        sheet = get_user_sheet()
        if sheet:
            records = sheet.get_all_records()
            user_data = next((item for item in records if item["Username"] == user_input), None)
            if user_data and str(user_data["Password"]) == pass_input:
                expiry_date = datetime.strptime(str(user_data["Expiry_Date"]), "%Y-%m-%d")
                if expiry_date > datetime.now():
                    st.session_state.logged_in = True
                    st.session_state.user_data = user_data
                    st.rerun()
                else:
                    st.error("❌ ඔබේ පැකේජය අවසන් වී ඇත!")
            else:
                st.error("❌ වැරදි තොරතුරු!")

if not st.session_state.logged_in:
    login_screen()
else:
    user = st.session_state.user_data
    # Sidebar
    st.sidebar.title(f"ආයුබෝවන්, {user['Username']}!")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # Trading Dashboard
    st.title("📊 SMC + SK AI Trading Dashboard")
    pair = st.sidebar.selectbox("මුදල් යුගලය", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X"])
    tf = st.sidebar.selectbox("කාලරාමුව", ["15m", "1h", "4h"])

    df = yf.download(pair, period="60d", interval=tf)
    
    if not df.empty:
        # --- FUTUREWARNINGS නිවැරදි කිරීම ---
        # iloc[0] හෝ scalar අගයක් ලෙස ගැනීමෙන් warnings ඉවත් වේ
        last_c = float(df['Close'].iloc[-1].iloc[0] if isinstance(df['Close'].iloc[-1], pd.Series) else df['Close'].iloc[-1])
        
        max_val = df['High'].iloc[-20:-1].max()
        prev_h = float(max_val.iloc[0] if hasattr(max_val, 'iloc') else max_val)
        
        min_val = df['Low'].iloc[-20:-1].min()
        prev_l = float(min_val.iloc[0] if hasattr(min_val, 'iloc') else min_val)
        
        if last_c > prev_h:
            struct = "Bullish (ඉහළට) 🟢"
        elif last_c < prev_l:
            struct = "Bearish (පහළට) 🔴"
        else:
            struct = "Ranging ↔️"

        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader(f"📈 {pair} Chart")
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            # අලුත්ම Streamlit version එකට ගැලපෙන ලෙස width සැකසීම
            fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, width='stretch') 
            st.write(f"Trend: **{struct}**")
            

        with col2:
            st.subheader("🤖 AI පුවත් විශ්ලේෂණය")
            if st.button("AI Analyze"):
                with st.spinner("AI අධ්‍යයනය කරමින්..."):
                    feed = feedparser.parse("https://www.forexfactory.com/ff_calendar_thisweek.xml")
                    news_summary = "\n".join([e.title for e in feed.entries[:5]])
                    prompt = f"Analyze Forex news: {news_summary}. Trend: {struct}. Advice in Sinhala."
                    st.info(get_ai_analysis(prompt))
            
            st.divider()
            high_all = df['High'].max()
            low_all = df['Low'].min()
            h_val = float(high_all.iloc[0] if hasattr(high_all, 'iloc') else high_all)
            l_val = float(low_all.iloc[0] if hasattr(low_all, 'iloc') else low_all)
            fib_618 = l_val + (h_val - l_val) * 0.618
            st.write(f"🎯 SK Discount (0.618): **{fib_618:.5f}**")
