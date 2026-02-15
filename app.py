import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
from google.oauth2.service_account import Credentials
import numpy as np

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

# --- TECHNICAL ANALYSIS FUNCTIONS ---
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_levels(df):
    # Simple Support & Resistance based on rolling min/max
    df['Support'] = df['Low'].rolling(window=20).min()
    df['Resistance'] = df['High'].rolling(window=20).max()
    return df

def get_fibonacci_levels(high, low):
    diff = high - low
    return {
        "0.382": high - (diff * 0.382),
        "0.5": high - (diff * 0.5),
        "0.618": high - (diff * 0.618)  # Golden Pocket
    }

# --- AI CACHING LOGIC (2 HOURS) ---
@st.cache_data(ttl=7200)
def get_cached_ai_analysis(prompt, key_idx):
    return run_gemini(prompt, key_idx)

def run_gemini(prompt, key_idx):
    keys = st.secrets["GEMINI_KEYS"]
    try:
        genai.configure(api_key=keys[key_idx])
        model = genai.GenerativeModel('gemini-2.0-flash') # Updated model for better reasoning
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Error: {str(e)}"

# --- CORE FUNCTIONS ---
def safe_float(value):
    return float(value.iloc[0]) if isinstance(value, pd.Series) else float(value)

# --- UI START ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 Infinite System Login")
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

    # Market Inputs (Updated with Crypto)
    assets = [
        "EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X", # Forex
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD" # Crypto
    ]
    pair = st.selectbox("Select Asset", assets)
    tf = st.select_slider("Timeframe", options=["15m", "1h", "4h", "1d"], value="1h")

    # Data Processing (Always Live)
    df = yf.download(pair, period="60d", interval=tf, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    if not df.empty:
        # --- ADVANCED CALCULATIONS ---
        df['RSI'] = calculate_rsi(df['Close'])
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        df = calculate_levels(df)

        last_c = safe_float(df['Close'].iloc[-1])
        last_rsi = safe_float(df['RSI'].iloc[-1])
        ema_50 = safe_float(df['EMA_50'].iloc[-1])
        ema_200 = safe_float(df['EMA_200'].iloc[-1])
        
        # Determine High/Low for structure
        recent_high = safe_float(df['High'].iloc[-30:].max())
        recent_low = safe_float(df['Low'].iloc[-30:].min())
        fibs = get_fibonacci_levels(recent_high, recent_low)

        # Basic Trend Logic
        if last_c > ema_50 and last_c > ema_200:
            trend = "STRONG BULLISH 🟢"
        elif last_c < ema_50 and last_c < ema_200:
            trend = "STRONG BEARISH 🔴"
        else:
            trend = "CONSOLIDATION / RANGING ↔️"

        col_main, col_ai = st.columns([2, 1])

        with col_main:
            # Chart with EMAs and Support/Resistance
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price")])
            
            # Add Indicators to Chart
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange', width=1), name="EMA 50"))
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(color='blue', width=1), name="EMA 200"))
            
            fig.update_layout(
                template="plotly_dark", 
                height=500, 
                xaxis_rangeslider_visible=False,
                title=f"{pair} Market Structure ({tf})"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Dashboard Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Current Price", f"{last_c:.4f}")
            m2.metric("RSI (14)", f"{last_rsi:.2f}")
            m3.metric("Fib 0.618", f"{fibs['0.618']:.4f}")
            m4.metric("Trend", trend)

        with col_ai:
            st.subheader("🤖 Smart Money AI Signal")
            
            force_run = st.button("🔄 Analyze Market Structure")
            
            # --- ADVANCED PROMPT ENGINEERING ---
            prompt = f"""
            Act as a Senior Hedge Fund Trader and Technical Analyst. Analyze {pair} on the {tf} timeframe.
            Output must be in SINHALA language (Sinhala font).

            **Real-Time Data:**
            - Current Price: {last_c}
            - Trend Status: {trend}
            - RSI(14): {last_rsi}
            - EMA 50: {ema_50} | EMA 200: {ema_200}
            - Recent High: {recent_high} | Recent Low: {recent_low}
            - Golden Pocket (Fib 0.618): {fibs['0.618']}

            **Analysis Requirements (MUST COVER):**
            1. **SMC & ICT Concepts:** Identify Order Blocks, Fair Value Gaps (FVG), and Liquidity Sweeps (Sell-side/Buy-side liquidity).
            2. **Structure:** Is there a Break of Structure (BOS) or Change of Character (CHoCH)?
            3. **Retail vs Smart Money:** What are retail traders doing vs what banks are likely doing?
            4. **Patterns:** Check for Chart Patterns (Head & Shoulders, Flags, Triangles).
            5. **Key Levels:** Use the Fib 0.618 and Support/Resistance logic.

            **Final Output:**
            - Provide a clear **BUY**, **SELL**, or **WAIT** signal.
            - **Entry Price:** (Best zone to enter).
            - **Stop Loss (SL):** (Based on invalidation point).
            - **Take Profit (TP):** (Based on liquidity pools).
            - Explain the reasoning briefly in Sinhala using technical terms like 'Liquidity Grab', 'Mitigation', etc.
            """
            
            if force_run:
                st.session_state.key_index = (st.session_state.get('key_index', 0) + 1) % len(st.secrets["GEMINI_KEYS"])
                with st.spinner("Analyzing Liquidity & Order Blocks..."):
                    result = run_gemini(prompt, st.session_state.key_index)
                    st.session_state.manual_result = result
            
            # Show Analysis
            if force_run:
                display_text = st.session_state.manual_result
            else:
                display_text = get_cached_ai_analysis(prompt, 0)
            
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px; border-left: 4px solid #00d4ff; font-size: 14px;">
                {display_text if display_text else "SMC Analysis සූදානම්. බොත්තම ඔබන්න."}
            </div>
            """, unsafe_allow_html=True)
            
            st.caption("💡 Scanning for Order Blocks & Liquidity Pools...")

    # --- FOOTER BRANDING ---
    st.markdown("""
        <div class="footer">
            Developed by INFINITE SYSTEM © 2026 | SMC & ICT AI Technology
        </div>
    """, unsafe_allow_html=True)
