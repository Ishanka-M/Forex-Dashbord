import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time
import re
import requests
import numpy as np

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System v6.0 | Gemini 3 Ultra", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    .price-up { color: #00ff00; font-size: 22px; font-weight: bold; }
    .price-down { color: #ff4b4b; font-size: 22px; font-weight: bold; }
    .entry-box { background: rgba(0, 212, 255, 0.07); border: 2px solid #00d4ff; padding: 20px; border-radius: 12px; margin-top: 10px; box-shadow: 0 4px 15px rgba(0,212,255,0.1); color: white; }
    .insight-box { background: #12141a; border-left: 4px solid #f39c12; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 14px; }
    .sig-box { padding: 10px; border-radius: 6px; font-size: 13px; text-align: center; font-weight: bold; border: 1px solid #444; margin-bottom: 5px; }
    .bull { background-color: #004d40; color: #00ff00; border-color: #00ff00; }
    .bear { background-color: #4a1414; color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background-color: #262626; color: #888; }
    .footer { text-align: center; font-size: 12px; color: #666; margin-top: 20px; }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State (FIX FOR ATTRIBUTE ERROR) ---
if "logged_in" not in st.session_state: 
    st.session_state.logged_in = False
if "active_provider" not in st.session_state: 
    st.session_state.active_provider = "Waiting for analysis..."

# --- 2. USER MANAGEMENT SYSTEM ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        return gspread.authorize(creds).open("Forex_User_DB").sheet1
    except Exception as e:
        st.error(f"Database Error: {e}")
        return None

def check_login(username, password):
    if username == "admin" and password == "admin123":
        return {"Username": "Admin", "Role": "Admin"}
    sheet = get_user_sheet()
    if sheet:
        try:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i["Username"]) == username), None)
            if user and str(user["Password"]) == password:
                return user
        except: return None
    return None

def create_user(new_username, new_password):
    sheet = get_user_sheet()
    if sheet:
        try:
            existing_users = sheet.col_values(1)
            if new_username in existing_users:
                return False, "User already exists!"
            sheet.append_row([new_username, new_password, "User", str(datetime.now())])
            return True, "User created successfully!"
        except Exception as e:
            return False, f"Error: {e}"
    return False, "Database Connection Failed"

# --- 3. ALPHA VANTAGE DATA ENGINE ---
def get_alpha_vantage_data(pair):
    if "ALPHA_VANTAGE_KEY" not in st.secrets:
        return "API Key Missing"
    try:
        if "=X" in pair:
            base, quote = pair[:3], pair[3:6]
            url = f'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={base}&to_currency={quote}&apikey={st.secrets["ALPHA_VANTAGE_KEY"]}'
        else:
            base = pair.split("-")[0]
            url = f'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={base}&to_currency=USD&apikey={st.secrets["ALPHA_VANTAGE_KEY"]}'
        r = requests.get(url, timeout=10)
        data = r.json()
        return data.get("Realtime Currency Exchange Rate", "No data available")
    except Exception as e:
        return f"Conn Error: {e}"

# --- 4. ADVANCED SIGNAL ENGINE ---
def calculate_advanced_signals(df):
    signals = {}
    c, h, l = df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    signals['ICT'] = ("Bullish FVG", "bull") if df['Low'].iloc[-1] > df['High'].iloc[-3] else (("Bearish FVG", "bear") if df['High'].iloc[-1] < df['Low'].iloc[-3] else ("No FVG", "neutral"))
    
    period_high, period_low = df['High'].rolling(50).max().iloc[-1], df['Low'].rolling(50).min().iloc[-1]
    fib_618 = period_high - ((period_high - period_low) * 0.618)
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.0005) else ("Ranging", "neutral")
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
    signals['RETAIL'] = ("Overbought", "bear") if rsi > 70 else (("Oversold", "bull") if rsi < 30 else (f"Neutral ({int(rsi)})", "neutral"))
    
    signals['LIQ'] = ("Liquidity Grab (L)", "bull") if l < df['Low'].iloc[-10:-1].min() else (("Liquidity Grab (H)", "bear") if h > df['High'].iloc[-10:-1].max() else ("Holding", "neutral"))
    signals['TREND'] = ("Uptrend", "bull") if c > df['Close'].rolling(50).mean().iloc[-1] else ("Downtrend", "bear")
    
    score = (1 if signals['SMC'][1] == "bull" else -1) + (1 if signals['TREND'][1] == "bull" else -1)
    signals['SK'] = ("SK Sniper Buy", "bull") if score >= 1 else (("SK Sniper Sell", "bear") if score <= -1 else ("Waiting", "neutral"))
    signals['PATT'] = ("Engulfing", "bull") if (df['Close'].iloc[-1] > df['Open'].iloc[-1] and df['Close'].iloc[-1] > df['Open'].iloc[-2]) else ("None", "neutral")
    
    return signals

# --- 5. AI ENGINE (UPDATED TO GEMINI 3 FLASH PREVIEW) ---
def get_ai_analysis(prompt, asset_data):
    if "GEMINI_KEYS" in st.secrets:
        for i, key in enumerate(st.secrets["GEMINI_KEYS"]):
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel('gemini-3-flash-preview')
                response = model.generate_content(prompt)
                if response and response.text:
                    return response.text, f"Gemini 3 Flash (Key #{i+1})"
            except: continue

    if "HF_TOKEN" in st.secrets:
        try:
            api_url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
            headers = {"Authorization": f"Bearer {st.secrets['HF_TOKEN']}"}
            payload = {"inputs": f"<s>[INST] {prompt} [/INST]", "parameters": {"max_new_tokens": 400}}
            res = requests.post(api_url, headers=headers, json=payload, timeout=15)
            if res.status_code == 200:
                output = res.json()[0]['generated_text']
                return output.split("[/INST]")[-1].strip(), "Mistral AI (HF)"
        except: pass

    sl, tp = asset_data['price'] * 0.995, asset_data['price'] * 1.01
    return f"ENTRY: {asset_data['price']}\nSL: {sl:.4f}\nTP: {tp:.4f}\n\n⚠️ AI PROVIDER ERROR: Manual calculation applied.", "Offline"

# --- 6. MAIN APPLICATION ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>⚡ INFINITE SYSTEM TERMINAL v6.0</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login_form"):
            u, p = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Access Terminal"):
                user = check_login(u, p)
                if user:
                    st.session_state.logged_in, st.session_state.user = True, user
                    st.rerun()
                else: st.error("Invalid Credentials")

else:
    user_info = st.session_state.get('user', {})
    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    
    if user_info.get('Role') == "Admin":
        with st.sidebar.expander("🛠 Admin Control Panel"):
            with st.form("create_user"):
                nu, npwd = st.text_input("New User"), st.text_input("New Pwd", type="password")
                if st.form_submit_button("Create User"):
                    s, m = create_user(nu, npwd)
                    st.success(m) if s else st.error(m)

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    st.sidebar.divider()
    market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
    assets = {"Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"], "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD"], "Metals": ["XAUUSD=X"]}
    pair = st.sidebar.selectbox("Select Asset", assets[market])
    tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h"], index=2)
    live = st.sidebar.checkbox("🔴 Real-time Refresh", value=True)

    df = yf.download(pair, period="5d", interval=tf, progress=False)
    
    if not df.empty:
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        curr_p = float(df['Close'].iloc[-1])
        st.title(f"{pair} Market Terminal - {curr_p:.5f}")

        with st.expander("📊 Alpha Vantage Live Order Flow", expanded=True):
            av_data = get_alpha_vantage_data(pair)
            if isinstance(av_data, dict):
                col1, col2, col3 = st.columns(3)
                col1.metric("Exchange Rate", av_data.get("5. Exchange Rate", "N/A"))
                col2.metric("Real-time Bid", av_data.get("8. Bid Price", "N/A"))
                col3.metric("Real-time Ask", av_data.get("9. Ask Price", "N/A"))
                st.caption(f"Last Sync: {av_data.get('6. Last Refreshed', 'N/A')} UTC")
            else:
                st.info(f"AV Insights: {av_data}")

        sigs = calculate_advanced_signals(df)
        cols = st.columns(4)
        keys = list(sigs.keys())
        for i in range(4):
            cols[i].markdown(f"<div class='sig-box {sigs[keys[i]][1]}'>{keys[i]}: {sigs[keys[i]][0]}</div>", unsafe_allow_html=True)
            cols[i].markdown(f"<div class='sig-box {sigs[keys[i+4]][1]}'>{keys[i+4]}: {sigs[keys[i+4]][0]}</div>", unsafe_allow_html=True)

        st.plotly_chart(go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])]).update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=20, b=20)), use_container_width=True)

        st.divider()
        c_ai, c_res = st.columns([1, 2])
        with c_ai:
            st.subheader("🚀 AI Sniper Analysis")
            if st.button("Generate Gemini 3 Insight", use_container_width=True):
                with st.spinner("Gemini 3 Flash analyzing market structure..."):
                    prompt = f"""
                    Analyze {pair} at {curr_p} on {tf} timeframe.
                    Technical Signals:
                    - SMC: {sigs['SMC'][0]}
                    - Trend: {sigs['TREND'][0]}
                    - RSI Sentiment: {sigs['RETAIL'][0]}
                    - Liquidity: {sigs['LIQ'][0]}
                    
                    Provide a professional trading signal in Sinhala.
                    Include:
                    1. Entry Price
                    2. Stop Loss (SL)
                    3. Take Profit (TP)
                    4. Brief reasoning for the trade.
                    """
                    result, provider = get_ai_analysis(prompt, {'price': curr_p})
                    st.session_state.ai_result = result
                    st.session_state.active_provider = provider
                    st.toast(f"Powered by: {provider}")

        with c_res:
            if "ai_result" in st.session_state:
                # SAFE ACCESS TO SESSION STATE
                st.markdown(f"**AI Provider:** `{st.session_state.get('active_provider', 'Unknown')}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    if live:
        time.sleep(60)
        st.rerun()
