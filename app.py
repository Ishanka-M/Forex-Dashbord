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

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System | Pro AI Terminal", layout="wide")

st.markdown("""
<style>
    .price-up { color: #00ff00; font-size: 24px; font-weight: bold; animation: fadein 0.5s; }
    .price-down { color: #ff0000; font-size: 24px; font-weight: bold; animation: fadein 0.5s; }
    .footer { position: fixed; bottom: 0; width: 100%; text-align: center; color: #00d4ff; padding: 10px; background: rgba(0,0,0,0.8); }
    .entry-box { background: rgba(0, 212, 255, 0.1); border: 1px solid #00d4ff; padding: 15px; border-radius: 10px; }
    @keyframes fadein { from { opacity: 0; } to { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

# --- 2. DATABASE & AI FUNCTIONS ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open("Forex_User_DB").sheet1 
    except: return None

@st.cache_data(ttl=7200)
def get_ai_analysis(prompt):
    keys = st.secrets["GEMINI_KEYS"]
    genai.configure(api_key=keys[0])
    model = genai.GenerativeModel('gemini-3-flash-preview')
    response = model.generate_content(prompt)
    return response.text

def safe_float(value):
    return float(value.iloc[0]) if isinstance(value, pd.Series) else float(value)

# --- 3. SESSION STATE ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "last_price" not in st.session_state: st.session_state.last_price = 0.0

# --- 4. LOGIN & ADMIN LOGIC ---
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
                exp = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                sheet.append_row([new_u, new_p, "user", exp])
                st.success(f"User {new_u} added!")

    # --- 5. REAL-TIME DATA ---
    pair = st.sidebar.selectbox("Pair", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X", "BTC-USD"])
    df = yf.download(pair, period="2d", interval="1m", progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        curr_price = safe_float(df['Close'].iloc[-1])
        
        # Price Update Animation Logic
        price_class = "price-up" if curr_price >= st.session_state.last_price else "price-down"
        st.session_state.last_price = curr_price

        c1, c2, c3 = st.columns([2,1,1])
        with c1:
            st.title(f"📊 {pair}")
        with c2:
            st.markdown(f"LIVE PRICE:<br><span class='{price_class}'>{curr_price:.5f}</span>", unsafe_allow_html=True)
        with c3:
            if st.button("🔄 Refresh"): st.rerun()

        # AI & Analysis
        col_chart, col_signal = st.columns([2, 1])
        
        with col_chart:
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            

        with col_signal:
            st.subheader("🎯 Sniper Entry Control")
            
            # AI Logic
            prompt = f"Give a trade signal for {pair} at {curr_price}. Format: ENTRY: (price), SL: (price), TP: (price). In Sinhala."
            analysis = get_ai_analysis(prompt)
            st.markdown(f"<div class='entry-box'>{analysis}</div>", unsafe_allow_html=True)
            
            # --- PROGRESS BAR LOGIC ---
            # AI එකෙන් දෙන Entry Price එක අංකයක් විදිහට වෙන් කර ගැනීම
            try:
                entry_match = re.search(r"ENTRY:\s*([\d.]+)", analysis)
                if entry_match:
                    entry_price = float(entry_match.group(1))
                    diff = abs(curr_price - entry_price)
                    # පරාසය 0.00500 ඇතුළත නම් progress පෙන්වන්න
                    progress = max(0.0, min(1.0, 1.0 - (diff / 0.0050))) 
                    
                    st.write(f"Distance to Entry: {diff:.5f}")
                    st.progress(progress)
                    
                    if diff < 0.0001:
                        st.toast("🚀 ENTRY POINT REACHED! ENTER NOW!", icon="🔥")
                        st.balloons()
            except: pass

            if st.button("Manual AI Sync"):
                st.cache_data.clear()
                st.rerun()

    # Footer
    st.markdown('<div class="footer">Developed by INFINITE SYSTEM © 2026</div>', unsafe_allow_html=True)
