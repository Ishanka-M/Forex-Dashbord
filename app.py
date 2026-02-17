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
st.set_page_config(page_title="Infinite System v10.5 | Gemini 3.0", layout="wide", page_icon="⚡")

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

# --- 4. ADVANCED SIGNAL ENGINE ---
def calculate_advanced_signals(df, tf):
    if len(df) < 50: return None, 0, 0
    signals = {}
    c, h, l = df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    
    if tf in ["1m", "5m"]:
        ma_short = df['Close'].rolling(9).mean().iloc[-1]
        ma_long = df['Close'].rolling(21).mean().iloc[-1]
        trend_label = "Scalp Trend"
    else:
        ma_short = df['Close'].rolling(50).mean().iloc[-1]
        ma_long = df['Close'].rolling(200).mean().iloc[-1]
        trend_label = "Swing Trend"

    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    signals['SMC'] = ("Bullish BOS", "bull") if c > highs.iloc[-2] else (("Bearish BOS", "bear") if c < lows.iloc[-2] else ("Internal Struct", "neutral"))
    
    fvg_bull = df['Low'].iloc[-1] > df['High'].iloc[-3]
    fvg_bear = df['High'].iloc[-1] < df['Low'].iloc[-3]
    signals['ICT'] = ("Bullish FVG", "bull") if fvg_bull else (("Bearish FVG", "bear") if fvg_bear else ("No FVG", "neutral"))
    
    pivot_high = df['High'].rolling(20).max().iloc[-1]
    pivot_low = df['Low'].rolling(20).min().iloc[-1]
    
    retail_status = "Ranging"
    retail_col = "neutral"
    
    if abs(c - pivot_low) < (c * 0.0005): 
        retail_status, retail_col = "Support Test", "bull"
    elif abs(c - pivot_high) < (c * 0.0005): 
        retail_status, retail_col = "Resistance Test", "bear"
    elif c > pivot_high:
        retail_status, retail_col = "Breakout", "bull"
    elif c < pivot_low:
        retail_status, retail_col = "Breakdown", "bear"
        
    signals['RETAIL_SYS'] = (retail_status, retail_col)

    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
    signals['RSI'] = ("Overbought", "bear") if rsi_val > 70 else (("Oversold", "bull") if rsi_val < 30 else (f"Neutral ({int(rsi_val)})", "neutral"))

    signals['LIQ'] = ("Liquidity Sweep (L)", "bull") if l < df['Low'].iloc[-10:-1].min() else (("Liquidity Sweep (H)", "bear") if h > df['High'].iloc[-10:-1].max() else ("Holding", "neutral"))

    trend_direction = "bull" if c > ma_short else "bear"
    signals['TREND'] = (f"{trend_label} {trend_direction.upper()}", trend_direction)
    
    ema_20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    if c > ma_short:
        ew_status = "Impulse (Wave 3)" if c > ema_20 else "Correction (Wave 4)"
        ew_col = "bull" if c > ema_20 else "neutral"
    else:
        ew_status = "Impulse (Wave C)" if c < ema_20 else "Correction (Wave B)"
        ew_col = "bear" if c < ema_20 else "neutral"
    signals['ELLIOTT'] = (ew_status, ew_col)

    sk_score = 0
    if signals['TREND'][1] == "bull": sk_score += 2
    elif signals['TREND'][1] == "bear": sk_score -= 2
    if signals['SMC'][1] == "bull": sk_score += 1.5
    elif signals['SMC'][1] == "bear": sk_score -= 1.5
    if signals['RETAIL_SYS'][1] == "bull": sk_score += 1
    elif signals['RETAIL_SYS'][1] == "bear": sk_score -= 1
    if signals['RSI'][1] == "bull": sk_score += 0.5 
    elif signals['RSI'][1] == "bear": sk_score -= 0.5 

    signals['SK'] = ("SK PRIME BUY", "bull") if sk_score >= 3.5 else (("SK PRIME SELL", "bear") if sk_score <= -3.5 else ("No Setup", "neutral"))
    
    atr = (df['High']-df['Low']).rolling(14).mean().iloc[-1]
    return signals, atr, sk_score

# --- 5. INFINITE ALGORITHMIC ENGINE V10.5 ---
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
        note = f"SK System තහවුරු විය. Retail Support එක අසල. Trend: {trend}"
        sl, tp = curr_p - (atr * sl_mult), curr_p + (atr * tp_mult)
    elif sk_signal == "bear" and news_score <= 1:
        action = "SELL"
        note = f"SK System තහවුරු විය. Retail Resistance එක අසල. Trend: {trend}"
        sl, tp = curr_p + (atr * sl_mult), curr_p - (atr * tp_mult)
    else:
        action = "WAIT"
        note = "SK System අනුමැතිය නොමැත (Low Confluence)."
        sl, tp = curr_p - atr, curr_p + atr

    analysis_text = f"""
    ♾️ **INFINITE ALGO ENGINE V10.5 (RETAIL + SK)**
    
    📊 **Setup ({tf}):**
    • Mode: {trade_mode}
    • Action: {action}
    • SMC: {smc} | Retail: {sigs['RETAIL_SYS'][0]}
    
    💡 **SK Logic:**
    {note}
    
    DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}
    """
    return analysis_text

# --- 6. HYBRID AI ENGINE (MULTI-KEY GEMINI 3.0 -> PUTER FALLBACK) ---
def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info, tf):
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr, tf)
    
    current_usage = user_info.get("UsageCount", 0)
    max_limit = user_info.get("HybridLimit", 10)
    
    if current_usage >= max_limit and user_info["Role"] != "Admin":
        return algo_result, "Infinite Algo (Limit Reached)"

    prompt = f"""
    Act as a Senior Hedge Fund Trader (SK System Expert). Analyze {pair} on {tf}.
    Algo Output: {algo_result}
    Technical Data: Trend:{sigs['TREND'][0]}, SMC:{sigs['SMC'][0]}, RSI:{sigs['RSI'][0]}, Retail:{sigs['RETAIL_SYS'][0]}
    Final Format: Explain in Sinhala (Technical terms in English).
    FINAL FORMAT MUST BE: DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx
    """

    # --- GEMINI KEY ROTATION LOGIC (7 KEYS) ---
    gemini_keys = [st.secrets.get(f"GEMINI_API_KEY_{i}") for i in range(1, 8)]
    gemini_keys = [k for k in gemini_keys if k] # Filter out missing keys

    response_text = ""
    provider_name = ""

    with st.status(f"🚀 Infinite AI Activating ({tf})...", expanded=True) as status:
        # Step 1: Try Gemini Keys
        for idx, key in enumerate(gemini_keys):
            try:
                st.write(f"📡 Trying Gemini Key {idx+1}...")
                genai.configure(api_key=key)
                model = genai.GenerativeModel('gemini-2.0-flash') # User terms: Gemini 3.0
                response = model.generate_content(prompt)
                response_text = response.text
                provider_name = f"Gemini 3.0 Flash (Key {idx+1}) ⚡"
                status.update(label=f"✅ Gemini Analysis (Key {idx+1}) Complete!", state="complete", expanded=False)
                break # Success! Break the loop
            except Exception as e:
                st.write(f"⚠️ Key {idx+1} failed/limited. Trying next...")
                continue

        # Step 2: Fallback to Puter if all Gemini keys fail
        if not response_text:
            st.write("⚠️ All Gemini Keys Failed. Switching to Puter AI...")
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

def scan_market(assets_list):
    scalp_results, swing_results = [], []
    progress_bar = st.progress(0)
    total = len(assets_list) * 2
    step = 0
    for symbol in assets_list:
        try:
            # Scalp Scan
            df_sc = yf.download(symbol, period="5d", interval="5m", progress=False)
            if not df_sc.empty and len(df_sc) > 50:
                if isinstance(df_sc.columns, pd.MultiIndex): df_sc.columns = df_sc.columns.get_level_values(0)
                sigs_sc, _, score_sc = calculate_advanced_signals(df_sc, "5m")
                if abs(score_sc) >= 3: scalp_results.append({"Pair": symbol.replace("=X",""), "Signal": sigs_sc['SK'][0], "Score": score_sc, "Price": df_sc['Close'].iloc[-1]})
        except: pass
        step += 1
        progress_bar.progress(step / total)
        try:
            # Swing Scan
            df_sw = yf.download(symbol, period="6mo", interval="4h", progress=False)
            if not df_sw.empty and len(df_sw) > 50:
                if isinstance(df_sw.columns, pd.MultiIndex): df_sw.columns = df_sw.columns.get_level_values(0)
                sigs_sw, _, score_sw = calculate_advanced_signals(df_sw, "4h")
                if abs(score_sw) >= 2.5: swing_results.append({"Pair": symbol.replace("=X",""), "Signal": sigs_sw['SK'][0], "Score": score_sw, "Price": df_sw['Close'].iloc[-1]})
        except: pass
        step += 1
        progress_bar.progress(step / total)
    progress_bar.empty()
    return scalp_results, swing_results

# --- 7. MAIN APPLICATION ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>⚡ INFINITE SYSTEM v10.5 | PRO</h1>", unsafe_allow_html=True)
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
    st.sidebar.caption(f"Engine: Multi-Key Gemini 3.0 (Preview)")
    auto_refresh = st.sidebar.checkbox("🔄 Auto Refresh (60s)", value=False)
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    app_mode = st.sidebar.radio("Navigation", ["Terminal", "Market Scanner", "Trader Chat", "Admin Panel"])
    assets = {
        "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCHF=X", "USDCAD=X", "NZDUSD=X"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD"],
        "Metals": ["XAUUSD=X", "XAGUSD=X"] 
    }

    if app_mode == "Terminal":
        st.sidebar.divider()
        market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
        pair = st.sidebar.selectbox("Select Asset", assets[market], format_func=lambda x: x.replace("=X", "").replace("-USD", ""))
        tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h"], index=2)
        news_items = get_market_news(pair)
        for news in news_items:
            st.sidebar.markdown(f"<div class='news-card {get_sentiment_class(news['title'])}'>{news['title']}</div>", unsafe_allow_html=True)

        df = yf.download(pair, period=get_data_period(tf), interval=tf, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr_p = float(df['Close'].iloc[-1])
            st.title(f"{pair.replace('=X', '')} Terminal - {curr_p:.5f}")
            sigs, current_atr, sk_score = calculate_advanced_signals(df, tf)
            
            # Notification
            sk_signal = sigs['SK'][1]
            if sk_signal == "bull": st.markdown(f"<div class='notif-container notif-buy'>🔔 <b>SK BUY SIGNAL:</b> Score {sk_score}</div>", unsafe_allow_html=True)
            elif sk_signal == "bear": st.markdown(f"<div class='notif-container notif-sell'>🔔 <b>SK SELL SIGNAL:</b> Score {sk_score}</div>", unsafe_allow_html=True)
            else: st.markdown(f"<div class='notif-container notif-wait'>📡 Monitoring Market...</div>", unsafe_allow_html=True)

            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='sig-box {sigs['TREND'][1]}'>TREND: {sigs['TREND'][0]}</div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='sig-box {sigs['SMC'][1]}'>SMC: {sigs['SMC'][0]}</div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='sig-box {sigs['ELLIOTT'][1]}'>WAVE: {sigs['ELLIOTT'][0]}</div>", unsafe_allow_html=True)

            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown(f"### 🎯 Hybrid AI Analysis")
            parsed = st.session_state.ai_parsed_data
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{parsed['ENTRY']}</h2></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{parsed['SL']}</h2></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{parsed['TP']}</h2></div>", unsafe_allow_html=True)
            
            if st.button("🚀 Analyze with Gemini 3.0 (Preview)", use_container_width=True):
                result, provider = get_hybrid_analysis(pair, {'price': curr_p}, sigs, news_items, current_atr, st.session_state.user, tf)
                st.session_state.ai_parsed_data = parse_ai_response(result)
                st.session_state.ai_result = result.split("DATA:")[0] if "DATA:" in result else result
                st.session_state.active_provider = provider
                st.rerun()

            if "ai_result" in st.session_state:
                st.markdown(f"**Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    elif app_mode == "Market Scanner":
        st.title("📡 SK Market Scanner")
        scan_market_type = st.selectbox("Select Market", ["Forex", "Crypto"])
        if st.button("Start Hybrid Scan", type="primary"):
            with st.spinner("Scanning..."):
                sc, sw = scan_market(assets[scan_market_type])
                t1, t2 = st.tabs(["⚡ Scalp (5m)", "🐢 Swing (4h)"])
                with t1: st.dataframe(pd.DataFrame(sc))
                with t2: st.dataframe(pd.DataFrame(sw))

    elif app_mode == "Trader Chat":
        st.title("💬 Global Trader Room")
        for msg in st.session_state.chat_history:
            st.markdown(f"<div class='chat-msg'><span class='chat-user'>{msg['user']}</span>: {msg['text']}</div>", unsafe_allow_html=True)
        with st.form("chat_form", clear_on_submit=True):
            user_msg = st.text_input("Type message...")
            if st.form_submit_button("Send") and user_msg:
                st.session_state.chat_history.append({"user": user_info['Username'], "text": user_msg, "time": datetime.now().strftime("%H:%M")})
                st.rerun()

    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Center")
            with st.form("add_user_form"):
                new_u, new_p = st.text_input("New User"), st.text_input("Pass", type="password")
                if st.form_submit_button("Create"): 
                    add_new_user(new_u, new_p, "User", 10)
                    st.success("Done")
        else: st.error("Access Denied.")

    if auto_refresh:
        time.sleep(60)
        st.rerun()
