import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime, timedelta
import time

# --- CONFIG & BRANDING ---
st.set_page_config(page_title="Infinite System | AI Terminal", layout="wide", page_icon="⚡")

# Custom Styles
st.markdown("""
<style>
    .live-badge { background-color: #ff5252; color: white; padding: 4px 12px; border-radius: 15px; font-size: 12px; animation: pulse 2s infinite; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    .footer { position: fixed; left: 0; bottom: 0; width: 100%; background-color: rgba(0,0,0,0.5); color: #00d4ff; text-align: center; padding: 10px; font-weight: bold; letter-spacing: 1px; }
    .stButton>button { border-radius: 8px; font-weight: bold; transition: 0.3s; }
    .stButton>button:hover { background-color: #00d4ff; color: black; border: none; }
</style>
""", unsafe_allow_html=True)

# --- AI CACHING LOGIC (2 HOURS) ---
@st.cache_data(ttl=7200)  # පැය 2ක් (7200 seconds) යනතුරු AI එක පරණ උත්තරය මතක තබා ගනී
def get_cached_ai_analysis(prompt, key_idx):
    return run_gemini(prompt, key_idx)

def run_gemini(prompt, key_idx):
    keys = st.secrets["GEMINI_KEYS"]
    try:
        genai.configure(api_key=keys[key_idx])
        model = genai.GenerativeModel('gemini-3-flash-preview')
        response = model.generate_content(prompt)
        return response.text
    except:
        return None

# --- CORE FUNCTIONS ---
def safe_float(value):
    return float(value.iloc[0]) if isinstance(value, pd.Series) else float(value)

# --- UI START ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    # (මෙහි ඔයාගේ පැරණි Login Code එක එලෙසම පවතී)
    st.title("🔐 Infinite System Login")
    # ... (Login logic)
    # පරීක්ෂණයක් සඳහා සෘජුවම Dashboard එක පෙන්වමු
    st.session_state.logged_in = True 

if st.session_state.logged_in:
    # Sidebar Branding
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2091/2091665.png", width=100)
    st.sidebar.title("INFINITE SYSTEM")
    st.sidebar.caption("Advanced AI Solutions")
    
    # Header
    c1, c2 = st.columns([4, 1])
    with c1:
        st.title("📈 Pro AI Sniper Terminal")
    with c2:
        st.markdown('<br><span class="live-badge">● LIVE ANALYZING</span>', unsafe_allow_html=True)

    # Market Inputs
    pair = st.selectbox("Select Asset", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X", "BTC-USD"])
    tf = st.select_slider("Timeframe", options=["15m", "1h", "4h"], value="1h")

    # Data Processing (Always Live)
    df = yf.download(pair, period="60d", interval=tf, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    if not df.empty:
        # Chart Analysis (Always Happens)
        last_c = safe_float(df['Close'].iloc[-1])
        high_20 = safe_float(df['High'].iloc[-20:-1].max())
        low_20 = safe_float(df['Low'].iloc[-20:-1].min())

        trend = "BULLISH 🟢" if last_c > high_20 else "BEARISH 🔴" if last_c < low_20 else "RANGING ↔️"

        col_main, col_ai = st.columns([2, 1])

        with col_main:
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            st.success(f"Market Sentiment: {trend} | Current Price: {last_c:.5f}")

        with col_ai:
            st.subheader("🤖 AI Trade Signal")
            
            # Manual Refresh Button
            force_run = st.button("🔄 Manual AI Run")
            
            prompt = f"Analyze {pair} at {last_c} with {trend} trend. Give Entry, SL, TP in Sinhala."
            
            if force_run:
                st.session_state.key_index = (st.session_state.get('key_index', 0) + 1) % len(st.secrets["GEMINI_KEYS"])
                with st.spinner("Executing Manual Analysis..."):
                    result = run_gemini(prompt, st.session_state.key_index)
                    st.session_state.manual_result = result
            
            # Show Analysis (Either Cached or Manual)
            if force_run:
                display_text = st.session_state.manual_result
            else:
                display_text = get_cached_ai_analysis(prompt, 0)
            
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px; border-left: 4px solid #00d4ff;">
                {display_text if display_text else "AI විශ්ලේෂණය සූදානම්. බොත්තම ඔබන්න."}
            </div>
            """, unsafe_allow_html=True)
            
            st.caption("💡 AI Auto-updates every 2 hours to save resources.")

    # --- FOOTER BRANDING ---
    st.markdown("""
        <div class="footer">
            Developed by INFINITE SYSTEM © 2026 | Smart AI Technology
        </div>
    """, unsafe_allow_html=True)
