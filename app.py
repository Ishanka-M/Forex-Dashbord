ඔබ ඉල්ලූ පරිදි, **Gemini 2.0 Flash (New Generation)** මුලික කරගෙන, එය අසාර්ථක වුවහොත් **Puter AI** වෙත මාරු වන ලෙසත්, **Retail & SK System** තියරි වැඩිදියුණු කර, **Market Scanner** එක Scalp සහ Swing ලෙස වෙන් කර පෙන්වන ලෙසත් Code එක යාවත්කාලීන කර ඇත.

පහත දැක්වෙන්නේ සම්පූර්ණ යාවත්කාලීන Code එකයි.

**(සැලකිය යුතුයි: මෙම Code එක ක්‍රියාත්මක කිරීමට ඔබේ Streamlit Secrets (`.streamlit/secrets.toml`) හි `GEMINI_API_KEY` එකතු කළ යුතුය. නැතහොත් Puter AI පමණක් වැඩ කරනු ඇත.)**

```python
import streamlit as st
import yfinance as yf
import pandas as pd
import puter  # Puter AI for Fallback
import google.generativeai as genai # Gemini AI
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, time as dt_time
import time
import re
import numpy as np
import requests
import xml.etree.ElementTree as ET

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System v10.0 Ultra | Hybrid", layout="wide", page_icon="⚡")

# --- GEMINI SETUP ---
# Secrets file එකේ GEMINI_API_KEY තිබිය යුතුය. නැතිනම් Puter පමණක් වැඩ කරයි.
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

st.markdown("""
<style>
    .price-up { color: #00ff00; font-size: 22px; font-weight: bold; }
    .price-down { color: #ff4b4b; font-size: 22px; font-weight: bold; }
    .entry-box { background: rgba(0, 212, 255, 0.07); border: 2px solid #00d4ff; padding: 15px; border-radius: 12px; margin-top: 10px; color: white; }
    
    .trade-metric { background: #222; border: 1px solid #444; border-radius: 8px; padding: 10px; text-align: center; }
    .trade-metric h4 { margin: 0; color: #aaa; font-size: 14px; }
    .trade-metric h2 { margin: 5px 0 0 0; color: #fff; font-size: 20px; font-weight: bold; }
    
    .news-card { background: #1e1e1e; padding: 10px; margin-bottom: 8px; border-radius: 5px; }
    .news-positive { border-left: 4px solid #00ff00; }
    .news-negative { border-left: 4px solid #ff4b4b; }
    .news-neutral { border-left: 4px solid #00d4ff; }
    
    .sig-box { padding: 10px; border-radius: 6px; font-size: 12px; text-align: center; font-weight: bold; border: 1px solid #444; margin-bottom: 5px; }
    .bull { background-color: #004d40; color: #00ff00; border-color: #00ff00; }
    .bear { background-color: #4a1414; color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background-color: #262626; color: #888; }

    /* Notification Styling */
    .notif-container { padding: 15px; border-radius: 10px; margin-bottom: 20px; border-left: 10px solid; background: #121212; }
    .notif-buy { border-color: #00ff00; color: #00ff00; box-shadow: 0 0 15px rgba(0, 255, 0, 0.2); }
    .notif-sell { border-color: #ff4b4b; color: #ff4b4b; box-shadow: 0 0 15px rgba(255, 75, 75, 0.2); }
    .notif-wait { border-color: #555; color: #aaa; }
    
    /* Chat Styling */
    .chat-msg { padding: 8px; border-radius: 5px; margin-bottom: 5px; background: #333; }
    .chat-user { font-weight: bold; color: #00d4ff; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "active_provider" not in st.session_state: st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# --- Helper Functions (DB & Auth) ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        try: sheet = client.open("Forex_User_DB").sheet1
        except: sheet = None
        return sheet, None
    except: return None, None

def check_login(username, password):
    if username == "admin" and password == "admin123": 
        return {"Username": "Admin", "Role": "Admin", "HybridLimit": 9999, "UsageCount": 0}
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i.get("Username")) == username), None)
            if user and str(user.get("Password")) == password:
                if "HybridLimit" not in user: user["HybridLimit"] = 10
                if "UsageCount" not in user: user["UsageCount"] = 0
            return user
        except: return None
    return None

def update_usage_in_db(username, new_usage):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell:
                headers = sheet.row_values(1)
                if "UsageCount" in headers:
                    col_idx = headers.index("UsageCount") + 1
                    sheet.update_cell(cell.row, col_idx, new_usage)
        except Exception as e:
            print(f"DB Update Error: {e}")

# --- ADMIN ADD USER FUNCTION ---
def add_new_user(username, password, role, limit):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            existing = sheet.find(username)
            if existing: return False, "Username already exists."
            sheet.append_row([username, password, role, limit, 0])
            return True, "User created successfully!"
        except Exception as e: return False, f"Error: {e}"
    return False, "Database connection failed."

def get_sentiment_class(title):
    title_lower = title.lower()
    negative_words = ['crash', 'drop', 'fall', 'plunge', 'loss', 'down', 'bear', 'weak', 'inflation', 'war', 'crisis', 'retreat', 'slump']
    positive_words = ['surge', 'rise', 'jump', 'gain', 'bull', 'up', 'strong', 'growth', 'profit', 'record', 'soar', 'rally', 'beat']
    if any(word in title_lower for word in negative_words): return "news-negative"
    elif any(word in title_lower for word in positive_words): return "news-positive"
    else: return "news-neutral"

def get_market_news(symbol):
    news_list = []
    clean_sym = symbol.replace("=X", "").replace("-USD", "")
    try:
        url = f"https://news.google.com/rss/search?q={clean_sym}+forex+market&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for item in root.findall('.//item')[:3]:
                news_list.append({
                    "title": item.find('title').text,
                    "link": item.find('link').text
                })
            if news_list: return news_list
    except: pass
    return []

def get_data_period(tf):
    if tf in ["1m", "5m"]: return "5d"
    elif tf == "15m": return "1mo"
    elif tf == "1h": return "6mo"
    elif tf == "4h": return "1y"
    return "1mo"

# --- 4. ADVANCED SIGNAL ENGINE (SCALP VS SWING AWARE) ---
# --- Updated with RETAIL & SK SYSTEM Theory ---
def calculate_advanced_signals(df, tf):
    if len(df) < 50: return None, 0
    signals = {}
    c, h, l = df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    
    # -- Dynamic Moving Averages --
    if tf in ["1m", "5m"]:
        ma_short = df['Close'].rolling(9).mean().iloc[-1]
        ma_long = df['Close'].rolling(21).mean().iloc[-1]
        trend_label = "Scalp Trend"
    else:
        ma_short = df['Close'].rolling(50).mean().iloc[-1]
        ma_long = df['Close'].rolling(200).mean().iloc[-1]
        trend_label = "Swing Trend"

    # 1. SMC (Structure & Order Blocks)
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    
    # 2. ICT (Fair Value Gaps & Silver Bullet Logic)
    # Simple FVG Check
    fvg_bull = df['Low'].iloc[-1] > df['High'].iloc[-3]
    fvg_bear = df['High'].iloc[-1] < df['Low'].iloc[-3]
    
    signals['ICT'] = ("Bullish FVG", "bull") if fvg_bull else (("Bearish FVG", "bear") if fvg_bear else ("No FVG", "neutral"))
    
    # 3. RETAIL SYSTEM (Support/Resistance & Pattern)
    # Retail Logic: Support becomes Resistance and vice versa.
    pivot_high = df['High'].rolling(20).max().iloc[-1]
    pivot_low = df['Low'].rolling(20).min().iloc[-1]
    
    retail_status = "Ranging"
    retail_col = "neutral"
    
    if abs(c - pivot_low) < (c * 0.0005): # Near Support
        retail_status, retail_col = "Supp Zone Test", "bull"
    elif abs(c - pivot_high) < (c * 0.0005): # Near Resistance
        retail_status, retail_col = "Res Zone Test", "bear"
    elif c > pivot_high:
        retail_status, retail_col = "Breakout Buy", "bull"
    elif c < pivot_low:
        retail_status, retail_col = "Breakdown Sell", "bear"
        
    signals['RETAIL_SYS'] = (retail_status, retail_col)

    # 4. RSI (Momentum)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
    signals['RSI'] = ("Overbought", "bear") if rsi_val > 70 else (("Oversold", "bull") if rsi_val < 30 else (f"Neutral ({int(rsi_val)})", "neutral"))

    # 5. LIQUIDITY
    signals['LIQ'] = ("Liquidity Sweep (L)", "bull") if l < df['Low'].iloc[-10:-1].min() else (("Liquidity Sweep (H)", "bear") if h > df['High'].iloc[-10:-1].max() else ("Holding", "neutral"))

    # 6. TREND 
    trend_direction = "bull" if c > ma_short else "bear"
    signals['TREND'] = (f"{trend_label} {trend_direction.upper()}", trend_direction)
    
    # 7. ELLIOTT WAVE (Simplified)
    ema_20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    if c > ma_short:
        ew_status = "Impulse (Wave 3)" if c > ema_20 else "Correction (Wave 4)"
        ew_col = "bull" if c > ema_20 else "neutral"
    else:
        ew_status = "Impulse (Wave C)" if c < ema_20 else "Correction (Wave B)"
        ew_col = "bear" if c < ema_20 else "neutral"
    signals['ELLIOTT'] = (ew_status, ew_col)

    # 8. SK SYSTEM SCORE (Custom Weighted Logic)
    # SK System prioritizes Trend + Structure + Momentum
    sk_score = 0
    # Trend Confluence
    if signals['TREND'][1] == "bull": sk_score += 2
    elif signals['TREND'][1] == "bear": sk_score -= 2
    
    # SMC Validation
    if signals['SMC'][1] == "bull": sk_score += 1.5
    elif signals['SMC'][1] == "bear": sk_score -= 1.5
    
    # Retail Support/Res Validation
    if signals['RETAIL_SYS'][1] == "bull": sk_score += 1
    elif signals['RETAIL_SYS'][1] == "bear": sk_score -= 1
    
    # RSI Filter (Avoid trading against extremes unless reversal)
    if signals['RSI'][1] == "bull": sk_score += 0.5 # Buying at oversold
    elif signals['RSI'][1] == "bear": sk_score -= 0.5 # Selling at overbought

    signals['SK'] = ("SK PRIME BUY", "bull") if sk_score >= 3.5 else (("SK PRIME SELL", "bear") if sk_score <= -3.5 else ("No Setup", "neutral"))
    
    atr = (df['High']-df['Low']).rolling(14).mean().iloc[-1]
    return signals, atr, sk_score

# --- 5. INFINITE ALGORITHMIC ENGINE V3.5 ---
def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr, tf):
    news_score = 0
    for item in news_items:
        sentiment = get_sentiment_class(item['title'])
        if sentiment == "news-positive": news_score += 1
        elif sentiment == "news-negative": news_score -= 1
    
    trend = sigs['TREND'][0]
    smc = sigs['SMC'][0]
    sk_signal = sigs['SK'][1]
    
    if tf in ["1m", "5m"]:
        trade_mode = "SCALPING (වේගවත්)"
        sl_mult = 1.2
        tp_mult = 2.0
    else:
        trade_mode = "SWING (දිගු කාලීන)"
        sl_mult = 1.5
        tp_mult = 3.5

    if sk_signal == "bull" and news_score >= -1:
        action = "BUY"
        note = f"SK System සහ Retail Support මගින් තහවුරු විය. Trend: {trend}"
        sl, tp = curr_p - (atr * sl_mult), curr_p + (atr * tp_mult)
    elif sk_signal == "bear" and news_score <= 1:
        action = "SELL"
        note = f"SK System සහ Retail Resistance මගින් තහවුරු විය. Trend: {trend}"
        sl, tp = curr_p + (atr * sl_mult), curr_p - (atr * tp_mult)
    else:
        action = "WAIT"
        note = "SK System අනුමැතිය නොමැත."
        sl, tp = curr_p - atr, curr_p + atr

    analysis_text = f"""
    ♾️ **INFINITE ALGO ENGINE V10 (RETAIL + SK)**
    
    📊 **Setup ({tf}):**
    • Mode: {trade_mode}
    • Action: {action}
    • SMC: {smc} | Retail: {sigs['RETAIL_SYS'][0]}
    
    💡 **SK Logic:**
    {note}
    
    DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}
    """
    return analysis_text

# --- 6. HYBRID AI ENGINE (GEMINI FIRST -> PUTER FALLBACK) ---
def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info, tf):
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr, tf)
    
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 10)
    
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return algo_result, "Infinite Algo (Limit Reached)"

    # Prompt Engineering for Swing Bias
    prompt = f"""
    Act as a Senior Hedge Fund Trader (SK System Expert).
    Analyze this trade for {pair} on {tf} timeframe.
    
    Current Algo Output: {algo_result}
    Technical Data:
    - Trend: {sigs['TREND'][0]}
    - SMC Structure: {sigs['SMC'][0]}
    - RSI: {sigs['RSI'][0]}
    - Retail Level: {sigs['RETAIL_SYS'][0]}
    
    Instructions:
    1. Prioritize LONG TERM SUSTAINABILITY (Swing) even on lower TFs.
    2. Check if 'Retail' traders are trapped (Liquidity Grabs).
    3. Validate using 'SK System' logic (Trend + Momentum confluence).
    4. Verify Entry, SL, TP.
    5. Explain in Sinhala (Technical terms in English).
    6. FINAL FORMAT MUST BE: DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx
    """

    provider_name = "Unknown"
    response_text = ""

    try:
        # Animation
        with st.status(f"🚀 Infinite AI Activating ({tf})...", expanded=True) as status:
            st.write("📡 Contacting Gemini 2.0 Flash...")
            
            # --- ATTEMPT 1: GEMINI 2.0 FLASH ---
            try:
                model = genai.GenerativeModel('gemini-2.0-flash') # Using latest Flash model
                response = model.generate_content(prompt)
                response_text = response.text
                provider_name = "Gemini 2.0 Flash ⚡"
                status.update(label="✅ Gemini Analysis Complete!", state="complete", expanded=False)
            
            except Exception as e_gemini:
                # --- ATTEMPT 2: FALLBACK TO PUTER ---
                st.write(f"⚠️ Gemini Busy/Error. Switching to Puter AI... ({e_gemini})")
                time.sleep(1)
                try:
                    puter_resp = puter.ai.chat(prompt)
                    response_text = puter_resp.message.content
                    provider_name = "Puter AI (Fallback) 🔵"
                    status.update(label="✅ Puter Analysis Complete!", state="complete", expanded=False)
                except Exception as e_puter:
                    st.error(f"All AI Services Failed. Using Algo. {e_puter}")
                    return algo_result, "Infinite Algo (Fallback)"

        if response_text:
            new_usage = current_usage + 1
            user_info["UsageCount"] = new_usage
            st.session_state.user = user_info 
            if user_info["Username"] != "Admin":
                update_usage_in_db(user_info["Username"], new_usage)
            return response_text, f"{provider_name} | Used: {new_usage}/{max_limit}"
            
    except Exception as e:
        return algo_result, "Infinite Algo (Error)"
    
    return algo_result, "Infinite Algo (Default)"

def parse_ai_response(text):
    data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
    try:
        entry_match = re.search(r"ENTRY\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        sl_match = re.search(r"SL\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        tp_match = re.search(r"TP\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        if entry_match: data["ENTRY"] = entry_match.group(1)
        if sl_match: data["SL"] = sl_match.group(1)
        if tp_match: data["TP"] = tp_match.group(1)
    except: pass
    return data

# --- SCANNER FUNCTION (SPLIT SCALP & SWING) ---
def scan_market(assets_list):
    scalp_results = []
    swing_results = []
    
    progress_bar = st.progress(0)
    total = len(assets_list) * 2 # Scans both TFs
    step = 0
    
    for symbol in assets_list:
        # 1. SCALP SCAN (5m)
        try:
            df_scalp = yf.download(symbol, period="5d", interval="5m", progress=False)
            if not df_scalp.empty and len(df_scalp) > 50:
                if isinstance(df_scalp.columns, pd.MultiIndex): df_scalp.columns = df_scalp.columns.get_level_values(0)
                sigs_sc, _, score_sc = calculate_advanced_signals(df_scalp, "5m")
                if abs(score_sc) >= 3: # Only high probability scalps
                    scalp_results.append({
                        "Pair": symbol.replace("=X","").replace("-USD",""),
                        "Signal": sigs_sc['SK'][0],
                        "Trend": sigs_sc['TREND'][0],
                        "Score": score_sc,
                        "Price": df_scalp['Close'].iloc[-1]
                    })
        except: pass
        step += 1
        progress_bar.progress(step / total)

        # 2. SWING SCAN (4h)
        try:
            df_swing = yf.download(symbol, period="6mo", interval="4h", progress=False)
            if not df_swing.empty and len(df_swing) > 50:
                if isinstance(df_swing.columns, pd.MultiIndex): df_swing.columns = df_swing.columns.get_level_values(0)
                sigs_sw, _, score_sw = calculate_advanced_signals(df_swing, "4h")
                if abs(score_sw) >= 2.5: # Swing needs solid structure
                    swing_results.append({
                        "Pair": symbol.replace("=X","").replace("-USD",""),
                        "Signal": sigs_sw['SK'][0],
                        "Trend": sigs_sw['TREND'][0],
                        "Score": score_sw,
                        "Price": df_swing['Close'].iloc[-1]
                    })
        except: pass
        step += 1
        progress_bar.progress(step / total)
    
    progress_bar.empty()
    return sorted(scalp_results, key=lambda x: abs(x['Score']), reverse=True), sorted(swing_results, key=lambda x: abs(x['Score']), reverse=True)

# --- 7. MAIN APPLICATION ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>⚡ INFINITE SYSTEM v10.0 ULTRA</h1>", unsafe_allow_html=True)
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
    
    # --- SIDEBAR ---
    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    st.sidebar.caption(f"Engine: Gemini 2.0 Flash + Puter")
    
    # --- AUTO REFRESH OPTION ---
    auto_refresh = st.sidebar.checkbox("🔄 Auto Refresh (60s)", value=False)
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    # Navigation
    app_mode = st.sidebar.radio("Navigation", ["Terminal", "Market Scanner", "Trader Chat", "Admin Panel"])
    
    assets = {
        "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCHF=X", "USDCAD=X", "NZDUSD=X"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD"],
        "Metals": ["XAUUSD=X", "XAGUSD=X"] 
    }

    # --- VIEW: TERMINAL ---
    if app_mode == "Terminal":
        st.sidebar.divider()
        market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
        pair = st.sidebar.selectbox("Select Asset", assets[market], format_func=lambda x: x.replace("=X", "").replace("-USD", ""))
        
        tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h"], index=2)
        
        st.sidebar.divider()
        st.sidebar.subheader("📰 Market News")
        news_items = get_market_news(pair)
        for news in news_items:
            color_class = get_sentiment_class(news['title'])
            st.sidebar.markdown(f"<div class='news-card {color_class}'><div class='news-title'>{news['title']}</div></div>", unsafe_allow_html=True)

        data_period = get_data_period(tf)
        st.caption(f"Fetching {data_period} history for {tf} analysis...")
        
        df = yf.download(pair, period=data_period, interval=tf, progress=False)
        
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr_p = float(df['Close'].iloc[-1])
            st.title(f"{pair.replace('=X', '')} Terminal - {curr_p:.5f}")
            
            sigs, current_atr, sk_score = calculate_advanced_signals(df, tf)
            
            # Notification
            sk_signal = sigs['SK'][1]
            if sk_signal == "bull":
                st.markdown(f"<div class='notif-container notif-buy'>🔔 <b>SK BUY SIGNAL ({tf}):</b> Setup Detected (Score: {sk_score})</div>", unsafe_allow_html=True)
            elif sk_signal == "bear":
                st.markdown(f"<div class='notif-container notif-sell'>🔔 <b>SK SELL SIGNAL ({tf}):</b> Setup Detected (Score: {sk_score})</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='notif-container notif-wait'>📡 <b>MONITORING:</b> Waiting for SK System Confluence...</div>", unsafe_allow_html=True)

            # --- SIGNAL GRID ---
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='sig-box {sigs['TREND'][1]}'>TREND: {sigs['TREND'][0]}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='sig-box {sigs['SMC'][1]}'>SMC: {sigs['SMC'][0]}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='sig-box {sigs['ELLIOTT'][1]}'>WAVE: {sigs['ELLIOTT'][0]}</div>", unsafe_allow_html=True)
            c1.markdown(f"<div class='sig-box {sigs['ICT'][1]}'>ICT FVG: {sigs['ICT'][0]}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='sig-box {sigs['RETAIL_SYS'][1]}'>RETAIL: {sigs['RETAIL_SYS'][0]}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='sig-box {sigs['LIQ'][1]}'>LIQ: {sigs['LIQ'][0]}</div>", unsafe_allow_html=True)

            # Chart
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

            # Dashboard
            st.markdown(f"### 🎯 Hybrid AI Analysis (Focus: {tf})")
            c1, c2, c3 = st.columns(3)
            parsed = st.session_state.ai_parsed_data
            c1.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)
            
            st.divider()
            
            if st.button("🚀 Analyze with Hybrid AI", use_container_width=True):
                result, provider = get_hybrid_analysis(pair, {'price': curr_p}, sigs, news_items, current_atr, st.session_state.user, tf)
                st.session_state.ai_parsed_data = parse_ai_response(result)
                st.session_state.ai_result = result.split("DATA:")[0] if "DATA:" in result else result
                st.session_state.active_provider = provider
                st.rerun()

            if "ai_result" in st.session_state:
                st.markdown(f"**Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    # --- VIEW: MARKET SCANNER ---
    elif app_mode == "Market Scanner":
        st.title("📡 AI Market Scanner (Dual Mode)")
        st.markdown("Scans for High Probability **SK System** Setups.")
        
        scan_market_type = st.selectbox("Select Market", ["Forex", "Crypto"])
        
        if st.button("Start Hybrid Scan", type="primary"):
            with st.spinner(f"Scanning {scan_market_type} (Scalp & Swing)..."):
                scalp_res, swing_res = scan_market(assets[scan_market_type])
                
                tab_scalp, tab_swing = st.tabs(["⚡ Scalp Setups (5m)", "🐢 Swing Setups (4h)"])
                
                with tab_scalp:
                    if scalp_res:
                        st.success(f"Found {len(scalp_res)} Scalp Opps")
                        st.dataframe(pd.DataFrame(scalp_res))
                    else: st.warning("No high-quality Scalp setups found.")
                    
                with tab_swing:
                    if swing_res:
                        st.success(f"Found {len(swing_res)} Swing Opps")
                        st.dataframe(pd.DataFrame(swing_res))
                    else: st.warning("No high-quality Swing setups found.")

    # --- VIEW: TRADER CHAT ---
    elif app_mode == "Trader Chat":
        st.title("💬 Global Trader Room")
        
        chat_container = st.container()
        with chat_container:
            for msg in st.session_state.chat_history:
                st.markdown(f"<div class='chat-msg'><span class='chat-user'>{msg['user']}</span>: {msg['text']} <span style='font-size:10px;color:#555;'>{msg['time']}</span></div>", unsafe_allow_html=True)
        
        with st.form("chat_form", clear_on_submit=True):
            user_msg = st.text_input("Type your message...")
            if st.form_submit_button("Send"):
                if user_msg:
                    new_msg = {
                        "user": user_info['Username'],
                        "text": user_msg,
                        "time": datetime.now().strftime("%H:%M")
                    }
                    st.session_state.chat_history.append(new_msg)
                    st.rerun()

    # --- VIEW: ADMIN PANEL ---
    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Control Center")
            tab1, tab2 = st.tabs(["User Management", "Add New User"])
            with tab1:
                st.dataframe(pd.DataFrame([{"User": "Demo", "Usage": "0"}]), use_container_width=True)
            with tab2:
                with st.form("add_user_form"):
                    new_u = st.text_input("New Username")
                    new_p = st.text_input("Password", type="password")
                    if st.form_submit_button("Create"):
                         add_new_user(new_u, new_p, "User", 10)
                         st.success("Done")
        else:
            st.error("Access Denied.")
            
    # --- AUTO REFRESH LOGIC ---
    if auto_refresh:
        time.sleep(60)
        st.rerun()

```
